"""
Daily PR Hunter -- full pipeline
---------------------------------
1. Searches a curated repo pool for small, unclaimed "good first issue"s
2. Tries to locate a relevant file from the issue text
3. Drafts a minimal patch via NVIDIA-hosted Llama
4. Forks the repo, clones the fork, applies the patch, pushes a branch
5. Opens a real PR (as draft) under your account
6. Logs every attempt (found / skipped / opened / failed) to pr-log.md

Every PR is opened as a draft. You still glance at it before marking it
ready for review -- that's a 5-second click, not manual coding work.
"""

import os
import re
import time
import subprocess
import base64
import requests
from datetime import date

GH_TOKEN = os.environ["GH_TOKEN"]
GH_USERNAME = os.environ["GH_USERNAME"]
NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]

GH_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

MAX_DIFF_LINES = 60
LOG_FILE = "pr-log.md"
WORKDIR = "/tmp/pr-hunter-work"

REPO_POOL = [
    # Big tech (kept, but low hit-rate -- issues get claimed fast)
    "microsoft/vscode",
    "microsoft/TypeScript",
    "microsoft/PowerToys",
    "aws/aws-cdk",
    "vercel/next.js",
    "facebook/docusaurus",
    "google/zx",
    "expressjs/express",
    "nodejs/node",
    "python/cpython",
    "pallets/flask",
    "psf/requests",
    "vuejs/core",
    "sveltejs/svelte",
    "denoland/deno",
    # Mid-size, active, less crowded -- much higher realistic hit-rate
    "tiangolo/fastapi",
    "encode/django-rest-framework",
    "psf/black",
    "pypa/pip",
    "python-poetry/poetry",
    "pydantic/pydantic",
    "sqlalchemy/sqlalchemy",
    "django/django",
    "scrapy/scrapy",
    "celery/celery",
    "huggingface/transformers",
    "huggingface/datasets",
    "streamlit/streamlit",
    "gradio-app/gradio",
    "ollama/ollama",
    "langchain-ai/langchain",
    "prettier/prettier",
    "eslint/eslint",
    "webpack/webpack",
    "vitejs/vite",
    "axios/axios",
    "lodash/lodash",
    "chartjs/Chart.js",
    "tailwindlabs/tailwindcss",
    "strapi/strapi",
    "nestjs/nest",
    "prisma/prisma",
    "supabase/supabase",
    "directus/directus",
    "n8n-io/n8n",
    "gohugoio/hugo",
]


def log_run(entry):
    header = "| Date | Repo | Issue | Status | PR |\n|---|---|---|---|---|\n"
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(header)
    line = f"| {entry['date']} | {entry['repo']} | [#{entry['number']}]({entry['issue_url']}) | {entry['status']} | {entry.get('pr_url','-')} |\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)


def gh_search_issues():
    candidates = []
    for repo in REPO_POOL:
        q = f'repo:{repo} label:"good first issue" state:open'
        url = f"{GH_API}/search/issues?q={requests.utils.quote(q)}&sort=created&order=desc&per_page=5"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            continue
        for item in r.json().get("items", []):
            if item.get("assignee") or item.get("pull_request"):
                continue
            candidates.append({
                "repo": repo,
                "number": item["number"],
                "title": item["title"],
                "body": item.get("body") or "",
                "comments": item["comments"],
                "url": item["html_url"],
            })
        time.sleep(1)
    candidates.sort(key=lambda c: c["comments"])
    return candidates


def guess_file_path(issue):
    """First try to spot an explicit filename in the issue text.
    If that fails, fall back to GitHub code search using keywords
    from the title -- catches far more real, fixable issues."""
    text = f"{issue['title']} {issue['body']}"
    match = re.search(r'[\w\-/]+\.(py|js|ts|tsx|jsx|md|json|go|rs)\b', text)
    if match:
        return match.group(0)

    stopwords = {"the", "a", "an", "in", "on", "to", "of", "and", "is", "for",
                 "fix", "bug", "issue", "error", "when", "with", "not", "add"}
    keywords = [w for w in re.findall(r"[A-Za-z_]{4,}", issue["title"]) if w.lower() not in stopwords]
    if not keywords:
        return None

    q = f'{" ".join(keywords[:3])} repo:{issue["repo"]}'
    url = f"{GH_API}/search/code?q={requests.utils.quote(q)}&per_page=3"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return None
    items = r.json().get("items", [])
    return items[0]["path"] if items else None


def fetch_file_content(repo, path):
    url = f"{GH_API}/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return None


def draft_patch(issue, file_path, file_content):
    prompt = f"""You are drafting a minimal, correct unified-diff patch for this GitHub issue.

File: {file_path}
File content:
{file_content[:4000]}

Issue title: {issue['title']}
Issue body: {issue['body'][:2000]}

Return ONLY a valid unified diff (git apply compatible), nothing else.
If you cannot confidently produce a correct, minimal (<{MAX_DIFF_LINES} line) fix,
return exactly: SKIP
"""
    r = requests.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
        json={
            "model": "meta/llama-3.3-70b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800,
            "temperature": 0.2,
        },
        timeout=60,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    if text == "SKIP" or text.startswith("SKIP"):
        return None
    text = re.sub(r"^```(diff|patch)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result


def fork_and_wait(repo):
    owner, name = repo.split("/")
    requests.post(f"{GH_API}/repos/{repo}/forks", headers=HEADERS)
    fork_url = f"{GH_API}/repos/{GH_USERNAME}/{name}"
    for _ in range(12):
        r = requests.get(fork_url, headers=HEADERS)
        if r.status_code == 200:
            return name
        time.sleep(5)
    raise RuntimeError(f"Fork of {repo} did not become available in time")


def apply_patch_and_push(fork_name, branch, patch_text):
    repo_dir = os.path.join(WORKDIR, fork_name)
    os.makedirs(WORKDIR, exist_ok=True)
    run(f"rm -rf {repo_dir}")
    clone_url = f"https://{GH_USERNAME}:{GH_TOKEN}@github.com/{GH_USERNAME}/{fork_name}.git"
    run(f"git clone --depth 1 {clone_url} {repo_dir}")
    run(f"git checkout -b {branch}", cwd=repo_dir)

    patch_file = os.path.join(WORKDIR, "change.patch")
    with open(patch_file, "w") as f:
        f.write(patch_text + "\n")

    check = run(f"git apply --check {patch_file}", cwd=repo_dir, check=False)
    if check.returncode != 0:
        return False

    run(f"git apply {patch_file}", cwd=repo_dir)
    run('git -c user.name="' + GH_USERNAME + '" -c user.email="' + GH_USERNAME +
        '@users.noreply.github.com" commit -am "Fix: automated patch draft, human-reviewed before merge"',
        cwd=repo_dir)
    run(f"git push origin {branch}", cwd=repo_dir)
    return True


def open_pr(repo, issue, branch, patch_preview):
    owner, name = repo.split("/")
    body = (
        f"Fixes #{issue['number']}\n\n"
        f"Candidate fix drafted via an automated issue-triage tool I built "
        f"(scans good-first-issues, drafts a minimal patch, I review before "
        f"marking ready). Opening as a draft so you can weigh in on approach "
        f"before I finalize it.\n\n"
        f"```diff\n{patch_preview[:600]}\n```"
    )
    payload = {
        "title": f"Fix: {issue['title']}"[:250],
        "head": f"{GH_USERNAME}:{branch}",
        "base": "main",
        "body": body,
        "draft": True,
    }
    return requests.post(f"{GH_API}/repos/{owner}/{name}/pulls", headers=HEADERS, json=payload)


def main():
    today = date.today().isoformat()
    candidates = gh_search_issues()
    if not candidates:
        log_run({"date": today, "repo": "-", "number": "-", "issue_url": "-", "status": "no candidates found"})
        return

    for issue in candidates[:5]:
        file_path = guess_file_path(issue)
        if not file_path:
            log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                      "issue_url": issue["url"], "status": "skipped (no file identified)"})
            continue

        file_content = fetch_file_content(issue["repo"], file_path)
        if not file_content:
            log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                      "issue_url": issue["url"], "status": "skipped (file not found)"})
            continue

        patch = draft_patch(issue, file_path, file_content)
        if not patch or len(patch.splitlines()) > MAX_DIFF_LINES:
            log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                      "issue_url": issue["url"], "status": "skipped (no confident/small fix)"})
            continue

        try:
            fork_name = fork_and_wait(issue["repo"])
            branch = f"fix/issue-{issue['number']}"
            applied = apply_patch_and_push(fork_name, branch, patch)
            if not applied:
                log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                          "issue_url": issue["url"], "status": "skipped (patch didn't apply cleanly)"})
                continue

            pr = open_pr(issue["repo"], issue, branch, patch)
            if pr.status_code == 201:
                log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                          "issue_url": issue["url"], "status": "PR opened (draft)",
                          "pr_url": pr.json()["html_url"]})
                return
            else:
                log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                          "issue_url": issue["url"], "status": f"PR failed ({pr.status_code}: {pr.text[:150]})"})
        except Exception as e:
            log_run({"date": today, "repo": issue["repo"], "number": issue["number"],
                      "issue_url": issue["url"], "status": f"error: {str(e)[:150]}"})

    log_run({"date": today, "repo": "-", "number": "-", "issue_url": "-",
              "status": "no candidate produced a working patch today"})


if __name__ == "__main__":
    main()
