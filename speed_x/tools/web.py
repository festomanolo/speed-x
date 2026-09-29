"""Open websites and run web searches in the default browser."""

import re
import subprocess
import urllib.parse
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry

KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "wikipedia": "https://www.wikipedia.org",
    "stack overflow": "https://stackoverflow.com",
    "stackoverflow": "https://stackoverflow.com",
}

_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?$", re.IGNORECASE)


def site_url(name: str) -> Optional[str]:
    """URL for a spoken site name ("youtube", "github.com", "go to bbc dot com"), else None."""
    cleaned = name.lower().strip().replace(" dot ", ".")
    cleaned = re.sub(r"^(https?://)?(www\.)?", "", cleaned)
    if cleaned in KNOWN_SITES:
        return KNOWN_SITES[cleaned]
    if _DOMAIN_RE.match(cleaned):
        return "https://" + cleaned
    return None


class WebTool(BaseTool):
    name = "web"
    description = "Open websites and search the web in the default browser."
    supported_actions = ["search", "open_url", "youtube"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        try:
            if action == "search":
                query = params.get("query", "").strip()
                if not query:
                    return ToolResult(success=False, message="What should I search for?")
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
                subprocess.run(["open", url], check=True)
                return ToolResult(
                    success=True, message=f"Searching the web for “{query}”.", data={"url": url}
                )

            if action == "youtube":
                query = params.get("query", "").strip()
                url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(
                    query
                )
                subprocess.run(["open", url], check=True)
                return ToolResult(
                    success=True, message=f"Searching YouTube for “{query}”.", data={"url": url}
                )

            if action == "open_url":
                url = params.get("url") or site_url(params.get("site", ""))
                if not url:
                    return ToolResult(
                        success=False, message="I couldn't work out which website to open."
                    )
                subprocess.run(["open", url], check=True)
                host = urllib.parse.urlparse(url).netloc.replace("www.", "")
                return ToolResult(success=True, message=f"Opened {host}.", data={"url": url})

            return ToolResult(success=False, message=f"Unknown web action: '{action}'.")
        except Exception as e:
            return ToolResult(success=False, message=f"Web action failed: {e}")


registry.register(WebTool())
