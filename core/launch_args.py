"""연결된(기존) 설치의 실행 배치 파일에서 실행 인자를 읽어 온다.

사용자가 직접 쓰던 `webui-user.bat` / `run_nvidia_gpu*.bat` 에는 그 PC 에 맞춰 둔 플래그
(--sage, --cuda-malloc, --fast fp16_accumulation …)가 있다. 앱이 그 설치를 띄울 때 이걸
빼먹으면 "직접 켤 땐 빠른데 앱에서 켜면 느리다" 가 된다. 반대로 앱이 스스로 정하는 인자
(--port, --data-dir, --api, --theme …)는 배치 파일 값을 버린다 — 둘이 겹치면 충돌한다.

순수 함수만 있다 — tests/test_launch_args.py 가 실제 배치 파일 본문으로 검증한다.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

FORGE_USER_BATS = ("webui-user.bat", "user.bat")
COMFY_RUN_BAT = "run_nvidia_gpu.bat"
COMFY_FAST_FP16_BAT = "run_nvidia_gpu_fast_fp16_accumulation.bat"
FAST_FP16_ARGS = ("--fast", "fp16_accumulation")

#: 앱이 직접 정하는 플래그 → 값 개수. "opt" 는 다음 토큰이 플래그가 아닐 때만 값.
FORGE_MANAGED_FLAGS: dict[str, int | str] = {
    "--api": 0, "--api-server-stop": 0, "--port": 1, "--data-dir": 1, "--theme": 1,
    "--skip-prepare-environment": 0, "--ckpt-dirs": 1, "--lora-dirs": 1, "--vae-dirs": 1,
    "--text-encoder-dirs": 1, "--ckpt-dir": 1, "--lora-dir": 1, "--vae-dir": 1,
    # --uv 는 앱이 일부러 넘기지 않는다 (관리형 venv 훅과 충돌).
    "--uv": 0, "--autolaunch": 0, "--listen": 0, "--share": 0, "--nowebui": 0,
    "--server-name": 1, "--gradio-auth": 1,
}
COMFY_MANAGED_FLAGS: dict[str, int | str] = {
    "--windows-standalone-build": 0, "--listen": "opt", "--port": 1, "--base-directory": 1,
    "--extra-model-paths-config": 1, "--enable-manager": 0, "--auto-launch": 0,
    "--disable-auto-launch": 0, "--cpu": 0,
}


@dataclass
class LaunchArgsImport:
    source: str = ""                       # 읽은 배치 파일 경로 ("" = 없음)
    args: list[str] = field(default_factory=list)      # 앱 명령줄에 덧붙일 것
    dropped: list[str] = field(default_factory=list)   # 앱이 정하는 것과 겹쳐 뺀 플래그


def split_args(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        return [t for t in shlex.split(text, posix=False) if t]
    except ValueError:
        return text.split()


def parse_forge_user_bat(text: str) -> list[str]:
    """`set COMMANDLINE_ARGS=...` 줄들을 읽는다. `%COMMANDLINE_ARGS%` 로 이어 붙이는 꼴도 지원.

    `::` / `rem` 주석은 건너뛴다 — 사용자가 주석으로 둔 옛 플래그를 살리면 안 된다.
    """
    value = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("::") or line.lower().startswith("rem ") or line.lower() == "rem":
            continue
        match = re.match(r'^set\s+"?COMMANDLINE_ARGS\s*=(.*?)"?\s*$', line, re.IGNORECASE)
        if not match:
            continue
        rhs = match.group(1).strip()
        rhs = re.sub(r"%COMMANDLINE_ARGS%", lambda _m: value, rhs, flags=re.IGNORECASE)
        value = rhs.strip()
    return split_args(value)


def parse_comfy_run_bat(text: str) -> list[str]:
    """`...python.exe -s ComfyUI\\main.py <인자들>` 줄에서 main.py 뒤의 인자를 읽는다."""
    for raw in (text or "").splitlines():
        line = raw.strip()
        lowered = line.lower()
        if not line or lowered.startswith(("rem ", "::", "echo ", "pause", "@echo")):
            continue
        tokens = split_args(line)
        index = next(
            (i for i, token in enumerate(tokens) if token.replace("\\", "/").lower().rstrip('"').endswith("main.py")),
            None,
        )
        if index is None:
            continue
        return tokens[index + 1:]
    return []


def _flag_name(token: str) -> str:
    return token.split("=", 1)[0].lower() if token.startswith("-") else ""


def strip_managed_flags(args: Sequence[str], managed: Mapping[str, int | str]) -> tuple[list[str], list[str]]:
    """앱이 직접 정하는 플래그(와 그 값)를 뺀다. (남긴 것, 뺀 플래그) 를 돌려준다."""
    kept: list[str] = []
    dropped: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        name = _flag_name(token)
        if name and name in managed:
            dropped.append(token)
            count = managed[name]
            has_inline_value = "=" in token
            if not has_inline_value:
                if count == 1 and i + 1 < len(args):
                    i += 1
                elif count == "opt" and i + 1 < len(args) and not args[i + 1].startswith("-"):
                    i += 1
            i += 1
            continue
        kept.append(token)
        i += 1
    return kept, dropped


def _group(args: Sequence[str]) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    for token in args:
        name = _flag_name(token)
        if name:
            groups.append((name, [token]))
        elif groups and groups[-1][0]:
            groups[-1][1].append(token)
        else:
            groups.append(("", [token]))
    return groups


def merge_args(imported: Sequence[str], user: Sequence[str]) -> list[str]:
    """배치 파일 인자 + 사용자가 설정에 적은 인자. 같은 플래그는 **사용자 것**이 이긴다."""
    user_groups = _group(user)
    user_flags = {name for name, _ in user_groups if name}
    merged: list[str] = []
    for name, tokens in _group(imported):
        if name and name in user_flags:
            continue
        merged.extend(tokens)
    for _name, tokens in user_groups:
        merged.extend(tokens)
    return merged


def discover_launch_args(
    engine: str,
    roots: Iterable[Path | str],
    *,
    fast_fp16: bool = False,
) -> LaunchArgsImport:
    """설치 루트들에서 실행 배치 파일을 찾아 인자를 읽는다.

    forge  : webui-user.bat 의 COMMANDLINE_ARGS.
    comfyui: run_nvidia_gpu.bat — fast_fp16 이면 run_nvidia_gpu_fast_fp16_accumulation.bat 를
             먼저 찾고, 없으면 일반 배치 + `--fast fp16_accumulation` 을 덧붙인다.
    배치 파일이 없으면 인자 없음(comfyui 의 fp16 토글만 살아남는다).
    """
    engine = (engine or "").lower()
    candidates: list[Path] = []
    for root in roots:
        try:
            path = Path(root)
        except TypeError:
            continue
        if path not in candidates:
            candidates.append(path)

    if engine == "forge":
        for root in candidates:
            for name in FORGE_USER_BATS:
                bat = root / name
                if bat.is_file():
                    args = parse_forge_user_bat(_read(bat))
                    kept, dropped = strip_managed_flags(args, FORGE_MANAGED_FLAGS)
                    return LaunchArgsImport(str(bat), kept, dropped)
        return LaunchArgsImport()

    if engine == "comfyui":
        names = ([COMFY_FAST_FP16_BAT] if fast_fp16 else []) + [COMFY_RUN_BAT]
        for name in names:
            for root in candidates:
                bat = root / name
                if bat.is_file():
                    args = parse_comfy_run_bat(_read(bat))
                    kept, dropped = strip_managed_flags(args, COMFY_MANAGED_FLAGS)
                    if fast_fp16 and "--fast" not in {_flag_name(t) for t in kept}:
                        kept.extend(FAST_FP16_ARGS)
                    return LaunchArgsImport(str(bat), kept, dropped)
        return LaunchArgsImport("", list(FAST_FP16_ARGS) if fast_fp16 else [], [])

    return LaunchArgsImport()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
