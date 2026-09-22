"""Native macOS clipboard intelligence (read, write, inspect)."""

import subprocess
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry


class ClipboardTool(BaseTool):
    name = "clipboard"
    description = "Read, write, and inspect the macOS system clipboard."
    supported_actions = ["read", "write", "inspect", "clear"]

    def _read_clipboard(self) -> str:
        res = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        return res.stdout

    def _write_clipboard(self, text: str):
        subprocess.run(["pbcopy"], input=text, text=True, check=True)

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        try:
            if action in ("read", "get"):
                content = self._read_clipboard()
                preview = (content[:100] + "...") if len(content) > 100 else content
                return ToolResult(
                    success=True,
                    message=f"Clipboard content: {preview}" if content else "Clipboard is empty.",
                    data={"content": content, "length": len(content)},
                )

            elif action in ("write", "set", "copy"):
                text = params.get("text", "")
                self._write_clipboard(text)
                return ToolResult(
                    success=True,
                    message=f"Copied {len(text)} characters to clipboard.",
                    data={"length": len(text)},
                )

            elif action == "inspect":
                content = self._read_clipboard()
                words = len(content.split())
                lines = len(content.splitlines())
                chars = len(content)
                return ToolResult(
                    success=True,
                    message=f"Clipboard stats: {words} words, {lines} lines, {chars} characters.",
                    data={
                        "words": words,
                        "lines": lines,
                        "characters": chars,
                        "preview": content[:120],
                    },
                )

            elif action == "clear":
                self._write_clipboard("")
                return ToolResult(success=True, message="Clipboard cleared.")

            else:
                return ToolResult(success=False, message=f"Unknown clipboard action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Clipboard operation failed: {str(e)}")


# Register tool
registry.register(ClipboardTool())
