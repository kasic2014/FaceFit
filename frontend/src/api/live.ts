import type { components } from "@/api/generated/facefit";

export type InterviewQuestion = components["schemas"]["InterviewQuestion"];
export type QuestionPending = components["schemas"]["QuestionPending"];
export type InterviewComplete = components["schemas"]["InterviewComplete"];
export type CurrentQuestion = components["schemas"]["CurrentQuestion"];
export type InterviewAnswer = components["schemas"]["InterviewAnswer"];
export type PlaybackAccess = components["schemas"]["PlaybackAccess"];

export function isInterviewQuestion(value: CurrentQuestion): value is InterviewQuestion {
  return "questionId" in value;
}

export function isInterviewComplete(value: CurrentQuestion): value is InterviewComplete {
  return "nextQuestionStatus" in value && value.nextQuestionStatus === "INTERVIEW_COMPLETE";
}

export function createAnswerFormData(questionId: string, blob: Blob, recordedDurationMs: number, endedBy: "USER_BUTTON" | "SPACE_KEY" | "SILENCE_CONFIRMED") {
  if (recordedDurationMs < 1000 || recordedDurationMs > 300000) throw new Error("Answer duration must be between 1 second and 5 minutes.");
  if (blob.size > 200 * 1024 * 1024) throw new Error("Answer file must be 200MB or smaller.");
  const extension = blob.type.includes("mp4") ? "mp4" : "webm";
  const formData = new FormData();
  formData.append("questionId", questionId);
  formData.append("file", blob, `answer.${extension}`);
  formData.append("recordedDurationMs", String(Math.round(recordedDurationMs)));
  formData.append("endedBy", endedBy);
  return formData;
}
