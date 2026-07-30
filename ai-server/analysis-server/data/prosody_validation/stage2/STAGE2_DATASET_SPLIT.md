# Stage 2 Dataset Split

## 역할 분리

- SPK001은 `development_pilot`이며 독립 검증 표본이 아니다.
- SPK002~SPK005는 `held_out_validation` 신규 화자 검증에 사용한다.
- SPK001과 신규 화자를 같은 검증 역할로 합치지 않는다.

## 동결 및 비교 원칙

- SESSION001 결과를 보고 Stage 2 기준이나 임계값을 임의로 조정하지 않는다.
- 알고리즘 변경이 필요하면 변경 전 기준과 변경 후 결과를 모두 보존한다.
- Stage 2 성능은 전체 5명과 신규 4명 결과를 분리하여 보고한다.
- 화자별 결과를 숨기고 전체 중앙값만 제시하지 않는다.
- 실패 파일, 제외 파일과 제외 사유도 함께 기록한다.

## 보고 단위

- Development pilot: SPK001
- Held-out validation: SPK002, SPK003, SPK004, SPK005
- 전체 요약은 역할별·화자별 결과와 함께 제시할 때만 보조적으로 사용한다.
