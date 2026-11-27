# ruff: noqa: E501  (보고서 문자열이 길다)
"""평가 실행기.

uv run python -m app.evaluation --provider local --repeat 3 --out ../docs/eval/local.md
uv run python -m app.evaluation --provider gemini --repeat 1 --stt
uv run python -m app.evaluation --provider fake           # 실행기 자체 확인용
"""

import argparse
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.ai.errors import AIError, TransientAIError
from app.ai.factory import build_ai, build_llm
from app.ai.postprocess import build_draft
from app.ai.summary import clean_summary, summarize, summarize_for_guardian
from app.ai.types import OpenFollowup, Segment, Transcript
from app.config import settings
from app.db import SessionLocal
from app.evaluation.alerts_eval import run_alert_scenarios
from app.evaluation.dataset import SCENARIOS, Scenario
from app.evaluation.metrics import Counts, cer, false_counts, score, summary_table
from app.masking import mask_transcript

_CATEGORY_KO = {"remark": "말씀", "observation": "관찰", "followup": "다음 확인"}


def _transcript(text: str) -> Transcript:
    """문장 단위 가상 구간 (근거 위치 계산용)"""
    sentences = [s for s in re.split(r"(?<=[.?!])\s+", text) if s]
    segments = [Segment(i * 3000, (i + 1) * 3000, s) for i, s in enumerate(sentences)]
    return mask_transcript(Transcript(text, segments, approximate_times=False))


def classify(classifier: Any, scenario: Scenario) -> tuple[dict[str, Any], float]:
    transcript = _transcript(scenario.transcript)
    followups = [OpenFollowup(f.ref, f.content, date(2026, 11, 20)) for f in scenario.followups]
    refs = {
        f.ref: {"item_id": f.ref, "content": f.content, "visited_on": "2026-11-20"}
        for f in scenario.followups
    }
    started = time.monotonic()
    out = classifier.classify(transcript, followups)
    return build_draft(transcript, out, refs), time.monotonic() - started


def grounded(llm: Any, draft: dict[str, Any]) -> tuple[int, int]:
    """확정 항목처럼 넘겨 인계·보호자 요약을 만들고, 실제 근거 번호를 단 문장 수를 센다."""
    items = draft["items"]
    if len(items) < 2:
        return 0, 0
    refs = {f"I{n}": n for n in range(1, len(items) + 1)}
    kept = total = 0
    handover = [
        f"I{n}. [2026-11-27] [{_CATEGORY_KO[i['category']]}] {i['content']}"
        for n, i in enumerate(items, 1)
    ]
    guardian = [
        f"I{n}. [{_CATEGORY_KO[i['category']]}] {i['content']}" for n, i in enumerate(items, 1)
    ]
    for out, limit in ((summarize(llm, handover), 5), (summarize_for_guardian(llm, guardian), 3)):
        total += len(out.sentences[:limit])
        kept += len(clean_summary(out, refs, limit=limit))
    return kept, total


def stt_cer(
    transcriber: Any, scenarios: list[Scenario], pace: float, errors: list[str]
) -> list[tuple[str, float]]:
    """macOS say로 읽힌 가상 음성의 글자 오류율"""
    if not (shutil.which("say") and shutil.which("afconvert")):
        return []
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in scenarios:
            aiff, wav = Path(tmp) / f"{s.id}.aiff", Path(tmp) / f"{s.id}.wav"
            subprocess.run(["say", "-v", "Yuna", "-o", str(aiff), s.transcript], check=True)
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=True
            )
            try:
                hyp = _retrying(lambda w=wav: transcriber.transcribe(w).text, pace)
            except AIError as e:
                errors.append(f"stt:{e.code}")
                continue
            rows.append((s.id, cer(s.transcript, hyp)))
    return rows


def _retrying[T](call: Callable[[], T], pace: float) -> T:
    """무료 등급의 429·503은 잠시 기다렸다가 두 번까지 다시 시도한다."""
    for attempt in range(3):
        time.sleep(pace)
        try:
            return call()
        except TransientAIError:
            if attempt == 2:
                raise
            time.sleep(20 * (attempt + 1))
    raise AssertionError("unreachable")


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


def report(provider: str, runs: list[tuple[Counts, list[float], tuple[int, int]]],
           alerts: list[Any], stt: list[tuple[str, float]], errors: list[str]) -> str:  # fmt: skip
    lines = [
        f"# 평가 결과: {provider}",
        "",
        f"- 실행: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC, 시나리오 {len(SCENARIOS)}개 × {len(runs)}회",
        f"- 모델: {settings.ollama_model if provider == 'local' else settings.gemini_model if provider == 'gemini' else 'fake'}",
        "",
        "## 분류 (반복 평균, 괄호는 최소~최대)",
        "",
        "| 지표 | 값 |",
        "|---|---|",
    ]
    tables = [summary_table(c) for c, _, _ in runs]
    for key in tables[0]:
        values = [v for t in tables if (v := t[key]) is not None]
        if not values:
            continue
        mean = statistics.mean(values)
        spread = f" ({_pct(min(values))}~{_pct(max(values))})" if len(values) > 1 else ""
        lines.append(f"| {key} | {_pct(mean)}{spread} |")
    grounded_kept = sum(g[0] for _, _, g in runs)
    grounded_total = sum(g[1] for _, _, g in runs)
    lines.append(
        f"| 요약 근거율 (인계+보호자) | {_pct(grounded_kept / grounded_total if grounded_total else None)} |"
    )
    latencies = [x for _, lat, _ in runs for x in lat]
    if latencies:
        lines.append(f"| 시나리오당 분류 시간 | 중앙값 {statistics.median(latencies):.1f}초 |")
    lines += ["", "## 틀린 개수 (모든 반복 합계)", "", "| 종류 | 개수 |", "|---|---|"]
    total = Counts()
    for c, _, _ in runs:
        total.add(c)
    lines += [f"| {k} | {v} |" for k, v in false_counts(total).items()]
    if errors:
        lines += [
            "",
            f"AI 오류로 건너뛴 시나리오: {len(errors)}건 ({', '.join(sorted(set(errors)))})",
        ]
    lines += [
        "",
        "## 알림 규칙",
        "",
        f"- 시나리오 {len(alerts)}개 중 {sum(a.ok for a in alerts)}개 일치",
    ]
    lines += [
        f"  - 불일치: {a.scenario.id} 기대 {set(a.scenario.expected)} / 실제 {set(a.got)}"
        for a in alerts
        if not a.ok
    ]
    if stt:
        lines += ["", "## 전사 글자 오류율 (say 음성)", "", "| 시나리오 | CER |", "|---|---|"]
        lines += [f"| {sid} | {v * 100:.1f}% |" for sid, v in stt]
    if total.misses:
        lines += ["", "## 틀린 사례 (사람이 확인용)", ""]
        lines += [f"- {m}" for m in sorted(set(total.misses))]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="돌봄수첩 가상 시나리오 평가")
    parser.add_argument("--provider", choices=["fake", "local", "gemini"], default="fake")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--stt", action="store_true", help="say 음성으로 전사 오류율도 잰다 (macOS)"
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--pace", type=float, default=0.0, help="AI 호출 사이 대기(초). 무료 등급 분당 한도용"
    )
    args = parser.parse_args()

    settings.ai_provider = args.provider
    transcriber, classifier = build_ai()
    llm = build_llm()
    runs, errors = [], []
    for n in range(args.repeat):
        counts, latencies, kept, total = Counts(), [], 0, 0
        for scenario in SCENARIOS:
            try:
                draft, elapsed = _retrying(lambda sc=scenario: classify(classifier, sc), args.pace)
                g = _retrying(lambda d=draft: grounded(llm, d), args.pace)
            except AIError as e:  # 무료 등급 503 등은 건너뛰고 따로 센다
                errors.append(e.code)
                continue
            counts.add(score(scenario, draft))
            latencies.append(elapsed)
            kept, total = kept + g[0], total + g[1]
            print(f"[{n + 1}/{args.repeat}] {scenario.id} {elapsed:.1f}s", flush=True)
        runs.append((counts, latencies, (kept, total)))
    with SessionLocal() as db:
        alerts = run_alert_scenarios(db)
    stt = stt_cer(transcriber, list(SCENARIOS[:5]), args.pace, errors) if args.stt else []
    text = report(args.provider, runs, alerts, stt, errors)
    print(text)
    if args.out:
        args.out.write_text(text)


if __name__ == "__main__":
    main()
