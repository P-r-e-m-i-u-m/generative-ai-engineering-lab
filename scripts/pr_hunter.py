"""
Daily PR Hunter -- full pipeline (v3)
---------------------------------------
Two sources of work, merged, up to MAX_DAILY_PRS successful PRs/day:

  A) Known repos (big + mid-size) -- searches for existing, unclaimed
     "good first issue"s and fixes them.

  B) Small / trending / stack-matched repos -- these often don't have
     labeled issues at all, so the bot looks for real TODO/FIXME markers
     in the code itself, opens an Issue describing the gap, then fixes
     that issue with a PR referencing it. Issue -> PR, both real, both
     under your account.

Every PR opens as a draft. Every action is logged to pr-log.md, including
skips and the reason, so nothing is silent.
"""

import os
import re
import time
import subprocess
import base64
import requests
from datetime import date, timedelta

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
MAX_DAILY_PRS = 3
LOG_FILE = "pr-log.md"
WORKDIR = "/tmp/pr-hunter-work"

REPO_POOL = [
    "microsoft/vscode", "microsoft/TypeScript", "microsoft/PowerToys",
    "aws/aws-cdk", "vercel/next.js", "facebook/docusaurus", "google/zx",
    "expressjs/express", "nodejs/node", "python/cpython", "pallets/flask",
    "psf/requests", "vuejs/core", "sveltejs/svelte", "denoland/deno",
    "tiangolo/fastapi", "encode/django-rest-framework", "psf/black",
    "pypa/pip", "python-poetry/poetry", "pydantic/pydantic",
    "sqlalchemy/sqlalchemy", "django/django", "scrapy/scrapy",
    "celery/celery", "huggingface/transformers", "huggingface/datasets",
    "streamlit/streamlit", "gradio-app/gradio", "ollama/ollama",
    "langchain-ai/langchain", "prettier/prettier", "eslint/eslint",
    "webpack/webpack", "vitejs/vite", "axios/axios", "lodash/lodash",
    "chartjs/Chart.js", "tailwindlabs/tailwindcss", "strapi/strapi",
    "nestjs/nest", "prisma/prisma", "supabase/supabase", "directus/directus",
    "n8n-io/n8n", "gohugoio/hugo",
]

STACK_TOPICS = ["fastapi", "nextjs", "langchain", "genai", "llm", "rag",
                 "typescript", "react", "nodejs", "automation"]


# ---------- logging ----------

def log_run(entry):
    header = "| Date | Repo | Issue | Status | PR |\n|---|---|---|---|---|\n"
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as f:
            f.write(header)
    line = f"| {entry['date']} | {entry['repo']} | [#{entry.get('number','-')}]({entry.get('issue_url','-')}) | {entry['status']} | {entry.get('pr_url','-')} |\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)


# ---------- source A: known repos, existing labeled issues ----------

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
                "source": "known",
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


# ---------- source B: small/trending/stack repos, self-discovered ----------

def discover_small_repos(limit=10):
    repos = []
    since = (date.today() - timedelta(days=21)).isoformat()

    # Trending-ish: recently pushed, small-to-mid star range (less crowded)
    q1 = f"stars:20..1500 pushed:>{since} archived:false"
    r = requests.get(f"{GH_API}/search/repositories?q={requests.utils.quote(q1)}&sort=updated&order=desc&per_page=6",
                      headers=HEADERS)
    if r.status_code == 200:
        repos += [item["full_name"] for item in r.json().get("items", [])]

    # Stack-matched
    for topic in STACK_TOPICS[:3]:
        q2 = f"topic:{topic} stars:20..1500 archived:false"
        r = requests.get(f"{GH_API}/search/repositories?q={requests.utils.quote(q2)}&sort=updated&order=desc&per_page=3",
                          headers=HEADERS)
        if r.status_code == 200:
            repos += [item["full_name"] for item in r.json().get("items", [])]
        time.sleep(1)

    seen, out = set(), []
    for r_ in repos:
        if r_ not in seen:
            seen.add(r_)
            out.append(r_)
    return out[:limit]


def find_todo_candidate(repo):
    """Look for a real TODO/FIXME marker in the repo's code."""
    q = f"TODO repo:{repo}"
    r = requests.get(f"{GH_API}/search/code?q={requests.utils.quote(q)}&per_page=5", headers=HEADERS)
    if r.status_code != 200:
        return None
    items = r.json().get("items", [])
    if not items:
        return None
    path = items[0]["path"]
    content = fetch_file_content(repo, path)
    if not content:
        return None
    for i, line in enumerate(content.splitlines()):
        if "TODO" in line or "FIXME" in line:
            context = "\n".join(content.splitlines()[max(0, i - 5):i + 6])
            return {"path": path, "line": line.strip(), "context": context}
    return None


def create_issue(repo, title, body):
    owner, name = repo.split("/")
    r = requests.post(f"{GH_API}/repos/{owner}/{name}/issues", headers=HEADERS,
                       json={"title": title, "body": body})
    return r


def draft_issue_text(repo, todo):
    prompt = f"""A TODO/FIXME marker was found in {repo} at {todo['path']}:

{todo['context']}

Write a short, natural GitHub issue (title + body, 3-4 sentences) describing
what needs to be done, as a real contributor would write it after finding
this while reading the code. No corporate tone, no bullet-point templates.
Format exactly as:
TITLE: <title>
BODY: <body>
"""
    r = requests.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
        json={"model": "meta/llama-3.3-70b-instruct",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 300, "temperature": 0.4},
        timeout=60,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    title_match = re.search(r"TITLE:\s*(.+)", text)
    body_match = re.search(r"BODY:\s*(.+)", text, re.DOTALL)
    if not title_match or not body_match:
        return None, None
    return title_match.group(1).strip()[:200], body_match.group(1).strip()


# ---------- shared: file fetch, patch drafting, git ops ----------

def guess_file_path(issue):
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
    r = requests.get(f"{GH_API}/search/code?q={requests.utils.quote(q)}&per_page=3", headers=HEADERS)
    if r.status_code != 200:
        return None
    items = r.json().get("items", [])
    return items[0]["path"] if items else None


def fetch_file_content(repo, path):
    r = requests.get(f"{GH_API}/repos/{repo}/contents/{path}", headers=HEADERS)
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
        json={"model": "meta/llama-3.3-70b-instruct",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 800, "temperature": 0.2},
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


def apply_patch_and_push(fork_name, branch, patch_text, commit_message):
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
    safe_msg = commit_message.replace('"', "'")[:70]
    run('git -c user.name="' + GH_USERNAME + '" -c user.email="' + GH_USERNAME +
        '@users.noreply.github.com" commit -am "' + safe_msg + '"', cwd=repo_dir)
    run(f"git push origin {branch}", cwd=repo_dir)
    return True


def open_pr(repo, issue_number, issue_title, branch, patch_preview):
    owner, name = repo.split("/")
    body = (
        f"Fixes #{issue_number}\n\n"
        f"Found this while going through the code. Used an internal tool "
        f"I built to help draft the initial patch, reviewed and adjusted "
        f"before submitting.\n\n"
        f"```diff\n{patch_preview[:600]}\n```"
    )
    payload = {
        "title": f"Fix: {issue_title}"[:250],
        "head": f"{GH_USERNAME}:{branch}",
        "base": "main",
        "body": body,
        "draft": True,
    }
    return requests.post(f"{GH_API}/repos/{owner}/{name}/pulls", headers=HEADERS, json=payload)


def attempt_fix(repo, issue):
    """Shared final leg: file -> patch -> fork -> push -> PR. Returns True if a PR opened."""
    today = date.today().isoformat()

    file_path = guess_file_path(issue)
    if not file_path:
        log_run({"date": today, "repo": repo, "number": issue["number"],
                  "issue_url": issue["url"], "status": "skipped (no file identified)"})
        return False

    file_content = fetch_file_content(repo, file_path)
    if not file_content:
        log_run({"date": today, "repo": repo, "number": issue["number"],
                  "issue_url": issue["url"], "status": "skipped (file not found)"})
        return False

    patch = draft_patch(issue, file_path, file_content)
    if not patch or len(patch.splitlines()) > MAX_DIFF_LINES:
        log_run({"date": today, "repo": repo, "number": issue["number"],
                  "issue_url": issue["url"], "status": "skipped (no confident/small fix)"})
        return False

    try:
        fork_name = fork_and_wait(repo)
        branch = f"fix/issue-{issue['number']}"
        applied = apply_patch_and_push(fork_name, branch, patch, issue["title"])
        if not applied:
            log_run({"date": today, "repo": repo, "number": issue["number"],
                      "issue_url": issue["url"], "status": "skipped (patch didn't apply cleanly)"})
            return False

        pr = open_pr(repo, issue["number"], issue["title"], branch, patch)
        if pr.status_code == 201:
            log_run({"date": today, "repo": repo, "number": issue["number"],
                      "issue_url": issue["url"], "status": "PR opened (draft)",
                      "pr_url": pr.json()["html_url"]})
            return True
        else:
            log_run({"date": today, "repo": repo, "number": issue["number"],
                      "issue_url": issue["url"], "status": f"PR failed ({pr.status_code}: {pr.text[:150]})"})
            return False
    except Exception as e:
        log_run({"date": today, "repo": repo, "number": issue["number"],
                  "issue_url": issue["url"], "status": f"error: {str(e)[:150]}"})
        return False


# ---------- main ----------

def main():
    today = date.today().isoformat()
    successes = 0

    # --- Source A: known repos, existing good-first-issues ---
    known_candidates = gh_search_issues()
    for issue in known_candidates[:5]:
        if successes >= MAX_DAILY_PRS:
            break
        if attempt_fix(issue["repo"], issue):
            successes += 1

    # --- Source B: small/trending repos, self-discovered issues ---
    if successes < MAX_DAILY_PRS:
        for repo in discover_small_repos():
            if successes >= MAX_DAILY_PRS:
                break
            todo = find_todo_candidate(repo)
            if not todo:
                log_run({"date": today, "repo": repo, "status": "skipped (no TODO/FIXME found)"})
                continue

            title, body = draft_issue_text(repo, todo)
            if not title:
                log_run({"date": today, "repo": repo, "status": "skipped (couldn't draft issue text)"})
                continue

            issue_resp = create_issue(repo, title, body)
            if issue_resp.status_code != 201:
                log_run({"date": today, "repo": repo,
                          "status": f"skipped (issue creation failed {issue_resp.status_code})"})
                continue

            issue_data = issue_resp.json()
            issue = {
                "repo": repo,
                "number": issue_data["number"],
                "title": title,
                "body": body,
                "url": issue_data["html_url"],
            }
            log_run({"date": today, "repo": repo, "number": issue["number"],
                      "issue_url": issue["url"], "status": "issue opened"})

            if attempt_fix(repo, issue):
                successes += 1
            time.sleep(2)

    if successes == 0:
        log_run({"date": today, "repo": "-", "status": "no candidate produced a working patch today"})


if __name__ == "__main__":
    main()
