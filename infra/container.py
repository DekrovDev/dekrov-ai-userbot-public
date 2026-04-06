"""Ручной DI-контейнер.

Поддерживает:
- Singleton (один экземпляр на приложение)
- Transient (новый экземпляр при каждом запросе)
- Ленивая инициализация
- Строковые ключи для простых значений (например, config)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type, TypeVar, Union

T = TypeVar("T")

ServiceKey = Union[Type, str]


@dataclass
class ServiceDescriptor:
    """Описание сервиса в контейнере."""

    service_type: ServiceKey
    factory: Callable[[Container], Any]
    singleton: bool = True
    instance: Any = None


class Container:
    """Ручной DI-контейнер."""

    def __init__(self) -> None:
        self._services: dict[ServiceKey, ServiceDescriptor] = {}
        self._initialized = False

    def register_singleton(
        self,
        service_type: ServiceKey,
        factory: Callable[[Container], Any],
    ) -> None:
        """Зарегистрировать singleton-сервис."""
        self._services[service_type] = ServiceDescriptor(
            service_type=service_type,
            factory=factory,
            singleton=True,
        )

    def register_transient(
        self,
        service_type: ServiceKey,
        factory: Callable[[Container], Any],
    ) -> None:
        """Зарегистрировать transient-сервис."""
        self._services[service_type] = ServiceDescriptor(
            service_type=service_type,
            factory=factory,
            singleton=False,
        )

    def resolve(self, service_type: ServiceKey) -> Any:
        """Получить экземпляр сервиса."""
        descriptor = self._services.get(service_type)
        if descriptor is None:
            raise KeyError(f"Service {service_type} not registered")

        # Singleton: вернуть кэшированный экземпляр
        if descriptor.singleton and descriptor.instance is not None:
            return descriptor.instance

        # Создать новый экземпляр
        instance = descriptor.factory(self)

        # Singleton: закэшировать
        if descriptor.singleton:
            descriptor.instance = instance

        return instance

    def initialize(self) -> None:
        """Инициализировать все singleton-сервисы."""
        if self._initialized:
            return

        for descriptor in self._services.values():
            if descriptor.singleton:
                descriptor.instance = descriptor.factory(self)

        self._initialized = True

    async def load_all(self) -> None:
        """Вызвать load() на всех сервисах с этим методом."""
        for descriptor in self._services.values():
            instance = descriptor.instance
            if instance and hasattr(instance, "load"):
                await instance.load()

    def get_service(self, service_type: ServiceKey) -> Any | None:
        """Получить сервис без ошибки если не зарегистрирован."""
        descriptor = self._services.get(service_type)
        if descriptor is None:
            return None
        if descriptor.singleton and descriptor.instance is not None:
            return descriptor.instance
        return descriptor.factory(self) if not descriptor.singleton else None
