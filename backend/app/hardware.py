"""Best-effort hardware detection for display, via platform introspection + CLI probes."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache


@dataclass(slots=True)
class HardwareInfo:
    device: str  # "apple-silicon" | "cuda" | "rocm" | "cpu"
    label: str
    details: str


def _has(command: str) -> bool:
    return shutil.which(command) is not None


def _probe(command: list[str]) -> str | None:
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=2)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return None


@lru_cache
def detect_hardware() -> HardwareInfo:
    system = platform.system()
    machine = platform.machine().lower()

    # Apple Silicon (Metal / MPS).
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return HardwareInfo(
            device="apple-silicon",
            label="Apple Silicon (Metal)",
            details=platform.processor() or "arm64",
        )

    # NVIDIA CUDA.
    if _has("nvidia-smi"):
        name = _probe(
            [
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader",
            ]
        )
        gpu = name.splitlines()[0] if name else "NVIDIA GPU"
        return HardwareInfo(device="cuda", label="NVIDIA CUDA", details=gpu)

    # AMD ROCm.
    if _has("rocminfo") or _has("rocm-smi"):
        return HardwareInfo(device="rocm", label="AMD ROCm", details="ROCm-capable GPU")

    # CPU fallback.
    return HardwareInfo(
        device="cpu",
        label="CPU",
        details=f"{platform.processor() or machine} ({system})",
    )
