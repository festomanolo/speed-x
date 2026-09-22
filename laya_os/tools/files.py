"""Native macOS file discovery using Spotlight's mdfind engine."""

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, registry


class FileTool(BaseTool):
    name = "files"
    description = "Instant indexed file search and management using Spotlight (mdfind)."
    supported_actions = [
        "search",
        "find_pdf",
        "open_file",
        "latest_screenshot",
    ]

    def _run_mdfind(self, query: str, limit: int = 5) -> List[str]:
        cmd = ["mdfind", query]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return lines[:limit]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        try:
            if action in ("search", "find"):
                name = params.get("query", "").strip()
                if not name:
                    return ToolResult(success=False, message="No search query provided.")
                # Search case-insensitive by filename
                query = f"kMDItemFSName == '*{name}*'cd"
                matches = self._run_mdfind(query, limit=params.get("limit", 5))
                if matches:
                    return ToolResult(
                        success=True,
                        message=f"Found {len(matches)} matching file(s).",
                        data={"matches": matches},
                    )
                return ToolResult(success=True, message=f"No files matching '{name}' found.", data={"matches": []})

            elif action == "find_pdf":
                query = "kMDItemContentType == 'com.adobe.pdf'"
                name = params.get("query")
                if name:
                    query += f" && kMDItemFSName == '*{name}*'cd"
                matches = self._run_mdfind(query, limit=params.get("limit", 5))
                return ToolResult(
                    success=True,
                    message=f"Found {len(matches)} PDF(s).",
                    data={"matches": matches},
                )

            elif action == "open_file":
                filepath = params.get("path")
                if not filepath or not os.path.exists(filepath):
                    return ToolResult(success=False, message=f"File does not exist: {filepath}")
                subprocess.run(["open", filepath], check=True)
                return ToolResult(success=True, message=f"Opened {Path(filepath).name}.")

            elif action == "latest_screenshot":
                desktop = Path.home() / "Desktop"
                screenshots = list(desktop.glob("Screenshot*")) + list(desktop.glob("Screen Shot*"))
                if not screenshots:
                    return ToolResult(success=False, message="No screenshots found on Desktop.")
                latest = max(screenshots, key=lambda p: p.stat().st_mtime)
                return ToolResult(
                    success=True,
                    message=f"Latest screenshot: {latest.name}",
                    data={"path": str(latest)},
                )

            else:
                return ToolResult(success=False, message=f"Unknown file action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"File operation failed: {str(e)}")


# Register tool
registry.register(FileTool())
