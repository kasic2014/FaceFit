import type { components } from "@/api/generated/facefit";

export type AnalysisStatus = components["schemas"]["AnalysisStatus"];
export type ReportData = components["schemas"]["ReportData"];
export type ReportProcessing = components["schemas"]["ReportProcessing"];
export type ReportResponse = ReportData | ReportProcessing;
export type InterviewHistoryPage = components["schemas"]["InterviewHistoryPage"];
export type GrowthData = components["schemas"]["GrowthData"];

export function isReportData(value: ReportResponse): value is ReportData {
  return "report" in value && value.reportStatus === "SUCCEEDED";
}
