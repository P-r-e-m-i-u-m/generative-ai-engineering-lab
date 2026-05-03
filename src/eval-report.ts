import { readFileSync } from "node:fs";
import { GenerativeAiEngineeringLab, PromptCase } from "./lab.js";

export interface EvalReportCase {
  id: string;
  passed: boolean;
  score: number;
  expectedKeywords: string[];
  forbiddenKeywords: string[];
  missingKeywords: string[];
  forbiddenHits: string[];
}

export interface EvalReport {
  generatedAt: string;
  totalCases: number;
  passedCases: number;
  failedCases: number;
  passRate: number;
  cases: EvalReportCase[];
}

const sampleOutputs: Record<string, string> = {
  "rag-quality": "A strong RAG answer uses retrieval, includes citations, and admits uncertainty when context is incomplete.",
  "safety-boundary-financial": "Loan eligibility is a high-impact risk area, so the workflow should include human review before a final decision.",
  "agent-planning-quality": "A reliable agent should clarify the goal, retrieve context, draft the answer, evaluate it, and request human review when needed."
};

export function loadEvalCases(path = "evals/smoke-evals.json"): PromptCase[] {
  return JSON.parse(readFileSync(path, "utf8")) as PromptCase[];
}

export function createEvalReport(cases = loadEvalCases()): EvalReport {
  const lab = new GenerativeAiEngineeringLab();
  const results = cases.map((testCase) => {
    const output = sampleOutputs[testCase.id] ?? testCase.input;
    const result = lab.evaluatePrompt(output, [testCase])[0];

    return {
      id: testCase.id,
      passed: result.passed,
      score: result.score,
      expectedKeywords: testCase.expectedKeywords,
      forbiddenKeywords: testCase.forbiddenKeywords,
      missingKeywords: result.missingKeywords,
      forbiddenHits: result.forbiddenHits
    };
  });
  const passedCases = results.filter((result) => result.passed).length;

  return {
    generatedAt: new Date().toISOString(),
    totalCases: results.length,
    passedCases,
    failedCases: results.length - passedCases,
    passRate: results.length === 0 ? 0 : Number((passedCases / results.length).toFixed(2)),
    cases: results
  };
}

export function formatEvalReport(report: EvalReport): string {
  const header = [
    "Eval Report",
    `Generated: ${report.generatedAt}`,
    `Cases: ${report.passedCases}/${report.totalCases} passed`,
    `Pass rate: ${Math.round(report.passRate * 100)}%`
  ];
  const lines = report.cases.map((testCase) => {
    const status = testCase.passed ? "PASS" : "FAIL";
    return [
      `${status} ${testCase.id} (${testCase.score})`,
      `  expected: ${testCase.expectedKeywords.join(", ")}`,
      `  forbidden: ${testCase.forbiddenKeywords.join(", ")}`,
      `  missing: ${testCase.missingKeywords.join(", ") || "none"}`,
      `  forbidden hits: ${testCase.forbiddenHits.join(", ") || "none"}`
    ].join("\n");
  });

  return [...header, "", ...lines].join("\n");
}

