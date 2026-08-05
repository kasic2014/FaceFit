import type { components } from "@/api/generated/facefit";

export type ProcessingStatus = components["schemas"]["ProcessingStatus"];
export type AiJobRole = components["schemas"]["AiJobRole"];
export type Persona = components["schemas"]["Persona"];
export type Difficulty = components["schemas"]["Difficulty"];
export type CareerDocument = components["schemas"]["CareerDocument"];
export type CareerDocumentPage = components["schemas"]["CareerDocumentPage"];
export type ResumeInterviewProfileSummary =
  components["schemas"]["ResumeInterviewProfileSummary"];
export type JobPosting = components["schemas"]["JobPosting"];
export type JobPostingPage = components["schemas"]["JobPostingPage"];
export type JobPostingUpdate = components["schemas"]["JobPostingUpdate"];
export type InterviewSession = components["schemas"]["InterviewSession"];
export type InterviewSessionUpdate =
  components["schemas"]["InterviewSessionUpdate"];

const maxUploadBytes = 10 * 1024 * 1024;

function validateFile(file: File, acceptedTypes: string[], label: string) {
  if (file.size > maxUploadBytes)
    throw new Error(`${label} 파일은 10MB 이하여야 합니다.`);
  if (!acceptedTypes.includes(file.type))
    throw new Error(`${label} 파일 형식을 확인해 주세요.`);
}

export function createCareerDocumentFormData(
  file: File,
  documentType: CareerDocument["documentType"] = "RESUME",
) {
  validateFile(
    file,
    [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
    "이력서",
  );
  const formData = new FormData();
  formData.append("file", file);
  formData.append("documentType", documentType);
  return formData;
}

export function createJobPostingFormData(file: File, targetJobRole: AiJobRole) {
  validateFile(
    file,
    ["application/pdf", "image/jpeg", "image/png"],
    "지원공고",
  );
  const formData = new FormData();
  formData.append("inputType", "FILE");
  formData.append("targetJobRole", targetJobRole);
  formData.append("file", file);
  return formData;
}
