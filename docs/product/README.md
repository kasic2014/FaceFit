# FaceFit 제품 산출문서

> 기준일: 2026-07-20  
> 문서 상태: 실시간 아바타 면접 MVP 기준안

이 폴더는 FaceFit의 제품 범위, 목표, 기술 구조, 실행 순서를 한곳에서 관리한다. 화면설계서와 서비스 소개 자료를 기준으로 정리했으며, React+Vite 프론트엔드, OpenAvatarChat + MuseTalk 기반 실시간 면접관 구현 계획을 연결한다.

## 공식 개발 착수 전 산출물

전체 00~20 문서, 역할별 읽는 순서, 미확정 항목과 업데이트 방법은 [FaceFit 기획 산출물 인덱스](README_FaceFit_기획산출물.md)를 기준으로 한다. 최종 정합성은 [산출물 검증보고서](99_산출물_검증보고서.md)에서 확인한다.

## 기존 제품·기술 참고 문서

| 문서 | 용도 | 주요 독자 |
| --- | --- | --- |
| [PRD](./PRD.md) | 사용자 문제, 제품 범위, 기능·비기능 요구사항, 수용 기준 | 전 팀 |
| [OKR](./OKR.md) | MVP 검증 목표와 정량 결과 지표 | PM, 리드 |
| [실시간 아바타 아키텍처](./REALTIME_AVATAR_ARCHITECTURE.md) | OpenAvatarChat + MuseTalk 통합 구조, 지연 예산, 배포·장애 대응 | BE, AI, FE |
| [MVP 로드맵](./MVP_ROADMAP.md) | 단계별 구현 순서, 우선순위, 완료 조건, 리스크 | 전 팀 |
| [요구사항 추적표](./REQUIREMENTS_TRACEABILITY.md) | 화면·요구사항·구현 상태의 연결 | PM, QA, 개발 |

## 문서 운영 원칙

- PRD가 제품 범위의 기준 문서이며, 다른 문서와 충돌할 때 PRD의 최신 결정 기록을 따른다.
- 목표 수치는 현재 실측값이 아니라 MVP 검증을 위한 목표값이다. 최초 부하·사용성 테스트 후 기준선을 갱신한다.
- 채용 합격 여부를 판정하는 서비스가 아니라, 지원자가 스스로 개선하는 연습·코칭 서비스로 한정한다.
- 감정 추정값은 진단이나 점수에 사용하지 않는다. 리포트는 관측 가능한 행동과 답변 근거를 우선한다.
- 음성·영상·얼굴 랜드마크는 민감정보로 취급하며 최소 수집, 명시적 동의, 보존기간 분리 원칙을 적용한다.

## 기준 자료

- `FACE-FIT_ 설명 가능한 AI 면접 코칭 서비스.pdf`
- `FaceFit_UIUX_멘토링_화면설계서.pdf`
- `uiux멘토링화면설계서.html`
- 현재 저장소의 React+Vite 화면·컴포넌트와 전환 완료 기준
- [OpenAvatarChat 공식 저장소](https://github.com/HumanAIGC-Engineering/OpenAvatarChat)
- [OpenAvatarChat MuseTalk 빠른 시작](https://humanaigc-engineering.github.io/OpenAvatarChat/getting-started/musetalk.html)
- [MuseTalk 공식 저장소](https://github.com/TMElyralab/MuseTalk)
