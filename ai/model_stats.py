from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from infra.json_atomic import atomic_write_json


@dataclass(slots=True)
class ModelPerformance:
    attempts: int = 0
    response_success_rate: float = 0.0
    incomplete_response_rate: float = 0.0
    refusal_rate: float = 0.0
    average_response_length: float = 0.0
    response_latency: float = 0.0


@dataclass(slots=True)
class ModelStatRecord:
    overall: ModelPerformance = field(default_factory=ModelPerformance)
    tasks: dict[str, ModelPerformance] = field(default_factory=dict)


class ModelStatsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._stats: dict[str, ModelStatRecord] = {}

    async def load(self) -> dict[str, ModelStatRecord]:
        async with self._lock:
            if not self._path.exists():
                await self._write_locked()
                return copy.deepcopy(self._stats)

            try:
                raw = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
                payload = json.loads(raw or "{}")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                payload = {}

            self._stats = {
                str(model): self._record_from_dict(item)
                for model, item in (payload or {}).items()
                if isinstance(item, dict)
            }
            await self._write_locked()
            return copy.deepcopy(self._stats)

    async def record_result(
        self,
        *,
        model: str,
        task_type: str,
        success: bool,
        incomplete: bool,
        refusal: bool,
        response_length: int,
        latency_ms: float,
    ) -> None:
        async with self._lock:
            record = self._stats.setdefault(model, ModelStatRecord())
            overall = record.overall
            task = record.tasks.setdefault(task_type, ModelPerformance())
            _update_performance(
                overall,
                success=success,
                incomplete=incomplete,
                refusal=refusal,
                response_length=response_length,
                latency_ms=latency_ms,
            )
            _update_performance(
                task,
                success=success,
                incomplete=incomplete,
                refusal=refusal,
                response_length=response_length,
                latency_ms=latency_ms,
            )
            await self._write_locked()

    async def rank_models(self, models: list[str], task_type: str) -> list[str]:
        async with self._lock:
            return sorted(
                models,
                key=lambda name: self._score_model(name, task_type),
                reverse=True,
            )

    async def get_snapshot(self) -> dict[str, ModelStatRecord]:
        async with self._lock:
            return copy.deepcopy(self._stats)

    def _score_model(
        self, model: str, task_type: str
    ) -> tuple[float, float, float, float]:
        record = self._stats.get(model)
        if record is None:
            return (0.0, 0.0, 0.0, 0.0)
        task = record.tasks.get(task_type, record.overall)
        attempts_bonus = min(task.attempts, 50) / 50.0
        speed_bonus = max(0.0, 1.0 - min(task.response_latency, 8000.0) / 8000.0)
        return (
            task.response_success_rate
            - (task.incomplete_response_rate * 0.6)
            - (task.refusal_rate * 0.8),
            attempts_bonus,
            speed_bonus,
            task.average_response_length,
        )

    def _record_from_dict(self, data: dict) -> ModelStatRecord:
        return ModelStatRecord(
            overall=_performance_from_dict(data.get("overall") or {}),
            tasks={
                str(task_type): _performance_from_dict(item)
                for task_type, item in (data.get("tasks") or {}).items()
                if isinstance(item, dict)
            },
        )

    async def _write_locked(self) -> None:
        await atomic_write_json(
            self._path,
            {model: asdict(record) for model, record in self._stats.items()},
            indent=2,
        )


def _update_performance(
    performance: ModelPerformance,
    *,
    success: bool,
    incomplete: bool,
    refusal: bool,
    response_length: int,
    latency_ms: float,
) -> None:
    performance.attempts += 1
    attempts = float(performance.attempts)
    performance.response_success_rate = performance.response_success_rate + (
        ((1.0 if success else 0.0) - performance.response_success_rate) / attempts
    )
    performance.incomplete_response_rate = performance.incomplete_response_rate + (
        ((1.0 if incomplete else 0.0) - performance.incomplete_response_rate) / attempts
    )
    performance.refusal_rate = performance.refusal_rate + (
        ((1.0 if refusal else 0.0) - performance.refusal_rate) / attempts
    )
    performance.average_response_length = performance.average_response_length + (
        (max(0.0, float(response_length)) - performance.average_response_length)
        / attempts
    )
    performance.response_latency = performance.response_latency + (
        (max(0.0, float(latency_ms)) - performance.response_latency) / attempts
    )


def _performance_from_dict(data: dict) -> ModelPerformance:
    return ModelPerformance(
        attempts=int(data.get("attempts", 0)),
        response_success_rate=float(data.get("response_success_rate", 0.0)),
        incomplete_response_rate=float(data.get("incomplete_response_rate", 0.0)),
        refusal_rate=float(data.get("refusal_rate", 0.0)),
        average_response_length=float(data.get("average_response_length", 0.0)),
        response_latency=float(data.get("response_latency", 0.0)),
    )
