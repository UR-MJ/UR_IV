# core/cache_cleanup.py
"""이미지 캐시 정리 — 순수 파일시스템 유틸(테스트 가능). Qt 의존 없음.

`image_cache/`에 정리 루틴이 아예 없어서 무한히 쌓였다. 실측(2026-07):
    image_cache 전체     812 MB
    ├─ thumbs        96,641 files / 389 MB   ← NTFS 단일 디렉터리 10만 파일
    ├─ editor_temp      115 files / 256 MB   ← 편집 1회당 풀해상도 PNG 1장
    └─ compare            1 file  /  15 MB

thumbs는 개수가 문제라 sha1 앞 2자리로 샤딩한다. 디렉터리당 ~380개로 떨어져
`os.path.exists` 조회와 탐색기 접근이 모두 빨라진다.
"""
import os
import time

# 썸네일 샤딩: sha1 앞 2자리 → 256개 하위 디렉터리
SHARD_PREFIX_LEN = 2


def shard_path(base_dir: str, digest: str, ext: str = '.jpg') -> str:
    """sha1 해시로 샤딩된 캐시 경로. 디렉터리는 만들지 않는다(호출자 책임)."""
    digest = str(digest)
    prefix = digest[:SHARD_PREFIX_LEN] or '00'
    return os.path.join(base_dir, prefix, f"{digest}{ext}")


def ensure_shard_dir(path: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass


def _entries_by_mtime(directory: str, exts=None):
    """(mtime, size, path) 목록을 오래된 순으로. scandir의 stat 캐시 사용."""
    out = []
    try:
        with os.scandir(directory) as scan:
            for entry in scan:
                if not entry.is_file():
                    continue
                if exts and not entry.name.lower().endswith(exts):
                    continue
                try:
                    stat = entry.stat()
                    out.append((stat.st_mtime, stat.st_size, entry.path))
                except OSError:
                    continue
    except (OSError, FileNotFoundError):
        return []
    out.sort(key=lambda item: item[0])
    return out


def _unlink(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def prune_editor_temp(directory: str, keep: int = 40, max_age_hours: float = 24.0) -> int:
    """편집 임시본 정리 — 최근 `keep`개는 남기고 나머지 중 오래된 것을 지운다.

    최근 것을 남기는 이유: undo 스택이 이 파일 경로를 그대로 참조하므로,
    작업 중인 히스토리를 지우면 undo가 깨진다. keep은 EditorView의 MAX_UNDO(30)보다
    넉넉해야 한다.

    반환: 지운 파일 수.
    """
    if keep < 0:
        keep = 0
    entries = _entries_by_mtime(directory, exts=('.png', '.jpg', '.jpeg', '.webp'))
    if len(entries) <= keep:
        return 0

    cutoff = time.time() - max(0.0, float(max_age_hours)) * 3600.0
    # 최근 keep개는 무조건 보존, 그 앞쪽(오래된 것)만 후보
    candidates = entries[:-keep] if keep else entries
    removed = 0
    for mtime, _size, path in candidates:
        if mtime <= cutoff:
            removed += _unlink(path)
    return removed


def prune_by_total_size(directory: str, max_bytes: int, *, recursive: bool = False) -> int:
    """디렉터리 총 용량이 상한을 넘으면 오래된 것부터 지운다 (LRU 근사).

    썸네일 캐시처럼 '언제든 다시 만들 수 있는' 캐시에만 쓴다.
    반환: 지운 파일 수.
    """
    if recursive:
        entries = []
        for root, _dirs, files in os.walk(directory):
            for name in files:
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                    entries.append((stat.st_mtime, stat.st_size, path))
                except OSError:
                    continue
        entries.sort(key=lambda item: item[0])
    else:
        entries = _entries_by_mtime(directory)

    total = sum(size for _m, size, _p in entries)
    if total <= max_bytes:
        return 0

    removed = 0
    for _mtime, size, path in entries:
        if total <= max_bytes:
            break
        if _unlink(path):
            total -= size
            removed += 1
    return removed


def prune_thumbs(directory: str, max_bytes: int = 300 * 1024 * 1024) -> int:
    """썸네일 캐시 상한(기본 300MB). 샤딩된 하위 디렉터리까지 훑는다."""
    return prune_by_total_size(directory, max_bytes, recursive=True)


def migrate_flat_to_sharded(directory: str, limit: int = 5000) -> int:
    """평면 캐시 디렉터리를 샤딩 구조로 이관. 한 번에 `limit`개씩(앱 시작 지연 방지).

    이관 실패는 무시한다 — 썸네일은 언제든 재생성 가능하고, 실패한 파일은
    다음 실행에서 다시 시도된다. 반환: 옮긴 파일 수.
    """
    moved = 0
    try:
        with os.scandir(directory) as scan:
            for entry in scan:
                if moved >= limit:
                    break
                if not entry.is_file():
                    continue
                stem, ext = os.path.splitext(entry.name)
                if len(stem) < SHARD_PREFIX_LEN:
                    continue
                target = shard_path(directory, stem, ext)
                if os.path.abspath(target) == os.path.abspath(entry.path):
                    continue
                ensure_shard_dir(target)
                try:
                    os.replace(entry.path, target)
                    moved += 1
                except OSError:
                    continue
    except (OSError, FileNotFoundError):
        return moved
    return moved
