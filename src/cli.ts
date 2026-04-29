import { createSampleLab, createSampleReport } from "./lab.js";

type Demo = "all" | "rag" | "evals" | "safety" | "agent";

const demo = (process.argv[2] ?? "all") as Demo;
const lab = createSampleLab();

function print(title: string, payload: unknown): void {
  console.log(`\n=== ${title} ===`);
  console.log(JSON.stringify(payload, null, 2));
}

switch (demo) {
  case "rag":
    print("RAG Demo", lab.answerWithRag("How should a RAG answer cite sources?"));
    break;
  case "evals":
    print("Prompt Evals Demo", createSampleReport().evals);
    break;
  case "safety":
    print("Safety Demo", lab.safetyScan("Explain loan eligibility with human review."));
    break;
  case "agent":
    print("Agent Plan Demo", lab.createAgentPlan("Build a RAG assistant for compliance questions."));
    break;
  case "all":
    print("Generative AI Engineering Lab", createSampleReport());
    break;
  default:
    console.error("Unknown demo. Use all, rag, evals, safety, or agent.");
    process.exitCode = 1;
}
