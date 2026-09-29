"""Send messages to people by name via WhatsApp or Messages (iMessage/SMS).

The recipient is resolved through Apple Contacts ("manolo" -> "Festo Manolo, +255 7…")
before anything is sent, so the confirmation shows exactly who will receive it.
"""

import difflib
import re
import subprocess
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from .apps import app_installed
from .base import BaseTool, ToolResult, registry

MESSAGING_APPS = {"WhatsApp", "Messages"}

# Country calling codes for turning local numbers (0712…) into international ones.
_CALLING_CODES = {"TZ": "255", "KE": "254", "UG": "256", "RW": "250", "BI": "257", "CD": "243", "NG": "234",
                  "ZA": "27", "GH": "233", "ET": "251", "US": "1", "CA": "1", "GB": "44", "IN": "91", "AE": "971"}


def _region_code() -> str:
    try:
        from Foundation import NSLocale

        return str(NSLocale.currentLocale().countryCode() or "")
    except Exception:
        return ""


def international_digits(number: str) -> str:
    """'+255 712 345 678' -> '255712345678'; '0712 345678' -> '255712345678' (using the Mac's region)."""
    raw = number.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") or raw.startswith("00"):
        return digits.lstrip("0") if raw.startswith("00") else digits
    code = _CALLING_CODES.get(_region_code(), "")
    if digits.startswith("0") and code:
        return code + digits[1:]
    return digits


class MessagingTool(BaseTool):
    name = "messaging"
    description = "Send WhatsApp or iMessage messages to contacts by name."
    supported_actions = ["send"]

    def __init__(self):
        self._contacts_cache: Dict[str, Tuple[float, List[Tuple[str, List[str], List[str]]]]] = {}

    # ------------------------------------------------------------------ contacts

    def _search_contacts(self, query: str) -> List[Tuple[str, List[str], List[str]]]:
        """[(full name, [phones], [emails])] for contacts whose name contains the first word of query."""
        key = query.lower()
        cached = self._contacts_cache.get(key)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        first = key.split()[0].replace('"', "")
        script = f'''
        tell application "Contacts"
            set out to ""
            repeat with p in (every person whose name contains "{first}")
                set out to out & (name of p) & "||"
                repeat with ph in (phones of p)
                    set out to out & (value of ph) & ";;"
                end repeat
                set out to out & "||"
                repeat with em in (emails of p)
                    set out to out & (value of em) & ";;"
                end repeat
                set out to out & linefeed
            end repeat
            return out
        end tell
        '''
        output = self._run_applescript(script, timeout=10)
        people = []
        for line in output.splitlines():
            parts = line.split("||")
            if len(parts) >= 3 and parts[0].strip():
                phones = [p for p in parts[1].split(";;") if p.strip()]
                emails = [e for e in parts[2].split(";;") if e.strip()]
                people.append((parts[0].strip(), phones, emails))
        self._contacts_cache[key] = (time.time(), people)
        return people

    def resolve_contact(self, spoken: str) -> Tuple[Optional[Tuple[str, List[str], List[str]]], List[str]]:
        """Best contact for a spoken name, plus the other candidate names (for ambiguity)."""
        people = self._search_contacts(spoken)
        if not people:
            return None, []
        spoken_l = spoken.lower()

        def score(person):
            name = person[0].lower()
            words = name.split()
            s = difflib.SequenceMatcher(None, spoken_l, name).ratio()
            if spoken_l in words:
                s += 0.6  # exact first/last name
            if name == spoken_l:
                s += 1.0
            if person[1]:
                s += 0.2  # reachable by phone
            return s

        ranked = sorted(people, key=score, reverse=True)
        return ranked[0], [p[0] for p in ranked[1:4]]

    # ------------------------------------------------------------------ planning hook

    def prepare(self, action: str, params: Dict[str, Any]) -> Optional[str]:
        """Resolve the recipient before confirmation. Returns an error message, or None."""
        if action != "send":
            return None
        if not params.get("text"):
            return f"What should I say to {params.get('to', 'them')}?"
        if not params.get("to"):
            return "Who should I send the message to?"
        if params.get("app") not in MESSAGING_APPS:
            params["app"] = "WhatsApp" if app_installed("WhatsApp") else "Messages"
        if params["app"] == "WhatsApp" or params.get("handle"):
            return None  # WhatsApp: we search the name inside WhatsApp itself
        try:
            person, others = self.resolve_contact(params["to"])
        except Exception as e:
            if params["app"] == "WhatsApp":
                # Still useful without Contacts: WhatsApp's picker with the text already typed.
                params["picker"] = True
                return None
            return (
                f"I can't look up “{params['to']}” without Contacts access ({e}). "
                "Allow Speed-X under Privacy & Security › Automation › Contacts."
            )
        if not person:
            if params["app"] == "WhatsApp":
                params["picker"] = True
                return None
            return f"I couldn't find “{params['to']}” in your Contacts."
        name, phones, emails = person
        params["contact"] = name
        params["alternatives"] = others
        if params["app"] == "WhatsApp":
            if not phones:
                return f"{name} has no phone number in Contacts, so I can't reach them on WhatsApp."
            params["phone"] = international_digits(phones[0])
        else:
            handle = phones[0] if phones else (emails[0] if emails else "")
            if not handle:
                return f"{name} has no phone number or email in Contacts."
            params["handle"] = handle
        return None

    # ------------------------------------------------------------------ WhatsApp

    WHATSAPP_SCRIPT = """
    set previousClipboard to ""
    try
        set previousClipboard to the clipboard as text
    end try
    tell application "WhatsApp" to activate
    delay 0.9
    tell application "System Events"
        tell process "WhatsApp"
            set frontmost to true
            -- 1. search the chat list for the contact
            keystroke "f" using {command down}
            delay 0.35
            keystroke "a" using {command down}
            set the clipboard to "__NAME__"
            keystroke "v" using {command down}
            delay 1.4
            -- 2. open the first result
            key code 125
            delay 0.25
            key code 36
            delay 1.0
            -- 3. paste the message and send
            set the clipboard to "__TEXT__"
            keystroke "v" using {command down}
            delay 0.3
            key code 36
        end tell
    end tell
    delay 0.3
    set the clipboard to previousClipboard
    return "ok"
    """

    def _send_whatsapp(self, who: str, text: str) -> ToolResult:
        """Open WhatsApp, search the contact by name, open the chat, paste the message, send."""
        if not app_installed("WhatsApp"):
            return ToolResult(success=False, message="WhatsApp isn't installed on this Mac.")
        esc = lambda v: v.replace("\\", "\\\\").replace('"', '\\"')
        script = self.WHATSAPP_SCRIPT.replace("__NAME__", esc(who)).replace("__TEXT__", esc(text))
        try:
            self._run_applescript(script, timeout=15)
        except Exception as e:
            msg = str(e)
            if "not allowed" in msg.lower() or "assistive" in msg.lower() or "1002" in msg or "-25211" in msg:
                return ToolResult(
                    success=False,
                    message="To type into WhatsApp, turn on Speed-X in System Settings › Privacy & Security › Accessibility, then ask again.",
                )
            return ToolResult(success=False, message=f"WhatsApp automation failed: {msg}")
        return ToolResult(success=True, message=f"Sent “{text}” to {who} on WhatsApp.", data={"contact": who, "app": "WhatsApp"})

    # ------------------------------------------------------------------ execution

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        if action != "send":
            return ToolResult(success=False, message=f"Unknown messaging action: '{action}'.")
        problem = self.prepare(action, params)
        if problem:
            return ToolResult(success=False, message=problem)

        text = params["text"]
        who = params.get("contact") or params["to"]
        try:
            if params["app"] == "WhatsApp":
                return self._send_whatsapp(who, text)
            safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
            safe_handle = params["handle"].replace('"', "")
            self._run_applescript(
                f'''
                tell application "Messages"
                    set targetService to 1st account whose service type = iMessage
                    set targetBuddy to participant "{safe_handle}" of targetService
                    send "{safe_text}" to targetBuddy
                end tell
                ''',
                timeout=10,
            )
            return ToolResult(success=True, message=f"Sent “{text}” to {who} with Messages.", data={"contact": who})
        except Exception as e:
            return ToolResult(success=False, message=f"Couldn't send the message to {who}: {e}")


registry.register(MessagingTool())
