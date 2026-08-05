import { Link, useParams } from "react-router";
import { Camera, CheckCircle2, ChevronLeft, Mic, RefreshCw, ScanFace, Volume2 } from "lucide-react";
import { AppNav } from "@/components/facefit/AppNav";
import { MediaPreview } from "@/components/facefit/interview/MediaPreview";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { useMediaDevices } from "@/hooks/useMediaDevices";
import { useMicLevel } from "@/hooks/useMicLevel";

const micLevelBars = 12;

export default function EquipmentPage() {
  const { sessionId } = useParams();
  const { stream, status, message, cameras, microphones, selection, start, refreshDevices, selectCamera, selectMicrophone } = useMediaDevices();
  const isReady = status === "ready";
  const micLevel = useMicLevel(stream);
  const activeBars = Math.round(micLevel * micLevelBars);

  return (
    <div className="min-h-screen bg-[#f7f5ef] text-ink-900">
      <AppNav active="AI 면접" />
      <PageContainer as="main" size="wide" className="pb-16 pt-7 md:pt-10">
        <Link to={sessionId ? `/sessions/${sessionId}/settings` : "/onboarding"} className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 transition hover:text-moss-900"><ChevronLeft size={16} />이전 단계</Link>

        <section className="mx-auto mt-5 max-w-[1120px] text-center">
          <div className="mx-auto flex h-14 w-40 items-center justify-center gap-4 rounded-[26px] border border-white/70 bg-white/55 shadow-[0_12px_30px_rgba(40,53,43,.08)]">
            <span className="h-7 w-7 rounded-[45%_55%_55%_45%] bg-[#5e4675] shadow-[inset_5px_4px_8px_rgba(255,255,255,.35)]" />
            <span className="h-7 w-7 rotate-45 rounded-[55%_35%_55%_35%] bg-[#cd714a] shadow-[inset_5px_4px_8px_rgba(255,255,255,.3)]" />
            <span className="h-7 w-6 rounded-[50%_30%_50%_30%] bg-[#70944a] shadow-[inset_5px_4px_8px_rgba(255,255,255,.3)]" />
          </div>
          <h1 className="mt-7 text-3xl font-bold tracking-[-.055em] md:text-4xl">정확한 분석을 위해 면접 환경을 체크해볼까요!</h1>
          <p className="mt-3 text-base text-ink-600">카메라와 마이크 권한을 허용하면 실제 장치 상태를 확인할 수 있어요.</p>

          <div className="mt-9 overflow-hidden rounded-2xl border border-[#1d2c26] bg-[#18221e] shadow-[0_20px_50px_rgba(20,31,26,.16)]">
            <div className="relative aspect-[16/7.3] overflow-hidden bg-[#18221e]">
              <MediaPreview stream={stream} className="absolute inset-0" label="카메라 미리보기" />
              {isReady && <><div className="pointer-events-none absolute left-1/2 top-[15%] h-[54%] w-[24%] -translate-x-1/2 rounded-[45%] border-2 border-dashed border-white/90" /><div className="pointer-events-none absolute left-[20%] right-[20%] top-[43%] border-t border-dashed border-white/90" /><span className="pointer-events-none absolute left-[20%] top-[43%] -translate-y-1/2 rounded-full bg-[#20372b]/90 px-3 py-1 text-xs font-bold text-white">눈높이</span><div className="pointer-events-none absolute bottom-[14%] left-[22%] right-[22%] border-t border-white/65" /><span className="pointer-events-none absolute right-[22%] bottom-[14%] translate-x-1/2 translate-y-1/2 rounded-full bg-[#20372b]/90 px-3 py-1 text-xs font-bold text-white">어깨선</span></>}
              <div className="absolute bottom-5 left-5 right-5 flex flex-wrap items-center justify-between gap-3">
                <span className="flex items-center gap-2 rounded-full bg-black/50 px-3 py-1.5 text-xs font-semibold text-white"><ScanFace size={14} />{isReady ? "카메라가 연결되었습니다." : "카메라와 마이크 권한이 필요합니다."}</span>
                <button type="button" onClick={() => void start()} disabled={status === "requesting"} className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-4 text-sm font-bold text-[#20372b] transition hover:bg-ivory-100 disabled:cursor-not-allowed disabled:opacity-60"><Camera size={16} />{status === "requesting" ? "권한 요청 중" : isReady ? "다시 연결" : "카메라·마이크 연결"}</button>
              </div>
            </div>
          </div>

          <p role="status" className={isReady ? "mt-4 text-sm font-semibold text-moss-700" : "mt-4 text-sm font-semibold text-sunset-700"}>{isReady ? "장치 테스트 준비가 완료되었습니다." : message || "연결 버튼을 눌러 권한을 요청해 주세요."}</p>

          <div className="mt-5 grid gap-2 text-left md:grid-cols-3">
            <DeviceSelect icon={Camera} label="카메라" value={selection.cameraId ?? ""} options={cameras} disabled={!isReady} onChange={selectCamera} />
            <DeviceSelect icon={Mic} label="마이크" value={selection.microphoneId ?? ""} options={microphones} disabled={!isReady} onChange={selectMicrophone} />
            <div className="flex items-center gap-3 rounded-xl border border-line-300 bg-white px-4 py-4 shadow-[0_7px_18px_rgba(40,45,39,.05)]"><Volume2 size={21} className="text-ink-700" /><span className="font-bold text-ink-900">스피커</span><span className="ml-auto text-xs text-ink-600">시스템 기본값</span></div>
          </div>

          <div className="mt-3 flex items-center gap-3 rounded-xl border border-line-300 bg-white px-4 py-3 text-left shadow-[0_7px_18px_rgba(40,45,39,.05)]">
            <Mic size={21} className="shrink-0 text-ink-700" />
            <span className="shrink-0 font-bold text-ink-900">입력 확인</span>
            <div className="flex flex-1 items-center gap-1" role="meter" aria-valuemin={0} aria-valuemax={micLevelBars} aria-valuenow={activeBars} aria-label="마이크 입력 세기">
              {Array.from({ length: micLevelBars }, (_, index) => <span key={index} className={index < activeBars ? "h-4 flex-1 rounded-full bg-moss-700" : "h-4 flex-1 rounded-full bg-ivory-200"} />)}
            </div>
            <span className="shrink-0 text-xs text-ink-600">{!isReady ? "연결 필요" : activeBars > 0 ? "입력 감지됨" : "말해 보세요"}</span>
          </div>

          <button type="button" onClick={() => void refreshDevices()} className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 transition hover:text-moss-900"><RefreshCw size={15} />장치 목록 새로고침</button>

          <section className="mt-10 grid gap-3 border-t border-line-200 pt-6 text-left md:grid-cols-4">
            {["얼굴이 화면 중앙에 보이는지 확인해 주세요.", "주변이 충분히 밝은지 확인해 주세요.", "마이크 입력이 켜져 있는지 확인해 주세요.", "주변 소음이 적은 공간을 이용해 주세요."].map((text) => <div key={text} className="flex items-center gap-2 text-sm text-ink-700"><CheckCircle2 size={16} className={isReady ? "shrink-0 text-[#32bb72]" : "shrink-0 text-ink-300"} />{text}</div>)}
          </section>

          <div className="mt-8 flex items-center justify-between border-t border-line-200 pt-6"><Link to="/onboarding" className="rounded-lg border border-line-300 bg-white px-5 py-3 text-sm font-bold">이전으로</Link><Link to={sessionId ? `/consent/${sessionId}` : "/onboarding"} aria-disabled={!isReady || !sessionId} onClick={(event) => { if (!isReady || !sessionId) event.preventDefault(); }} className={isReady && sessionId ? "rounded-lg bg-sunset-600 px-6 py-3 text-sm font-bold text-white shadow-[0_8px_18px_rgba(191,83,35,.22)] transition hover:bg-sunset-700" : "cursor-not-allowed rounded-lg bg-ink-300 px-6 py-3 text-sm font-bold text-white"}>동의 확인 및 면접 시작하기</Link></div>
        </section>
      </PageContainer>
    </div>
  );
}

type DeviceSelectProps = {
  icon: typeof Camera;
  label: string;
  value: string;
  options: { deviceId: string; label: string }[];
  disabled: boolean;
  onChange: (deviceId: string) => void;
};

function DeviceSelect({ icon: Icon, label, value, options, disabled, onChange }: DeviceSelectProps) {
  return <label className="flex min-w-0 items-center gap-3 rounded-xl border border-line-300 bg-white px-4 py-3 shadow-[0_7px_18px_rgba(40,45,39,.05)]"><Icon size={21} className="shrink-0 text-ink-700" /><span className="shrink-0 font-bold text-ink-900">{label}</span><select aria-label={`${label} 선택`} value={value} disabled={disabled || options.length === 0} onChange={(event) => onChange(event.target.value)} className="min-w-0 flex-1 bg-transparent text-xs text-ink-600 outline-none disabled:cursor-not-allowed disabled:text-ink-400"><option value="">기본 장치</option>{options.map((option) => <option key={option.deviceId} value={option.deviceId}>{option.label}</option>)}</select></label>;
}
