export const voiceProfileStates = {
  unregistered: { title: "음성 프로필 미등록", description: "등록하지 않아도 면접과 리포트는 이용할 수 있지만, 개선 답변을 내 목소리로 들을 수는 없어요.", action: "음성 프로필 등록 안내 보기" },
  guide: { title: "음성 프로필 등록 안내", description: "짧은 안내 문장을 읽으면 개선 답변을 내 목소리에 가깝게 들을 수 있어요.", action: "등록 시작하기" },
  creating: { title: "음성 프로필 생성 중", description: "음성 특성을 정리하고 있어요. 생성이 끝나면 개선 답변을 내 목소리로 들을 수 있어요.", action: "생성 상태 확인" },
  ready: { title: "내 음성 프로필 준비 완료", description: "개선 답변을 내 목소리로 들으며 말하기 흐름을 다시 연습할 수 있어요.", action: "개선 답변 듣기" },
  failed: { title: "음성 프로필 생성 실패", description: "녹음 환경을 확인한 뒤 다시 시도해 주세요. 면접과 일반 개선 답변은 계속 이용할 수 있어요.", action: "다시 시도" },
} as const;

export const errorGuidance = {
  permission: "브라우저가 장치 사용을 허용하지 않아 확인할 수 없어요. 주소창 설정에서 권한을 허용한 뒤 다시 확인해 주세요.",
  device: "연결된 장치를 찾을 수 없어요. 카메라나 마이크를 연결한 뒤 다시 확인해 주세요.",
  analysis: "분석 처리에 시간이 더 필요해요. 마이페이지에서 완료된 리포트를 잠시 후 다시 확인해 주세요.",
};
