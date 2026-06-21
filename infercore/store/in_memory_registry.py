from typing import Generic, TypeVar

T = TypeVar("T")


class InMemoryRegistry(Generic[T]):
    def __init__(self):
        self._items: dict[str, T] = {}

    def put(self, key: str, value: T) -> None:
        self._items[key] = value

    def get(self, key: str) -> T | None:
        return self._items.get(key)

    def remove(self, key: str):
        self._items.pop(key)

    def all(self) -> dict[str, T]:
        return self._items.copy()
