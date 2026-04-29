import assert from "node:assert/strict";
import { createSampleReport } from "../src/lab.js";

const report = createSampleReport();

assert.ok(report.rag.citations.length >= 1);
assert.ok(report.rag.answer.includes("retrieved"));
assert.equal(report.evals[0]?.passed, true);
assert.equal(report.safety[0]?.riskLevel, "high");
assert.ok(report.agent.steps.length >= 5);

console.log("Smoke tests passed.");
