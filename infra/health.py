"""Health check для бота.

Проверка статуса, uptime, базовые метрики.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class HealthStatus:
    """Статус здоровья бота."""
    status: str  # "healthy", "degraded", "unhealthy"
    uptime_seconds: float
    started_at: str
    version: str = "1.0.0"
    checks: dict[str, bool] = None
    metrics: dict[str, Any] = None

    def __post_init__(self):
        if self.checks is None:
            self.checks = {}
        if self.metrics is None:
            self.metrics = {}

    def to_dict(self) -> dict[str, Any]:
        """Конвертировать в dict."""
        return {
            "status": self.status,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "uptime_human": _format_uptime(self.uptime_seconds),
            "started_at": self.started_at,
            "version": self.version,
            "checks": self.checks,
            "metrics": self.metrics,
        }

    def to_text(self) -> str:
        """Конвертировать в текст для Telegram."""
        lines = [
            f"🤖 **Bot Status: {self.status.upper()}**",
            "",
            f"⏱ **Uptime:** {_format_uptime(self.uptime_seconds)}",
            f"🕐 **Started:** {self.started_at}",
            f"📦 **Version:** {self.version}",
            "",
            "**Checks:**",
        ]

        for check_name, passed in self.checks.items():
            icon = "✅" if passed else "❌"
            lines.append(f"  {icon} {check_name}")

        if self.metrics:
            lines.append("")
            lines.append("**Metrics:**")
            for key, value in self.metrics.items():
                lines.append(f"  • {key}: {value}")

        return "\n".join(lines)


class HealthChecker:
    """Проверка здоровья бота."""

    def __init__(self) -> None:
        self._start_time = time.time()
        self._start_datetime = datetime.now(timezone.utc)
        self._checks: dict[str, callable] = {}
        self._metrics: dict[str, callable] = {}

        # Register default checks
        self.register_check("env_loaded", self._check_env)
        self.register_metric("uptime", self._get_uptime)

    def register_check(self, name: str, func: callable) -> None:
        """Зарегистрировать проверку.

        Args:
            name: Имя проверки
            func: Функция возвращающая bool
        """
        self._checks[name] = func

    def register_metric(self, name: str, func: callable) -> None:
        """Зарегистрировать метрику.

        Args:
            name: Имя метрики
            func: Функция возвращающая значение
        """
        self._metrics[name] = func

    def get_status(self) -> HealthStatus:
        """Получить текущий статус.

        Returns:
            HealthStatus с результатами проверок
        """
        uptime = time.time() - self._start_time

        # Выполнить проверки
        checks = {}
        failed_count = 0
        for name, func in self._checks.items():
            try:
                result = func()
                checks[name] = result
                if not result:
                    failed_count += 1
            except Exception:
                checks[name] = False
                failed_count += 1

        # Выполнить метрики
        metrics = {}
        for name, func in self._metrics.items():
            try:
                metrics[name] = func()
            except Exception:
                metrics[name] = "error"

        # Определить общий статус
        if failed_count == 0:
            status = "healthy"
        elif failed_count <= len(self._checks) // 2:
            status = "degraded"
        else:
            status = "unhealthy"

        return HealthStatus(
            status=status,
            uptime_seconds=uptime,
            started_at=self._start_datetime.isoformat(),
            checks=checks,
            metrics=metrics,
        )

    def _check_env(self) -> bool:
        """Проверка загрузки окружения."""
        return True  # Если запустились, значит env загружен

    def _get_uptime(self) -> str:
        """Получить uptime в человеко-читаемом формате."""
        return _format_uptime(time.time() - self._start_time)


def _format_uptime(seconds: float) -> str:
    """Форматировать uptime в человеко-читаемый вид.

    Args:
        seconds: Количество секунд

    Returns:
        Строка вида "1d 2h 3m 4s"
    """
    seconds = int(seconds)

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


# Глобальный instance
_health_checker: HealthChecker | None = None


def get_health_checker() -> HealthChecker:
    """Получить глобальный health checker."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


def get_uptime() -> float:
    """Получить uptime в секундах."""
    return time.time() - get_health_checker()._start_time
