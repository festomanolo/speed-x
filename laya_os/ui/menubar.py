"""Native macOS Menu Bar application for Laya OS using rumps."""

import sys
from typing import Optional

import rumps

from ..core.memory import memory
from ..core.router import CommandRouter


class LayaMenuBarApp(rumps.App):
    def __init__(self):
        super(LayaMenuBarApp, self).__init__("Laya", quit_button=None)
        self.router = CommandRouter()

        # Build initial menu
        self._build_menu()

    def _build_menu(self):
        self.menu.clear()

        # 1. Header
        self.title_item = rumps.MenuItem("Laya OS: Idle (Ready)")
        self.menu.add(self.title_item)
        self.menu.add(rumps.separator)

        # 2. Command Prompt
        self.ask_item = rumps.MenuItem("Ask Laya...", callback=self.on_ask_laya)
        self.menu.add(self.ask_item)
        self.menu.add(rumps.separator)

        # 3. Quick Actions
        quick_menu = rumps.MenuItem("Quick Actions")
        quick_menu.add(rumps.MenuItem("Play / Pause Music", callback=lambda _: self._dispatch("cheza muziki")))
        quick_menu.add(rumps.MenuItem("Next Track", callback=lambda _: self._dispatch("next track")))
        quick_menu.add(rumps.MenuItem("Toggle Dark Mode", callback=lambda _: self._dispatch("dark mode")))
        quick_menu.add(rumps.MenuItem("Mute Audio", callback=lambda _: self._dispatch("mute")))
        quick_menu.add(rumps.MenuItem("Inspect Clipboard", callback=lambda _: self._dispatch("inspect clipboard")))
        quick_menu.add(rumps.MenuItem("Read Screen (OCR)", callback=lambda _: self._dispatch("read screen")))
        self.menu.add(quick_menu)

        # 4. Workspaces
        ws_menu = rumps.MenuItem("Workspaces")
        for ws in memory.list_workspaces():
            ws_menu.add(rumps.MenuItem(ws.title(), callback=lambda _, w=ws: self._dispatch(f"start {w}")))
        self.menu.add(ws_menu)
        self.menu.add(rumps.separator)

        # 5. Recent Commands
        history_menu = rumps.MenuItem("Recent History")
        history = memory._data.get("history", [])[-5:]
        if history:
            for item in reversed(history):
                cmd = item.get("command", "")
                icon = "[OK]" if item.get("success") else "[ERR]"
                history_menu.add(
                    rumps.MenuItem(f"{icon} {cmd}", callback=lambda _, c=cmd: self._dispatch(c))
                )
        else:
            history_menu.add(rumps.MenuItem("(No recent commands)"))
        self.menu.add(history_menu)
        self.menu.add(rumps.separator)

        # 6. Preferences & Quit
        self.menu.add(rumps.MenuItem("Quit Laya", callback=self.on_quit))

    def _dispatch(self, command: str):
        """Execute command via router and show native macOS notification."""
        self.title = "Laya..."
        resp = self.router.process(command)
        self.title = "Laya"

        title = "Laya OS"
        subtitle = f"{resp.decision.domain}:{resp.decision.action}"
        msg = resp.message

        rumps.notification(
            title=title,
            subtitle=subtitle,
            message=msg,
            sound=True,
        )
        self._build_menu()

    def on_ask_laya(self, _):
        """Show native input prompt dialog."""
        window = rumps.Window(
            message="Ask Laya in English or Swahili (e.g. 'ongeza sauti', 'play music', 'anza coding'):",
            title="Ask Laya",
            default_text="",
            ok="Execute",
            cancel="Cancel",
            dimensions=(360, 24),
        )
        response = window.run()
        if response.clicked and response.text.strip():
            self._dispatch(response.text.strip())

    def on_quit(self, _):
        rumps.quit_application()


def run_menubar():
    app = LayaMenuBarApp()
    app.run()


if __name__ == "__main__":
    run_menubar()
