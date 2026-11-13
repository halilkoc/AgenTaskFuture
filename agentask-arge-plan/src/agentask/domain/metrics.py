"""Run metrikleri: iş başarısı ile teknik toparlanma ayrı sayılır (docs/07 Metrikler)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from agentask.domain.runtime import Run, RunStatus


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(p * (len(ordered) - 1))))
    return ordered[index]


def run_metrics(runs: list[Run]) -> dict[str, Any]:
    by_status = Counter(r.status.value for r in runs)
    completed = [r for r in runs if r.status is RunStatus.COMPLETED]
    recoveries = Counter(x for r in runs for s in r.steps for x in s.recoveries)
    errors = Counter(
        s.error_class for r in runs for s in r.steps if s.error_class and s.state.value == "known_failed"
    )
    durations = [
        (r.updated_at - r.created_at).total_seconds()
        for r in runs
        if r.is_terminal or r.status in {RunStatus.OUTCOME_UNKNOWN}
    ]
    by_op: dict[str, Counter[str]] = {}
    for r in runs:
        op = (r.binding or {}).get("operation_id")
        if op:
            by_op.setdefault(op, Counter())[r.status.value] += 1
    terminal = [r for r in runs if r.is_terminal or r.status is RunStatus.OUTCOME_UNKNOWN]
    return {
        "total": len(runs),
        "by_status": dict(by_status),
        "business_success_rate": round(len(completed) / len(terminal), 3) if terminal else None,
        "completed_with_technical_recovery": sum(1 for r in completed if any(s.recoveries for s in r.steps)),
        "outcome_unknown": by_status.get("outcome_unknown", 0),
        "recoveries": dict(recoveries),
        "error_classes": dict(errors),
        "duration_seconds": {"p50": _percentile(durations, 0.5), "p95": _percentile(durations, 0.95)},
        "by_operation": {k: dict(v) for k, v in by_op.items()},
    }
