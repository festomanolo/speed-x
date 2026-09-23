"""Native macOS Apple Notes integration using AppleScript."""

import datetime
import subprocess
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry


class NotesTool(BaseTool):
    name = "notes"
    description = "Create, view, and update notes in native Apple Notes."
    supported_actions = ["create", "update", "open"]

    def _run_applescript(self, script: str) -> str:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            if action in ("create", "new", "write"):
                title = params.get("title") or "Speed-X Note"
                body_content = params.get("body") or f"Created by Speed-X Assistant on {now_str}."
                # Clean strings for AppleScript
                safe_title = title.replace('"', '\\"').replace("\n", " ")
                safe_body = body_content.replace('"', '\\"').replace("\n", "<br/>")

                script = f'''
                tell application "Notes"
                    activate
                    tell default account
                        make new note with properties {{name:"{safe_title}", body:"<div><h1>{safe_title}</h1><p>{safe_body}</p></div>"}}
                    end tell
                end tell
                '''
                self._run_applescript(script)
                return ToolResult(
                    success=True,
                    message=f"Created new note '{title}' in Apple Notes.",
                    data={"title": title, "body": body_content},
                )

            elif action in ("update", "append"):
                addition = params.get("addition") or params.get("body") or f"Updated by Speed-X Assistant on {now_str}."
                safe_add = addition.replace('"', '\\"').replace("\n", "<br/>")

                script = f'''
                tell application "Notes"
                    activate
                    if (count of notes) > 0 then
                        set n to note 1
                        set oldBody to body of n
                        set body of n to oldBody & "<br/><p style=\\"color:#2563eb;\\"><strong>[Updated {now_str}]:</strong> {safe_add}</p>"
                        return name of n
                    else
                        make new note with properties {{name:"Speed-X Note", body:"<div><h1>Speed-X Note</h1><p>{safe_add}</p></div>"}}
                        return "Speed-X Note"
                    end if
                end tell
                '''
                note_name = self._run_applescript(script)
                return ToolResult(
                    success=True,
                    message=f"Updated note '{note_name}' in Apple Notes.",
                    data={"note_name": note_name, "addition": addition},
                )

            elif action == "open":
                subprocess.run(["open", "-a", "Notes"], check=True)
                return ToolResult(success=True, message="Opened Apple Notes.")

            else:
                return ToolResult(success=False, message=f"Unknown notes action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Notes operation failed: {str(e)}")


# Register Notes Tool
registry.register(NotesTool())
