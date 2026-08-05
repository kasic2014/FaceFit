import type { components } from "@/api/generated/facefit";

export type VoiceProfile = components["schemas"]["VoiceProfile"];

const acceptedTypes = ["audio/webm", "audio/mp4", "audio/wav"];
const maxBytes = 20 * 1024 * 1024;

export function createVoiceProfileFormData(consentLegalRecordId: string, file: File) {
  if (!acceptedTypes.includes(file.type)) throw new Error("Voice sample must be WebM, MP4, or WAV.");
  if (file.size > maxBytes) throw new Error("Voice sample must be 20MB or smaller.");
  const formData = new FormData();
  formData.append("consentLegalRecordId", consentLegalRecordId);
  formData.append("file", file);
  return formData;
}
