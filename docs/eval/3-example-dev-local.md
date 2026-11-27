# 평가 결과: local

- 실행: 2026-11-27 17:35 UTC, 시나리오 14개(dev) × 1회
- 모델: qwen2.5:7b

## 분류 (반복 평균, 괄호는 최소~최대)

| 지표 | 값 |
|---|---|
| 항목 재현율 | 68% |
| 항목 정밀도 | 79% |
| 근거 일치율 | 97% |
| 부위 정확도 | 75% |
| 위험 표시 재현율 | 100% |
| 식사량 정확도 | 100% |
| 기분 정확도 | 100% |
| 후속 확인 재현율 | 100% |
| 요약 근거율 (인계+보호자) | 100% |
| 시나리오당 분류 시간 | 중앙값 11.7초 |

## 틀린 개수 (모든 반복 합계)

| 종류 | 개수 |
|---|---|
| 정답에 없는 항목 | 4 |
| 부위 오탐 | 1 |
| 언급 없는 식사량 | 0 |
| 언급 없는 기분 | 0 |
| 답 없는 후속 확인에 답 | 0 |

## 알림 규칙

- 시나리오 10개 중 10개 일치

## 틀린 사례 (사람이 확인용)

- back-pain-hand: 놓침 [remark] 손
- basic-knee-walk: 놓침 [remark] 산책
- basic-knee-walk: 정답에 없는 항목 [observation] 날 좋으면 산책 나가고 싶다고 하셨어요
- blanket-not-pain: 부위 오탐 knee ← 날이 추워 무릎 담요를 덮어 드렸어요
- fall-risk: 정답에 없는 항목 [remark] 욕실 미끄럼 방지 매트가 필요해 보여요
- followup-answers: 정답에 없는 항목 [observation] 무릎은 어제보다 조금 나아졌다고 하심
- followup-none: 놓침 [remark] 고향
- foot-swelling-followup: 부위 back (정답 foot)
- medication: 놓침 [observation] 혈압약|약
- medication: 놓침 [remark] 입맛
- mood-good-no-items-risk: 놓침 [observation] 노래|기분
- short-record: 놓침 [observation] 식사
- short-record: 정답에 없는 항목 [remark] 특별한 일은 없었고 식사는 거의 못 하셨어요
