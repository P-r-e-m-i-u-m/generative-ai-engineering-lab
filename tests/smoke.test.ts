import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { createEvalReport } from "../src/eval-report.js";
import { createSampleReport } from "../src/lab.js";

const report = createSampleReport();
const evalCases = JSON.parse(
  readFileSync(new URL("evals/smoke-evals.json", `file://${process.cwd()}/`), "utf8")
) as Array<{
  id: string;
  expectedKeywords: string[];
  forbiddenKeywords: string[];
}>;

assert.ok(report.rag.citations.length >= 1);
assert.ok(report.rag.answer.includes("retrieved"));
assert.ok(report.rag.citations[0]?.excerpt.startsWith("Retrieval augmented generation"));
assert.equal(report.evals[0]?.passed, true);
assert.equal(report.safety[0]?.riskLevel, "high");
assert.ok(report.agent.steps.length >= 5);
assert.ok(evalCases.length >= 3);
assert.ok(evalCases.some((testCase) => testCase.id === "safety-boundary-financial"));
assert.ok(evalCases.every((testCase) => testCase.expectedKeywords.length > 0));
assert.ok(evalCases.every((testCase) => testCase.forbiddenKeywords.length > 0));

const evalReport = createEvalReport();
assert.equal(evalReport.totalCases, evalCases.length);
assert.equal(evalReport.failedCases, 0);
assert.equal(evalReport.passRate, 1);

const jsonReport = JSON.parse(
  execFileSync("node", ["dist/src/eval-report-cli.js", "--json"], { encoding: "utf8" })
) as { totalCases: number; failedCases: number };
assert.equal(jsonReport.totalCases, evalCases.length);
assert.equal(jsonReport.failedCases, 0);

console.log("Smoke tests passed.");
