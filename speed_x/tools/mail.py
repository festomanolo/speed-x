"""Native macOS Apple Mail integration using AppleScript and mailto URI fallback."""

import subprocess
import urllib.parse
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry


class MailTool(BaseTool):
    name = "mail"
    description = "Compose and send emails via native Apple Mail."
    supported_actions = ["send", "compose", "open"]

    def _run_applescript(self, script: str, timeout: float = 4.0) -> str:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        return res.stdout.strip()

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}

        try:
            if action in ("send", "compose", "draft"):
                recipient = params.get("recipient", "").strip()
                subject = params.get("subject", "").strip() or "Message from Speed-X"
                message_body = params.get("message", "").strip() or "Sent using Speed-X Assistant for macOS."

                safe_sub = subject.replace('"', '\\"').replace("\n", " ")
                safe_msg = message_body.replace('"', '\\"').replace("\n", "\\n")
                safe_rec = recipient.replace('"', '\\"')

                try:
                    # Attempt via AppleScript first
                    script = f'''
                    tell application "Mail"
                        activate
                        set newMsg to make new outgoing message with properties {{subject:"{safe_sub}", content:"{safe_msg}\\n\\n--\\nSent with Speed-X Offline Assistant", visible:true}}
                        tell newMsg
                            if "{safe_rec}" is not "" then
                                make new to recipient at end of to recipients with properties {{address:"{safe_rec}"}}
                            end if
                        end tell
                    end tell
                    '''
                    self._run_applescript(script, timeout=3.5)
                except Exception:
                    # Fallback to standard macOS URL scheme
                    query_params = {
                        "subject": subject,
                        "body": f"{message_body}\n\n--\nSent with Speed-X Offline Assistant",
                    }
                    mailto_url = f"mailto:{recipient}?" + urllib.parse.urlencode(query_params)
                    subprocess.run(["open", mailto_url], check=True)

                target_desc = f" to {recipient}" if recipient else ""
                return ToolResult(
                    success=True,
                    message=f"Prepared email '{subject}'{target_desc} in Apple Mail.",
                    data={"subject": subject, "recipient": recipient},
                )

            elif action == "open":
                subprocess.run(["open", "-a", "Mail"], check=True)
                return ToolResult(success=True, message="Opened Apple Mail.")

            else:
                return ToolResult(success=False, message=f"Unknown mail action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Mail operation failed: {str(e)}")


# Register Mail Tool
registry.register(MailTool())
