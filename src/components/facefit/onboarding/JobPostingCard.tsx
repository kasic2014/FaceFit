"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { FileUploader } from "@/components/facefit/ui/States";

const sample = "지원 직무의 주요 업무와 필요한 역량을 붙여 넣어 주세요. 공고문을 바탕으로 면접 질문을 구성합니다.";

export function JobPostingCard() {
  const [tab, setTab] = useState<"text" | "file">("text");
  return <section className="rounded-[18px] border border-line-200 bg-white p-6"><div className="mb-5 flex items-center gap-2.5"><span className="grid size-6 place-items-center rounded-full bg-moss-900 text-[11px] font-bold text-white">2</span><p className="text-[15px] font-bold text-ink-900">채용 공고문 등록</p></div><div className="grid grid-cols-2 rounded-xl border border-line-200 bg-ivory-100 p-1"><button onClick={()=>setTab("text")} className={cn("rounded-lg py-2 text-[13px] font-semibold",tab==="text"?"bg-white text-moss-700":"text-ink-400")}>공고문 직접 입력</button><button onClick={()=>setTab("file")} className={cn("rounded-lg py-2 text-[13px] font-semibold",tab==="file"?"bg-white text-moss-700":"text-ink-400")}>파일 업로드</button></div>{tab === "text" ? <label className="mt-4 block"><span className="mb-2 block text-xs font-semibold text-ink-400">공고문 내용</span><textarea defaultValue={sample} rows={7} className="w-full resize-none rounded-xl border border-line-300 px-4 py-3 text-[13px] leading-[1.7] text-ink-700 outline-none focus:border-moss-500"/></label> : <div className="mt-4"><FileUploader/></div>}</section>;
}
