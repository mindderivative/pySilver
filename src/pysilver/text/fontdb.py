"""Font registry and the fallback chain.

Fallback resolves **per grapheme cluster, not per codepoint** (ARCHITECTURE.md
5.7.2). Splitting a cluster across two faces produces visibly broken output for
combining marks and ZWJ sequences: the base character renders from one font and
its marks from another, positioned by the wrong metrics.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..assets import DEFAULT_FONT, FALLBACK_CHAIN, MEDIUM_FONT
from .font import Face

__all__ = ["FontDB", "FontRequest"]


@dataclass(frozen=True, slots=True)
class FontRequest:
    """What a widget asks for. Resolved against the registry."""

    family: str = "Roboto"
    weight: int = 400

    def key(self) -> tuple[str, int]:
        return (self.family.lower(), self.weight)


class FontDB:
    """Owns loaded faces and resolves text to the face that can render it."""

    __slots__ = ("_by_key", "_chain", "_faces", "_resolve_cache")

    def __init__(self, *, load_defaults: bool = True) -> None:
        self._faces: dict[Path, Face] = {}
        self._by_key: dict[tuple[str, int], Face] = {}
        self._chain: list[Face] = []
        self._resolve_cache: dict[tuple[str, tuple[str, int]], Face] = {}
        if load_defaults:
            self.load_defaults()

    # ------------------------------------------------------------- loading

    def load(self, path: str | Path, *, fallback: bool = False) -> Face:
        """Load a face (or return the already-loaded one)."""
        resolved = Path(path).resolve()
        face = self._faces.get(resolved)
        if face is None:
            face = Face(resolved)
            self._faces[resolved] = face
            self._by_key[(face.family.lower(), face.weight)] = face
            self._resolve_cache.clear()
        if fallback and face not in self._chain:
            self._chain.append(face)
            self._resolve_cache.clear()
        return face

    def load_defaults(self) -> None:
        """Load the bundled M3 stack: Roboto, then Noto Sans as fallback."""
        self.load(DEFAULT_FONT)
        self.load(MEDIUM_FONT)
        for path in FALLBACK_CHAIN:
            self.load(path, fallback=True)

    @property
    def faces(self) -> Sequence[Face]:
        return tuple(self._faces.values())

    @property
    def fallback_chain(self) -> Sequence[Face]:
        return tuple(self._chain)

    # ------------------------------------------------------------ resolving

    def face_for(self, request: FontRequest) -> Face:
        """The primary face for a request, ignoring coverage."""
        key = request.key()
        face = self._by_key.get(key)
        if face is not None:
            return face
        # Nearest weight within the family before giving up on it entirely.
        candidates = [f for f in self._faces.values() if f.family.lower() == request.family.lower()]
        if candidates:
            return min(candidates, key=lambda f: abs(f.weight - request.weight))
        if not self._chain:
            raise LookupError(f"no font available for {request}")
        return self._chain[0]

    def resolve(self, cluster: str, request: FontRequest) -> Face:
        """The first face covering every codepoint in *cluster*.

        Falls back through the chain, then returns the primary face so the
        result is ``.notdef`` -- a visible missing-glyph box rather than a
        silent gap.
        """
        cache_key = (cluster, request.key())
        hit = self._resolve_cache.get(cache_key)
        if hit is not None:
            return hit

        primary = self.face_for(request)
        chosen = primary
        if not primary.covers_all(cluster):
            for face in self._chain:
                if face is not primary and face.covers_all(cluster):
                    chosen = face
                    break
        self._resolve_cache[cache_key] = chosen
        return chosen

    def coverage_report(self, text: str, request: FontRequest | None = None) -> dict[str, str]:
        """Which face would render each distinct character. A debugging aid."""
        req = request or FontRequest()
        return {c: self.resolve(c, req).family for c in dict.fromkeys(text)}

    def missing(self, text: str, request: FontRequest | None = None) -> Iterable[str]:
        """Characters no face in the chain can render."""
        req = request or FontRequest()
        for char in dict.fromkeys(text):
            if not self.resolve(char, req).covers_all(char):
                yield char
