"""Configuration and hardware auto-detection for Laya OS."""

import os
import platform
import subprocess
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DEFAULT_MODEL_DIR = MODELS_DIR / "laya-multilingual"
USER_CONFIG_DIR = Path.home() / ".config" / "laya_os"
USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = USER_CONFIG_DIR / "memory.json"

# Hardware auto-detection
IS_MACOS = platform.system() == "Darwin"
ARCH = platform.machine().lower()
IS_ARM = "arm" in ARCH or "aarch64" in ARCH


def is_apple_silicon() -> bool:
    """Check if device has native Apple Silicon (ANE/Apple GPU)."""
    if not IS_MACOS:
        return False
    if IS_ARM:
        return True
    try:
        # Check if running under Rosetta
        res = subprocess.run(
            ["sysctl", "-n", "sysctl.proc_translated"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.stdout.strip() == "1"
    except Exception:
        return False


# Determine safe compute unit for Core ML
# On Intel Macs with integrated graphics, Metal compiler crashes or hangs can occur.
# "cpu" (CPU_ONLY) provides rock-solid stability and zero crashes.
# On Apple Silicon, "cpu_ne" or "cpu_gpu" can be used.
if is_apple_silicon():
    DEFAULT_COMPUTE_UNITS = os.getenv("LAYA_COMPUTE_UNITS", "cpu_ne")
else:
    DEFAULT_COMPUTE_UNITS = os.getenv("LAYA_COMPUTE_UNITS", "cpu")

LANGUAGE_MODES = ["en", "sw", "mixed"]
DEFAULT_LANGUAGE = "mixed"
