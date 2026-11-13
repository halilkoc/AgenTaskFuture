"""Frame ağacı kayıtları: runtime ref, epoch (yönlenme sayacı) ve lineage tabanlı geçersizleştirme.

Frame sırası veya HTML id kullanılmaz. Anahtar, adapterin verdiği opak runtime nesnesidir; ref yalnız oturum
süresince geçerlidir ve kalıcı kataloğa yazılmaz.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass

Lineage = tuple[tuple[str, int], ...]


@dataclass(slots=True)
class FrameInfo:
    ref: str
    parent_ref: str | None
    epoch: int = 0


class FrameRegistry:
    def __init__(self) -> None:
        self._by_key: dict[Hashable, FrameInfo] = {}
        self._by_ref: dict[str, FrameInfo] = {}
        self._key_of: dict[str, Hashable] = {}
        self._counter = 0
        self.tree_revision = 0

    def attach(self, key: Hashable, parent_key: Hashable | None) -> FrameInfo:
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        parent = self._by_key.get(parent_key) if parent_key is not None else None
        self._counter += 1
        info = FrameInfo(ref=f"f{self._counter}", parent_ref=parent.ref if parent else None)
        self._by_key[key] = info
        self._by_ref[info.ref] = info
        self._key_of[info.ref] = key
        self.tree_revision += 1
        return info

    def navigated(self, key: Hashable) -> None:
        info = self._by_key.get(key)
        if info is None:
            return
        # Epoch artışı lineage üzerinden bu frame'in ve bütün alt ağacının eski gözlemlerini geçersiz kılar.
        info.epoch += 1
        self.tree_revision += 1

    def detached(self, key: Hashable) -> None:
        info = self._by_key.get(key)
        if info is None:
            return
        for ref in [info.ref, *self._descendants(info.ref)]:
            self._by_ref.pop(ref, None)
            self._by_key.pop(self._key_of.pop(ref), None)
        self.tree_revision += 1

    def _descendants(self, ref: str) -> list[str]:
        result: list[str] = []
        stack = [ref]
        while stack:
            current = stack.pop()
            children = [i.ref for i in self._by_ref.values() if i.parent_ref == current]
            result += children
            stack += children
        return result

    def info(self, ref: str) -> FrameInfo | None:
        return self._by_ref.get(ref)

    def ref_for(self, key: Hashable) -> str | None:
        info = self._by_key.get(key)
        return info.ref if info else None

    def lineage(self, ref: str) -> Lineage:
        chain: list[tuple[str, int]] = []
        current = self._by_ref.get(ref)
        while current is not None:
            chain.append((current.ref, current.epoch))
            current = self._by_ref.get(current.parent_ref) if current.parent_ref else None
        return tuple(reversed(chain))

    def depth(self, ref: str) -> int:
        return len(self.lineage(ref)) - 1

    def is_current(self, lineage: Lineage) -> bool:
        for ref, epoch in lineage:
            info = self._by_ref.get(ref)
            if info is None or info.epoch != epoch:
                return False
        return bool(lineage)
