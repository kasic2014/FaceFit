import { Link } from "react-router-dom";
import { Camera, CheckCircle2, ChevronDown, ChevronLeft, Eye, Mic, Pause, Play, RefreshCw, ScanFace, Sun, Volume2, VolumeX } from "lucide-react";
import { useEffect, useState } from "react";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

type Device = "camera" | "microphone" | "speaker";
type VoiceStatus = "ready" | "unregistered" | "creating" | "failed";

const deviceLabels: Record<Device, { label: string; value: string; icon: typeof Camera }> = {
  camera: { label: "카메라", value: "FaceTime HD 카메라 (내장)", icon: Camera },
  microphone: { label: "마이크", value: "MacBook Pro 마이크 (내장)", icon: Mic },
  speaker: { label: "스피커", value: "MacBook Pro 스피커 (내장)", icon: Volume2 },
};

export default function EquipmentPage() {
  const [menu, setMenu] = useState<Device | null>(null);
  const [previewStarted, setPreviewStarted] = useState(false);
  const [testing, setTesting] = useState(false);
  const voiceStatus: VoiceStatus = "ready";

  useEffect(() => {
    if (!testing) return;
    const timer = window.setTimeout(() => setTesting(false), 10000);
    return () => window.clearTimeout(timer);
  }, [testing]);

  return (
    <div className="min-h-screen bg-[#f7f5ef] text-ink-900">
      <AppNav active="새 면접" />
      <PageContainer as="main" size="wide" className="pb-16 pt-7 md:pt-10">
        <Link to="/onboarding" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 transition hover:text-moss-900">
          <ChevronLeft size={16} /> 이전 단계
        </Link>

        <section className="mx-auto mt-5 max-w-[1120px] text-center">
          <div className="mx-auto flex h-14 w-40 items-center justify-center gap-4 rounded-[26px] border border-white/70 bg-white/55 shadow-[0_12px_30px_rgba(40,53,43,.08)]">
            <span className="h-7 w-7 rounded-[45%_55%_55%_45%] bg-[#5e4675] shadow-[inset_5px_4px_8px_rgba(255,255,255,.35)]" />
            <span className="h-7 w-7 rotate-45 rounded-[55%_35%_55%_35%] bg-[#cd714a] shadow-[inset_5px_4px_8px_rgba(255,255,255,.3)]" />
            <span className="h-7 w-6 rounded-[50%_30%_50%_30%] bg-[#70944a] shadow-[inset_5px_4px_8px_rgba(255,255,255,.3)]" />
          </div>
          <h1 className="mt-7 text-3xl font-bold tracking-[-.055em] md:text-4xl">정확한 분석을 위해 면접 환경을 체크해볼게요!</h1>
          <p className="mt-3 text-base text-ink-600">모든 장치가 연결되어야 면접을 시작할 수 있어요.</p>

          <div className="mt-9 overflow-hidden rounded-2xl border border-[#1d2c26] bg-[#18221e] shadow-[0_20px_50px_rgba(20,31,26,.16)]">
            <div className="relative grid aspect-[16/7.3] place-items-center overflow-hidden bg-[#18221e]">
              <img
                src="/images/user-webcam.png"
                alt="카메라 프리뷰 예시: 카메라 정면을 보고 앉은 사용자"
                className="absolute inset-0 size-full object-cover"
                loading="eager"
                fetchPriority="high"
              />
              <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(15,28,22,.28),transparent_26%,transparent_74%,rgba(15,28,22,.28))]" />
              <div className="pointer-events-none absolute left-1/2 top-[15%] h-[54%] w-[24%] -translate-x-1/2 rounded-[45%] border-2 border-dashed border-white/90 shadow-[0_0_0_999px_rgba(8,17,13,.08)]" />
              <div className="pointer-events-none absolute left-[20%] right-[20%] top-[43%] border-t border-dashed border-white/90" />
              <span className="pointer-events-none absolute left-[20%] top-[43%] -translate-y-1/2 rounded-full bg-[#20372b]/90 px-3 py-1 text-xs font-bold text-white">눈높이</span>
              <div className="pointer-events-none absolute bottom-[14%] left-[22%] right-[22%] border-t border-white/65" />
              <span className="pointer-events-none absolute right-[22%] bottom-[14%] translate-x-1/2 translate-y-1/2 rounded-full bg-[#20372b]/90 px-3 py-1 text-xs font-bold text-white">어깨선</span>
              <button onClick={() => setPreviewStarted(!previewStarted)} aria-label="카메라 미리보기 재생" className="relative z-10 grid size-16 place-items-center rounded-full border border-white/55 bg-black/35 text-white backdrop-blur transition hover:scale-105">
                {previewStarted ? <Pause size={26} fill="currentColor" /> : <Play size={27} fill="currentColor" />}
              </button>
              <div className="absolute bottom-5 left-5 flex items-center gap-2 rounded-full bg-black/45 px-3 py-1.5 text-xs font-semibold text-white"><ScanFace size={14} /> 얼굴 윤곽을 프레임 안에 맞춰 주세요</div>
            </div>
          </div>

          <div className="relative z-10 -mt-1 grid gap-2 rounded-b-2xl bg-[#f7f5ef] pt-4 md:grid-cols-3">
            {(Object.keys(deviceLabels) as Device[]).map((device) => <DeviceControl key={device} device={device} open={menu === device} onToggle={() => setMenu(menu === device ? null : device)} />)}
          </div>

          <div className="mx-auto mt-9 max-w-md">
            <h2 className="text-lg font-bold">마이크 음성 테스트</h2>
            <p className="mt-1 text-sm text-ink-600">아래 버튼을 누르고, 또렷하게 말해보세요.</p>
            <button onClick={() => setTesting(!testing)} className="mt-4 flex w-full items-center gap-4 rounded-full border border-line-300 bg-white px-4 py-3 text-left shadow-[0_8px_20px_rgba(40,45,39,.06)] transition hover:border-moss-300">
              <span className="grid size-11 shrink-0 place-items-center rounded-full border border-line-200 text-moss-900">{testing ? <Pause size={19} fill="currentColor" /> : <Mic size={20} />}</span>
              <Waveform active={testing} />
              <span className="shrink-0 text-xs tabular-nums text-ink-600">{testing ? "00:04" : "00:00"} / 00:10</span>
            </button>
            <p className="mt-3 text-xs text-ink-400">말하기가 감지되면 파형이 표시돼요.</p>
          </div>

          <section className="mt-10 grid gap-3 border-t border-line-200 pt-6 text-left md:grid-cols-4">
            {[{ icon: Eye, text: "얼굴이 화면 중앙에 보여요" }, { icon: Sun, text: "주변이 충분히 밝아요" }, { icon: Mic, text: "마이크 입력이 확인돼요" }, { icon: VolumeX, text: "주변 소음이 크지 않아요" }].map(({ icon: Icon, text }) => <div key={text} className="flex items-center gap-2 text-sm text-ink-700"><span className="grid size-6 place-items-center rounded-full bg-moss-300/35 text-moss-900"><Icon size={13} /></span>{text}</div>)}
          </section>

          <section className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-line-200 bg-white/70 px-5 py-4 text-left">
            <div><p className="text-sm font-bold">내 음성 프로필 <span className="ml-1 font-medium text-ink-400">· 선택 사항</span></p><p className="mt-1 text-xs text-ink-600">등록하면 개선 답변을 내 목소리로 들어볼 수 있어요.</p></div>
            <div className="flex items-center gap-2"><span className="text-xs font-semibold text-moss-700">{voiceStatus === "ready" ? "준비 완료" : voiceStatus === "creating" ? "준비 중" : voiceStatus === "failed" ? "확인 필요" : "미등록"}</span><Link to="/voice-profile" className="rounded-lg border border-line-300 px-3 py-2 text-xs font-bold text-ink-700">녹음 안내 보기</Link></div>
          </section>

          <div className="mt-8 flex items-center justify-between border-t border-line-200 pt-6"><Link to="/onboarding" className="rounded-lg border border-line-300 bg-white px-5 py-3 text-sm font-bold">이전으로</Link><Link to="/session/live" className="rounded-lg bg-sunset-600 px-6 py-3 text-sm font-bold text-white shadow-[0_8px_18px_rgba(191,83,35,.22)] transition hover:bg-sunset-700">면접 시작하기</Link></div>
        </section>
      </PageContainer>
    </div>
  );
}

function DeviceControl({ device, open, onToggle }: { device: Device; open: boolean; onToggle: () => void }) {
  const { label, value, icon: Icon } = deviceLabels[device];
  return <div className="relative"><button onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-3 rounded-xl border border-line-300 bg-white px-4 py-4 text-left shadow-[0_7px_18px_rgba(40,45,39,.05)] transition hover:border-moss-300"><Icon size={21} className="text-ink-700" /><span className="font-bold text-ink-900">{label}</span><span className="min-w-0 flex-1 truncate text-xs text-ink-600">{value}</span><CheckCircle2 size={18} className="text-[#32bb72]" /><ChevronDown size={16} className={open ? "rotate-180 transition" : "transition"} /></button>{open && <div className="absolute inset-x-0 z-20 mt-2 rounded-xl border border-line-200 bg-white p-2 text-left text-sm shadow-lg"><button onClick={onToggle} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 font-medium hover:bg-ivory-100"><CheckCircle2 size={15} className="text-[#32bb72]" />{value}</button><button onClick={onToggle} className="w-full rounded-lg px-3 py-2 text-left text-ink-600 hover:bg-ivory-100">다른 장치 검색 <RefreshCw className="ml-1 inline" size={13} /></button></div>}</div>;
}

function Waveform({ active }: { active: boolean }) { const heights = [12, 20, 29, 16, 35, 23, 41, 18, 33, 12, 28, 38, 20, 14, 26, 18]; return <span className="flex flex-1 items-center justify-center gap-1" aria-label="마이크 입력 파형">{heights.map((height, index) => <i key={index} className={active ? "w-1 rounded-full bg-moss-700 animate-pulse" : "w-1 rounded-full bg-ink-300"} style={{ height, animationDelay: `${index * 45}ms` }} />)}</span>; }
