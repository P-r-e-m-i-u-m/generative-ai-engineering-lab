import { createEvalReport, formatEvalReport } from "./eval-report.js";

const report = createEvalReport();
const format = process.argv.includes("--json") ? "json" : "text";

console.log(format === "json" ? JSON.stringify(report, null, 2) : formatEvalReport(report));
