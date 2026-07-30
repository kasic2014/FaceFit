# 평가자 workflow

Rater A와 Rater B는 같은 rubric 교육을 받은 뒤 독립적으로 원본 라벨을 만든다.
원본 작업 중 Stage 10 metric 값, Stage 11 fixture 결과, 다른 평가자의 라벨,
참여자 직접 식별정보를 볼 수 없어야 한다.

두 원본 레이어는 수정·병합하지 않고 보존한다. 일치도 계산 뒤 필요한 경우
별도 adjudicator가 `ADJUDICATED_RESULT` 레이어를 만든다. adjudication은
원본을 대체하지 않는다.

Temporal IoU, observed/positive/negative agreement와 Cohen's kappa는 라벨링
절차의 재현성 점검용이다. 이번 단계는 승인 cutoff나 성능 합격 기준을 정하지
않으며, 분모가 0이면 값을 `null`로 보존한다.
