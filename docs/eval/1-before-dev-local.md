# 평가 결과: local

- 실행: 2026-11-27 12:30 UTC, 시나리오 14개 × 3회
- 모델: qwen2.5:7b

## 분류 (반복 평균, 괄호는 최소~최대)

| 지표 | 값 |
|---|---|
| 항목 재현율 | 64% (64%~64%) |
| 항목 정밀도 | 100% (100%~100%) |
| 근거 일치율 | 100% (100%~100%) |
| 부위 정확도 | 100% (100%~100%) |
| 위험 표시 재현율 | 50% (50%~50%) |
| 식사량 정확도 | 83% (83%~83%) |
| 기분 정확도 | 75% (75%~75%) |
| 후속 확인 재현율 | 100% (100%~100%) |
| 요약 근거율 (인계+보호자) | 100% |
| 시나리오당 분류 시간 | 중앙값 19.8초 |

## 틀린 개수 (모든 반복 합계)

| 종류 | 개수 |
|---|---|
| 정답에 없는 항목 | 0 |
| 부위 오탐 | 3 |
| 언급 없는 식사량 | 0 |
| 언급 없는 기분 | 9 |
| 답 없는 후속 확인에 답 | 3 |

## 알림 규칙

- 시나리오 10개 중 10개 일치

## 전사 글자 오류율 (say 음성)

| 시나리오 | CER |
|---|---|
| basic-knee-walk | 0.0% |
| blanket-not-pain | 0.0% |
| fall-risk | 0.0% |
| medication | 0.0% |
| back-pain-hand | 0.0% |

## 틀린 사례 (사람이 확인용)

- back-pain-hand: 놓침 [remark] 손
- back-pain-hand: 언급 없는 mood에 값 low
- basic-knee-walk: 놓침 [observation] 점심|식사
- basic-knee-walk: 놓침 [remark] 산책
- blanket-not-pain: meal None (정답 4)
- blanket-not-pain: 놓침 [observation] 담요
- blanket-not-pain: 부위 오탐 knee ← 날이 추워서 무릎 담요를 덮어 드렸어요. 어르신이 따뜻하다고 좋아하셨어요. 저녁은 다 드셨고 기분도 좋아 보이셨어요.
- fall-risk: 언급 없는 mood에 값 low
- family-request: 놓침 [followup] 병원
- followup-none: mood None (정답 good)
- followup-none: 답이 없는 F1에 답을 만듦
- medication: 놓침 [observation] 혈압약|약
- medication: 놓침 [remark] 입맛
- mood-good-no-items-risk: 놓침 [observation] 노래|기분
- uncertain-speaker: 언급 없는 mood에 값 neutral
