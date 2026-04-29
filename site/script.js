const phases = [
  {
    eyebrow: "Phase 00",
    title: "Foundations",
    body: "Understand the GenAI loop: user goal, prompt, context, output, evaluation, safety, and product action."
  },
  {
    eyebrow: "Phase 01",
    title: "Prompt Engineering",
    body: "Design prompts with roles, input contracts, output schemas, boundaries, and measurable quality criteria."
  },
  {
    eyebrow: "Phase 02",
    title: "RAG Systems",
    body: "Retrieve trusted knowledge before drafting, rank context, cite sources, and admit uncertainty."
  },
  {
    eyebrow: "Phase 03",
    title: "Agent Workflows",
    body: "Break goals into clear steps with retrieval, drafting, evaluation, and human handoff for risky tasks."
  },
  {
    eyebrow: "Phase 04",
    title: "Evals And Safety",
    body: "Turn AI behavior into tests: expected behavior, forbidden claims, safety risk, and regression checks."
  },
  {
    eyebrow: "Phase 05",
    title: "Production",
    body: "Ship with CI, traces, prompt versions, eval history, privacy controls, and release discipline."
  }
];

const demoText = {
  check: `npm run check

build passed
demo generated
Smoke tests passed.`,
  rag: `npm run demo:rag

question: How should RAG cite sources?
answer: Based on retrieved context...
citations: RAG Basics
confidence: 67`,
  agent: `npm run demo:agent

1. Clarify
2. Retrieve
3. Draft
4. Evaluate
5. Return or human review`
};

const phaseButtons = document.querySelectorAll(".phase");
const phaseDetail = document.querySelector(".phase-detail");

phaseButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const phase = phases[Number(button.dataset.phase)];
    phaseButtons.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    phaseDetail.innerHTML = `
      <p class="eyebrow">${phase.eyebrow}</p>
      <h3>${phase.title}</h3>
      <p>${phase.body}</p>
    `;
  });
});

const demoTabs = document.querySelectorAll(".demo-tab");
const demoOutput = document.querySelector(".demo-output code");

demoTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    demoTabs.forEach((item) => {
      item.classList.remove("active");
      item.setAttribute("aria-selected", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");
    demoOutput.textContent = demoText[tab.dataset.demo];
  });
});

const topbar = document.querySelector(".topbar");
window.addEventListener("scroll", () => {
  topbar.dataset.elevated = window.scrollY > 20 ? "true" : "false";
});

const canvas = document.querySelector("#field");
const ctx = canvas.getContext("2d");
let points = [];

function resize() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(window.innerWidth * ratio);
  canvas.height = Math.floor(window.innerHeight * ratio);
  canvas.style.width = `${window.innerWidth}px`;
  canvas.style.height = `${window.innerHeight}px`;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  points = Array.from({ length: Math.min(72, Math.floor(window.innerWidth / 18)) }, () => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    vx: (Math.random() - 0.5) * 0.28,
    vy: (Math.random() - 0.5) * 0.28
  }));
}

function draw() {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
  ctx.fillStyle = "#080b16";
  ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);

  for (const point of points) {
    point.x += point.vx;
    point.y += point.vy;
    if (point.x < 0 || point.x > window.innerWidth) point.vx *= -1;
    if (point.y < 0 || point.y > window.innerHeight) point.vy *= -1;
  }

  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const a = points[i];
      const b = points[j];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (distance < 150) {
        ctx.strokeStyle = `rgba(109, 125, 255, ${0.15 - distance / 1200})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }
  }

  for (const point of points) {
    ctx.fillStyle = "rgba(0, 194, 168, 0.72)";
    ctx.beginPath();
    ctx.arc(point.x, point.y, 1.8, 0, Math.PI * 2);
    ctx.fill();
  }

  requestAnimationFrame(draw);
}

resize();
draw();
window.addEventListener("resize", resize);
