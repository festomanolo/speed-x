"""Native macOS screen intelligence tool (silent capture & Apple Vision OCR)."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry

BIN_OCR = Path(__file__).resolve().parent.parent.parent / "bin" / "laya-ocr"


class ScreenTool(BaseTool):
    name = "screen"
    description = "Capture screen and extract on-device text using native macOS Vision OCR."
    supported_actions = ["capture", "read", "ocr", "active_window"]

    def _capture_silent(self, output_path: str, window_only: bool = False) -> bool:
        cmd = ["screencapture", "-x"]
        if window_only:
            cmd.append("-w")  # or interactive/active
        cmd.append(output_path)
        res = subprocess.run(cmd, capture_output=True)
        return res.returncode == 0 and os.path.exists(output_path)

    def _run_ocr(self, image_path: str) -> str:
        if not BIN_OCR.exists():
            return "OCR engine binary not found."
        res = subprocess.run(
            [str(BIN_OCR), image_path],
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        try:
            if action == "capture":
                dest = params.get("path")
                if not dest:
                    dest = os.path.expanduser("~/Desktop/Laya_Screenshot.png")
                ok = self._capture_silent(dest)
                if ok:
                    return ToolResult(
                        success=True,
                        message=f"Screenshot saved to {dest}.",
                        data={"path": dest},
                    )
                return ToolResult(success=False, message="Failed to capture screen.")

            elif action in ("read", "ocr", "read_screen"):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name

                try:
                    if not self._capture_silent(tmp_path):
                        return ToolResult(success=False, message="Could not capture screen for OCR.")
                    text = self._run_ocr(tmp_path)
                    lines = [l for l in text.splitlines() if l.strip()]
                    summary = f"Detected {len(lines)} line(s) of text on screen."
                    preview = "\n".join(lines[:10])
                    if len(lines) > 10:
                        preview += f"\n... ({len(lines)-10} more lines)"
                    return ToolResult(
                        success=True,
                        message=f"{summary}\n{preview}",
                        data={"text": text, "line_count": len(lines)},
                    )
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

            else:
                return ToolResult(success=False, message=f"Unknown screen action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Screen operation failed: {str(e)}")


# Register tool
registry.register(ScreenTool())
