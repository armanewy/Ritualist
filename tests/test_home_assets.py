from __future__ import annotations

from pathlib import Path

from ritualist.home.assets import (
    FALLBACK_GRADIENT,
    MAX_THUMBNAIL_HEIGHT,
    MAX_THUMBNAIL_WIDTH,
    HomeThumbnailCache,
)


def test_thumbnail_path_generation_is_stable(tmp_path: Path) -> None:
    source = tmp_path / "source-card-art.png"
    source.write_bytes(b"not a real image, only a path fingerprint")
    cache = HomeThumbnailCache(tmp_path / "cache")

    first = cache.thumbnail_path_for(source)
    second = cache.thumbnail_path_for(source)

    assert first == second
    assert first.parent == tmp_path / "cache"
    assert first.name.endswith(f"-{MAX_THUMBNAIL_WIDTH}x{MAX_THUMBNAIL_HEIGHT}.png")


def test_missing_image_uses_fallback_without_creating_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache = HomeThumbnailCache(cache_dir)

    asset = cache.cached_thumbnail(tmp_path / "missing.png")

    assert asset.thumbnail_url == ""
    assert asset.thumbnail_path is None
    assert asset.uses_fallback
    assert asset.missing_source
    assert asset.fallback_gradient == FALLBACK_GRADIENT
    assert not cache_dir.exists()


def test_thumbnail_path_invalidates_when_source_changes(tmp_path: Path) -> None:
    source = tmp_path / "source-card-art.png"
    source.write_bytes(b"first")
    cache = HomeThumbnailCache(tmp_path / "cache")
    original_path = cache.thumbnail_path_for(source)

    source.write_bytes(b"changed bytes")

    assert cache.thumbnail_path_for(source) != original_path


def test_ensure_thumbnail_uses_thumbnailer_once_for_cached_asset(tmp_path: Path) -> None:
    source = tmp_path / "source-card-art.png"
    source.write_bytes(b"image bytes")
    calls: list[tuple[Path, Path, tuple[int, int]]] = []

    def fake_thumbnailer(source_path: Path, target_path: Path, max_size: tuple[int, int]) -> None:
        calls.append((source_path, target_path, max_size))
        target_path.write_bytes(b"cached thumbnail")

    cache = HomeThumbnailCache(tmp_path / "cache", thumbnailer=fake_thumbnailer)

    created = cache.ensure_thumbnail(source)
    cached = cache.ensure_thumbnail(source)

    assert created.thumbnail_url == created.thumbnail_path.as_uri()
    assert cached.thumbnail_url == created.thumbnail_url
    assert cached.cache_hit
    assert calls == [(source, created.thumbnail_path, (MAX_THUMBNAIL_WIDTH, MAX_THUMBNAIL_HEIGHT))]
