import type { SVGProps } from "react";

/**
 * Face Fit 자체 제작 기능 아이콘 세트.
 * 24x24 viewBox, 동일 stroke-width(1.6), round cap/join.
 * 기본색은 currentColor(딥그린 계열), 강조 포인트만 --color-sunset-600 사용.
 */
type IconProps = SVGProps<SVGSVGElement>;

const base = {
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function ResumeAnalysisIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M7 3.5h7.5L18 7v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" />
      <path d="M14.5 3.5V7H18" />
      <path d="M8.75 11h6.5M8.75 13.5h6.5M8.75 16h4" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function InterviewerPersonaIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="9.5" cy="8" r="3" />
      <path d="M4.5 19c0-2.9 2.24-5 5-5s5 2.1 5 5" />
      <path d="M15.5 5.3c1.3.4 2.2 1.6 2.2 3s-.9 2.6-2.2 3" stroke="var(--color-sunset-600)" />
      <path d="M16.5 14.3c1.9.6 3.2 2.4 3.2 4.7" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function LiveInterviewIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="3" y="6" width="13" height="12" rx="2" />
      <path d="M16 10.5 20.5 7.6a.8.8 0 0 1 1.2.68v7.44a.8.8 0 0 1-1.2.68L16 13.5" />
      <circle cx="7" cy="10.2" r="1" fill="var(--color-sunset-600)" stroke="none" />
    </svg>
  );
}

export function FollowUpQuestionIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 6.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6.5v5A1.5 1.5 0 0 1 14.5 13H10l-3.2 3v-3H5.5A1.5 1.5 0 0 1 4 11.5Z" />
      <path d="M13.5 15.5a1.2 1.2 0 0 1 1.2-1.2h4.6a1.2 1.2 0 0 1 1.2 1.2v3.4a1.2 1.2 0 0 1-1.2 1.2h-2.9L15 21.5v-1.6h-.3a1.2 1.2 0 0 1-1.2-1.2Z" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function EyeAnalysisIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.6" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function SpeechAnalysisIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="9.5" y="2.75" width="5" height="9" rx="2.5" />
      <path d="M6 11a6 6 0 0 0 12 0" />
      <path d="M12 17v3.5M9 20.5h6" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function PostureAnalysisIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="4.5" r="2" />
      <path d="M12 6.5v6l-3.5 7M12 12.5l3.5 7" />
      <path d="M7.5 10h9" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function ContentAnalysisIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5Z" />
      <path d="M7.5 9h9M7.5 12h9M7.5 15h5.5" />
      <path d="m16 14.5 1 1 2-2.2" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function AnswerImprovementIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M5 18 9.5 9l3 4.5L16 8l3 5.5" />
      <path d="M14.5 5.5 16 8l2.5-1.2" stroke="var(--color-sunset-600)" />
      <path d="M4 20.5h16" />
    </svg>
  );
}

export function VoicePlaybackIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M6.5 9v6M9.5 6.5v11M12.5 4v16M15.5 7.5v9M18.5 10v4" />
      <path d="M18.5 12h2.3" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function VoiceProfileIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3.5a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0v-5a3 3 0 0 1 3-3Z" />
      <path d="M6.5 11a5.5 5.5 0 0 0 11 0" />
      <path d="M12 16.5v3.8" />
      <circle cx="17.3" cy="6.7" r="1.4" fill="var(--color-sunset-600)" stroke="none" />
    </svg>
  );
}

export function ReverseQuestionIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="11.5" cy="11.5" r="7.5" />
      <path d="M9.2 9.4a2.3 2.3 0 1 1 3.4 2c-.9.55-1.3 1-1.3 2" />
      <circle cx="11.4" cy="16.3" r="0.15" fill="currentColor" />
      <path d="m17.2 17.2 3.8 3.8" stroke="var(--color-sunset-600)" />
    </svg>
  );
}

export function GrowthHistoryIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 20V4" />
      <path d="M4 20h16" />
      <path d="M6.5 16.5 10 12l3 2.5 4.5-6" stroke="var(--color-sunset-600)" />
      <circle cx="6.5" cy="16.5" r="1" fill="currentColor" stroke="none" />
      <circle cx="10" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="13" cy="14.5" r="1" fill="currentColor" stroke="none" />
      <circle cx="17.5" cy="8.5" r="1" fill="var(--color-sunset-600)" stroke="none" />
    </svg>
  );
}

export function PrivacyControlIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3.5 5 6.2v5.3c0 4.4 3 6.8 7 8 4-1.2 7-3.6 7-8V6.2Z" />
      <path d="m9 12 2 2 4-4.3" stroke="var(--color-sunset-600)" />
    </svg>
  );
}
