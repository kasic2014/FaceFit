import { afterEach, describe, expect, it, vi } from "vitest";
import { selectMimeType } from "@/hooks/useAnswerRecorder";

describe("selectMimeType", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefers mp4 for Safari-class browsers that only support it", () => {
    vi.stubGlobal("MediaRecorder", { isTypeSupported: (type: string) => type === "video/mp4;codecs=avc1,mp4a" });
    expect(selectMimeType()).toBe("video/mp4;codecs=avc1,mp4a");
  });

  it("falls back to plain webm when only that is supported", () => {
    vi.stubGlobal("MediaRecorder", { isTypeSupported: (type: string) => type === "video/webm" });
    expect(selectMimeType()).toBe("video/webm");
  });

  it("returns an empty string when nothing is supported", () => {
    vi.stubGlobal("MediaRecorder", { isTypeSupported: () => false });
    expect(selectMimeType()).toBe("");
  });
});
