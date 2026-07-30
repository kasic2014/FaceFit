# 동의 철회 절차

철회 요청을 접수하면 참여자 상태를 `WITHDRAWN`으로 표시하고 연결된 session,
answer, annotation 대기 항목과 dataset manifest 사용을 차단한다. 파일은 이번
단계에서 삭제하지 않는다. `DELETION_PENDING`, `QUARANTINED`,
`DELETED_CONFIRMED` 중 처리 계획 상태를 기록하되, 삭제 확인은 실제 승인된
절차가 수행된 경우에만 사용한다.

철회 전파 대상과 처리 시각을 감사 가능한 메타데이터로 남긴다. 백업·파생물·
동결 데이터 처리와 법적 보존 의무는 실제 수집 전 윤리·법무 검토가 필요하다.
