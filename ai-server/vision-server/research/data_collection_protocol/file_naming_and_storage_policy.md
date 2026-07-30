# 파일명 및 저장 정책

허용 예시는 `PTC_000001_SES_000001_ANS_000001.mp4`다. 파일명은 가명
participant, session, answer ID만 포함하고 이름, 이메일, 전화번호, 생년월일,
회사명, 주민등록번호를 포함하지 않는다.

경로는 `data/pilot/incoming`, `validated`, `excluded`, `withdrawn` 중 하나의
상대 경로로 기록한다. 실제 파일 대신 file reference, SHA-256, byte 크기,
생성 시각, participant/session/answer/consent reference를 manifest에 기록한다.
경로 traversal과 절대 경로는 금지한다. 실제 보존 기간·암호화·삭제는 pilot
승인 전에 별도 정책으로 확정한다.
