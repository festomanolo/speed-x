"""Tool collection for Laya OS."""

from .apps import AppTool
from .base import BaseTool, ToolResult, registry
from .clipboard import ClipboardTool
from .files import FileTool
from .mail import MailTool
from .music import MusicTool
from .notes import NotesTool
from .screen import ScreenTool
from .system import SystemTool
from .workspaces import WorkspaceTool

__all__ = [
    "registry",
    "BaseTool",
    "ToolResult",
    "SystemTool",
    "AppTool",
    "MusicTool",
    "ClipboardTool",
    "FileTool",
    "WorkspaceTool",
    "ScreenTool",
    "NotesTool",
    "MailTool",
]
