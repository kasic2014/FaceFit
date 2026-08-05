import type { components } from "@/api/generated/facefit";

export type LegalActionType = components["schemas"]["LegalActionType"];
export type LegalDocumentSummary = components["schemas"]["LegalDocumentSummary"];
export type LegalDocumentDetail = components["schemas"]["LegalDocumentDetail"];
export type AccountOnboardingResult = components["schemas"]["OnboardingCompletion"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isActionType(value: unknown): value is LegalActionType {
  return value === "CONSENTED" || value === "ACKNOWLEDGED";
}

function isLegalDocumentSummary(value: unknown): value is LegalDocumentSummary {
  if (!isRecord(value)) return false;

  return typeof value.documentId === "string"
    && typeof value.title === "string"
    && typeof value.version === "string"
    && typeof value.requiredForOnboarding === "boolean"
    && isActionType(value.requiredAction)
    && typeof value.effectiveAt === "string";
}

export function parseLegalDocumentList(value: unknown) {
  if (!Array.isArray(value) || !value.every(isLegalDocumentSummary)) {
    throw new Error("Legal document API returned an invalid response shape.");
  }

  return value;
}

export function parseLegalDocumentDetail(value: unknown): LegalDocumentDetail {
  if (!isRecord(value)) {
    throw new Error("Legal document detail API returned an invalid response shape.");
  }

  const contentFormat = value.contentFormat;
  const content = value.content;
  if (!isLegalDocumentSummary(value) || contentFormat !== "MARKDOWN" || typeof content !== "string") {
    throw new Error("Legal document detail API returned an invalid response shape.");
  }

  return {
    ...value,
    contentFormat,
    content,
  };
}
