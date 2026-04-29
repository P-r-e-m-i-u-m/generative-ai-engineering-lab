export type RiskLevel = "low" | "medium" | "high";

export interface KnowledgeDocument {
  id: string;
  title: string;
  text: string;
  tags: string[];
}

export interface RetrievedChunk {
  documentId: string;
  title: string;
  score: number;
  excerpt: string;
}

export interface RagAnswer {
  question: string;
  answer: string;
  citations: RetrievedChunk[];
  confidence: number;
}

export interface PromptCase {
  id: string;
  input: string;
  expectedKeywords: string[];
  forbiddenKeywords: string[];
}

export interface PromptEvalResult {
  caseId: string;
  passed: boolean;
  score: number;
  missingKeywords: string[];
  forbiddenHits: string[];
}

export interface SafetyFinding {
  riskLevel: RiskLevel;
  category: "pii" | "legal" | "medical" | "financial" | "self-harm" | "none";
  reason: string;
}

export interface AgentStep {
  id: string;
  name: string;
  instruction: string;
  tool: "clarify" | "retrieve" | "draft" | "evaluate" | "human_review";
}

export interface AgentPlan {
  goal: string;
  steps: AgentStep[];
  handoffRequired: boolean;
}

const stopWords = new Set([
  "a",
  "an",
  "and",
  "are",
  "as",
  "for",
  "in",
  "is",
  "of",
  "on",
  "or",
  "the",
  "to",
  "with"
]);

export class GenerativeAiEngineeringLab {
  private documents: KnowledgeDocument[] = [];

  addDocument(document: KnowledgeDocument): void {
    this.documents.push(document);
  }

  retrieve(query: string, limit = 3): RetrievedChunk[] {
    const queryTerms = tokenize(query);
    return this.documents
      .map((document) => {
        const documentTerms = tokenize(`${document.title} ${document.text} ${document.tags.join(" ")}`);
        const overlap = queryTerms.filter((term) => documentTerms.includes(term));
        const score = overlap.length / Math.max(queryTerms.length, 1);

        return {
          documentId: document.id,
          title: document.title,
          score: Number(score.toFixed(2)),
          excerpt: createExcerpt(document.text, overlap)
        };
      })
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  }

  answerWithRag(question: string): RagAnswer {
    const citations = this.retrieve(question);
    const confidence = citations.length === 0 ? 0 : Math.min(95, Math.round((citations[0].score + citations.length * 0.1) * 100));

    return {
      question,
      answer:
        citations.length === 0
          ? "I do not have enough local knowledge to answer this confidently."
          : `Based on retrieved context: ${citations.map((citation) => citation.excerpt).join(" ")}`,
      citations,
      confidence
    };
  }

  evaluatePrompt(output: string, cases: PromptCase[]): PromptEvalResult[] {
    const normalizedOutput = output.toLowerCase();
    return cases.map((testCase) => {
      const missingKeywords = testCase.expectedKeywords.filter(
        (keyword) => !normalizedOutput.includes(keyword.toLowerCase())
      );
      const forbiddenHits = testCase.forbiddenKeywords.filter((keyword) =>
        normalizedOutput.includes(keyword.toLowerCase())
      );
      const expectedScore =
        (testCase.expectedKeywords.length - missingKeywords.length) /
        Math.max(testCase.expectedKeywords.length, 1);
      const score = Math.max(0, Number((expectedScore - forbiddenHits.length * 0.35).toFixed(2)));

      return {
        caseId: testCase.id,
        passed: score >= 0.8 && forbiddenHits.length === 0,
        score,
        missingKeywords,
        forbiddenHits
      };
    });
  }

  safetyScan(text: string): SafetyFinding[] {
    const lower = text.toLowerCase();
    const findings: SafetyFinding[] = [];

    if (/\b\d{3}-\d{2}-\d{4}\b/.test(text) || lower.includes("passport")) {
      findings.push({ riskLevel: "high", category: "pii", reason: "Possible sensitive identity data." });
    }
    if (lower.includes("sue") || lower.includes("contract") || lower.includes("legal advice")) {
      findings.push({ riskLevel: "medium", category: "legal", reason: "Legal-domain content should include disclaimers and human review options." });
    }
    if (lower.includes("diagnose") || lower.includes("dosage") || lower.includes("symptom")) {
      findings.push({ riskLevel: "high", category: "medical", reason: "Medical-domain content needs qualified professional review." });
    }
    if (lower.includes("loan") || lower.includes("credit") || lower.includes("eligibility")) {
      findings.push({ riskLevel: "high", category: "financial", reason: "Financial eligibility content can create high-impact decision risk." });
    }
    if (lower.includes("self harm") || lower.includes("kill myself")) {
      findings.push({ riskLevel: "high", category: "self-harm", reason: "Self-harm content requires crisis-safe handling." });
    }

    return findings.length > 0
      ? findings
      : [{ riskLevel: "low", category: "none", reason: "No obvious safety trigger found." }];
  }

  createAgentPlan(goal: string): AgentPlan {
    const findings = this.safetyScan(goal);
    const handoffRequired = findings.some((finding) => finding.riskLevel === "high");

    return {
      goal,
      handoffRequired,
      steps: [
        { id: "step-1", name: "Clarify", instruction: "Restate goal, assumptions, constraints, and success criteria.", tool: "clarify" },
        { id: "step-2", name: "Retrieve", instruction: "Collect trusted context and cite the sources.", tool: "retrieve" },
        { id: "step-3", name: "Draft", instruction: "Draft a grounded answer or artifact.", tool: "draft" },
        { id: "step-4", name: "Evaluate", instruction: "Check expected behavior, forbidden claims, and safety issues.", tool: "evaluate" },
        {
          id: "step-5",
          name: handoffRequired ? "Human Review" : "Return",
          instruction: handoffRequired ? "Route to a human reviewer before final delivery." : "Return the final answer with citations and limitations.",
          tool: handoffRequired ? "human_review" : "draft"
        }
      ]
    };
  }
}

export function createSampleLab(): GenerativeAiEngineeringLab {
  const lab = new GenerativeAiEngineeringLab();
  lab.addDocument({
    id: "rag-001",
    title: "RAG Basics",
    text: "Retrieval augmented generation retrieves relevant source chunks before drafting an answer. Strong RAG systems cite sources and admit uncertainty.",
    tags: ["rag", "retrieval", "citations"]
  });
  lab.addDocument({
    id: "eval-001",
    title: "Prompt Evaluation",
    text: "Prompt evaluation checks AI outputs against expected behavior, forbidden claims, safety requirements, and task-specific quality criteria.",
    tags: ["evals", "quality", "testing"]
  });
  lab.addDocument({
    id: "agent-001",
    title: "Agent Workflows",
    text: "Reliable agents break goals into steps, call tools, evaluate intermediate work, and ask for human review when risk is high.",
    tags: ["agents", "tools", "human-review"]
  });
  return lab;
}

export function createSampleReport() {
  const lab = createSampleLab();
  return {
    rag: lab.answerWithRag("How should a RAG answer use citations and uncertainty?"),
    evals: lab.evaluatePrompt("A good RAG answer uses retrieval, citations, and uncertainty.", [
      {
        id: "rag-quality",
        input: "Explain RAG quality.",
        expectedKeywords: ["retrieval", "citations", "uncertainty"],
        forbiddenKeywords: ["always correct", "no sources needed"]
      }
    ]),
    safety: lab.safetyScan("Explain loan eligibility with human review."),
    agent: lab.createAgentPlan("Build a cited RAG assistant for compliance questions.")
  };
}

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((term) => term.length > 2 && !stopWords.has(term));
}

function createExcerpt(text: string, terms: string[]): string {
  const uniqueTerms = [...new Set(terms)];
  if (uniqueTerms.length === 0) {
    return text.slice(0, 220);
  }

  const lower = text.toLowerCase();
  const firstIndex = uniqueTerms
    .map((term) => lower.indexOf(term))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];
  const start = Math.max(0, firstIndex - 70);
  const end = Math.min(text.length, firstIndex + 180);
  return text.slice(start, end).trim();
}
