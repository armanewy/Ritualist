from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from ritualist.paths import app_data_path

MAX_THUMBNAIL_WIDTH = 512
MAX_THUMBNAIL_HEIGHT = 288
FALLBACK_GRADIENT = ("#2a3848", "#10151e")

Thumbnailer = Callable[[Path, Path, tuple[int, int]], None]


@dataclass(frozen=True)
class CachedThumbnail:
    source_path: Path | None
    thumbnail_path: Path | None
    thumbnail_url: str
    fallback_gradient: tuple[str, str] = FALLBACK_GRADIENT
    cache_hit: bool = False
    missing_source: bool = False

    @property
    def uses_fallback(self) -> bool:
        return self.thumbnail_url == ""


class HomeThumbnailCache:
    """Local thumbnail cache for Home card images.

    `cached_thumbnail` is safe for already-prepared UI payloads because it only
    returns an existing cached file URL or a fast fallback. `ensure_thumbnail`
    may decode and scale the source image, so callers should run it from a
    background worker or setup path instead of a GUI signal handler.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        max_width: int = MAX_THUMBNAIL_WIDTH,
        max_height: int = MAX_THUMBNAIL_HEIGHT,
        thumbnailer: Thumbnailer | None = None,
    ) -> None:
        if max_width <= 0 or max_height <= 0:
            raise ValueError("thumbnail dimensions must be positive")
        self.cache_dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        self.max_size = (max_width, max_height)
        self._thumbnailer = thumbnailer or _qt_thumbnailer

    def thumbnail_path_for(self, source_path: str | Path) -> Path:
        source = Path(source_path)
        stat = source.stat()
        key = _thumbnail_key(source, stat.st_size, stat.st_mtime_ns, self.max_size)
        return self.cache_dir / f"{key}-{self.max_size[0]}x{self.max_size[1]}.png"

    def cached_thumbnail(self, source_path: str | Path | None) -> CachedThumbnail:
        source = _coerce_source(source_path)
        if source is None:
            return _fallback(missing_source=True)

        try:
            target = self.thumbnail_path_for(source)
        except OSError:
            return _fallback(source_path=source, missing_source=True)

        if target.is_file():
            return CachedThumbnail(
                source_path=source,
                thumbnail_path=target,
                thumbnail_url=target.resolve().as_uri(),
                cache_hit=True,
            )
        return CachedThumbnail(source_path=source, thumbnail_path=target, thumbnail_url="")

    def ensure_thumbnail(self, source_path: str | Path | None) -> CachedThumbnail:
        asset = self.cached_thumbnail(source_path)
        if asset.thumbnail_url or asset.thumbnail_path is None or asset.source_path is None:
            return asset

        try:
            asset.thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            self._thumbnailer(asset.source_path, asset.thumbnail_path, self.max_size)
        except (ImportError, OSError, ValueError):
            return CachedThumbnail(
                source_path=asset.source_path,
                thumbnail_path=asset.thumbnail_path,
                thumbnail_url="",
            )

        if not asset.thumbnail_path.is_file():
            return CachedThumbnail(
                source_path=asset.source_path,
                thumbnail_path=asset.thumbnail_path,
                thumbnail_url="",
            )
        return CachedThumbnail(
            source_path=asset.source_path,
            thumbnail_path=asset.thumbnail_path,
            thumbnail_url=asset.thumbnail_path.resolve().as_uri(),
            cache_hit=True,
        )


def _default_cache_dir() -> Path:
    return app_data_path() / "home-thumbnails"


def _coerce_source(source_path: str | Path | None) -> Path | None:
    if source_path is None:
        return None
    raw = str(source_path).strip()
    if not raw:
        return None
    return Path(raw)


def _thumbnail_key(source: Path, size: int, mtime_ns: int, max_size: tuple[int, int]) -> str:
    resolved = str(source.resolve(strict=False))
    payload = f"{resolved}\0{size}\0{mtime_ns}\0{max_size[0]}x{max_size[1]}".encode("utf-8")
    return sha256(payload).hexdigest()[:24]


def _fallback(
    *,
    source_path: Path | None = None,
    missing_source: bool,
) -> CachedThumbnail:
    return CachedThumbnail(
        source_path=source_path,
        thumbnail_path=None,
        thumbnail_url="",
        missing_source=missing_source,
    )


def _qt_thumbnailer(source_path: Path, target_path: Path, max_size: tuple[int, int]) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    image = QImage(str(source_path))
    if image.isNull():
        raise ValueError(f"could not load image: {source_path}")

    scaled = image.scaled(
        max_size[0],
        max_size[1],
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    with NamedTemporaryFile(
        prefix=f"{target_path.stem}-",
        suffix=".png",
        dir=target_path.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        if not scaled.save(str(temp_path), "PNG"):
            raise OSError(f"could not write thumbnail: {target_path}")
        temp_path.replace(target_path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
