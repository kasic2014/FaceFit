export type PrototypeRecord = {
  id: string;
  company: string;
  role: string;
  date: string;
  interviewer: string;
  score: number;
  summary: string;
  questions: Array<{
    question: string;
    answer: string;
    evidence: string;
    score: number;
  }>;
  growthTask: {
    title: string;
    reason: string;
    practice: string;
  };
};

export const latestRecord: PrototypeRecord = {
  id: "naver-backend-20260710",
  company: "네이버 (NAVER)",
  role: "백엔드 개발자",
  date: "2026.07.10",
  interviewer: "기술 면접관 · 일반 · 5문항",
  score: 78,
  summary: "답변의 구조와 문제를 좁혀 가는 과정은 명확했습니다. 다음 재연습에서는 카메라 시선을 유지하며 결론을 먼저 전달하는 데 집중해 보세요.",
  questions: [
    {
      question: "이미지 업로드 오류를 해결하셨다고 했는데요. 어떤 현상부터 확인했고, API 무효화 시점을 수정해야 한다고 판단한 근거는 무엇이었나요?",
      answer: "캐시 키를 먼저 분리해 재현 조건을 좁혔고, API 응답과 무효화 시점을 함께 수정했습니다.",
      evidence: "문제 재현 → 원인 분리 → 수정 결과의 흐름이 답변에 포함됐습니다.",
      score: 82,
    },
    {
      question: "협업 과정에서 기술적 의견이 달랐을 때, 어떤 기준으로 결정을 정리했나요?",
      answer: "사용자 영향과 배포 위험도를 기준으로 선택지를 비교하고, 팀과 실험 범위를 합의했습니다.",
      evidence: "판단 기준은 분명했지만 결론을 먼저 말하면 전달력이 더 좋아집니다.",
      score: 69,
    },
  ],
  growthTask: {
    title: "결론을 먼저 말하고, 판단 근거를 30초 안에 정리하기",
    reason: "답변 내용은 충분했지만 핵심 결론이 뒤에 나와 전달력이 약해졌습니다.",
    practice: "첫 문장에 결론을 말한 뒤, 상황·판단·결과 순서로 다시 답해보세요.",
  },
};

export const findPrototypeRecord = (recordId: string) =>
  recordId === latestRecord.id ? latestRecord : undefined;
