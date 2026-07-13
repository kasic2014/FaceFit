"use client";

import { useState } from "react";
import { FileText, Upload, X } from "lucide-react";
import { JobRoleSelect } from "./JobRoleSelect";

export function ApplicationInfoCard() {
  const [fileName] = useState("resume_lee.pdf");

  return (
    <div className="rounded-2xl border border-line-200 bg-white p-6">
      <div className="mb-5 flex items-center gap-2.5">
        <span className="grid size-6 place-items-center rounded-full bg-moss-900 text-[11px] font-bold text-white">1</span>
        <p className="text-[15px] font-bold text-ink-900">지원 정보</p>
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-4">
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-ink-400">지원 기업명</span>
            <input
              type="text"
              defaultValue="네이버"
              className="w-full rounded-xl border border-line-300 px-3.5 py-2.5 text-sm text-ink-900 outline-none focus:border-moss-500"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-ink-400">지원 직무</span>
            <JobRoleSelect defaultValue="백엔드 개발자" />
          </label>
        </div>

        <div>
          <span className="mb-1.5 block text-xs font-semibold text-ink-400">이력서 업로드</span>
          <p className="mb-2 text-[11px] text-ink-400">PDF 파일을 드래그하거나 클릭하여 업로드하세요.</p>
          <div className="flex flex-col items-center gap-1.5 rounded-xl border-[1.5px] border-dashed border-line-300 bg-ivory-100 px-4 py-5 text-center">
            <Upload size={18} className="text-ink-300" />
            <p className="text-[13px] font-medium text-ink-900">
              여기에 파일을 드래그하거나<br />
              <span className="font-semibold text-moss-700">파일 선택</span>
            </p>
          </div>

          {fileName && (
            <div className="mt-2.5 flex items-center gap-2.5 rounded-xl border border-line-200 px-3.5 py-2.5">
              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-red-50 text-red-500">
                <FileText size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink-900">{fileName}</p>
                <p className="text-[11px] text-ink-400">245 KB</p>
              </div>
              <button aria-label="파일 제거" className="text-ink-300 transition hover:text-ink-600">
                <X size={15} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
