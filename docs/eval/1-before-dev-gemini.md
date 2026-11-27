# 평가 결과: gemini

- 실행: 2026-11-27 12:14 UTC, 시나리오 14개 × 1회
- 모델: gemini-3.5-flash-lite

## 분류 (반복 평균, 괄호는 최소~최대)

| 지표 | 값 |
|---|---|
| 항목 재현율 | 77% |
| 항목 정밀도 | 81% |
| 근거 일치율 | 100% |
| 부위 정확도 | 100% |
| 위험 표시 재현율 | 100% |
| 식사량 정확도 | 100% |
| 기분 정확도 | 75% |
| 후속 확인 재현율 | 100% |
| 요약 근거율 (인계+보호자) | 100% |
| 시나리오당 분류 시간 | 중앙값 1.4초 |

## 틀린 개수 (모든 반복 합계)

| 종류 | 개수 |
|---|---|
| 정답에 없는 항목 | 4 |
| 부위 오탐 | 1 |
| 언급 없는 식사량 | 0 |
| 언급 없는 기분 | 1 |
| 답 없는 후속 확인에 답 | 0 |

## 알림 규칙

- 시나리오 10개 중 10개 일치

## 전사 글자 오류율 (say 음성)

| 시나리오 | CER |
|---|---|
| basic-knee-walk | 0.0% |
| blanket-not-pain | 4.2% |
| fall-risk | 0.0% |
| medication | 1.6% |
| back-pain-hand | 0.0% |

## 틀린 사례 (사람이 확인용)

- basic-knee-walk: 놓침 [observation] 점심|식사
- basic-knee-walk: 언급 없는 mood에 값 good
- blanket-not-pain: 놓침 [remark] 따뜻
- blanket-not-pain: 부위 오탐 knee ← 무릎 담요를 덮어 드림
- blanket-not-pain: 정답에 없는 항목 [observation] 어르신이 따뜻하다고 좋아하심
- followup-answers: 정답에 없는 항목 [observation] 무릎은 어제보다 조금 나아졌다고 함
- followup-none: mood None (정답 good)
- followup-none: 놓침 [remark] 고향
- medication: 놓침 [remark] 입맛
- short-record: 정답에 없는 항목 [observation] 특별한 일이 없었음
- shoulder-meal-none: 놓침 [remark] 어깨
- shoulder-meal-none: 정답에 없는 항목 [observation] 어깨가 결려서 팔을 올리기 힘들어 하심
