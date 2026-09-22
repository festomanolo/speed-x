"""Base classes and registry for Laya OS tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    success: bool
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
        }


class BaseTool(ABC):
    """Abstract base class for all native macOS tools."""

    name: str = "base"
    description: str = "Base tool description"
    supported_actions: List[str] = field(default_factory=list)

    @abstractmethod
    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Execute a specific action with optional parameters."""
        pass


class ToolRegistry:
    """Central registry for discovering and dispatching tools."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, List[str]]:
        return {name: tool.supported_actions for name, tool in self._tools.items()}

    def dispatch(self, domain: str, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        tool = self.get(domain)
        if not tool:
            return ToolResult(
                success=False,
                message=f"Tool domain '{domain}' not found in registry.",
            )
        try:
            return tool.execute(action, params or {})
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Error executing '{action}' on '{domain}': {str(e)}",
            )


# Global registry instance
registry = ToolRegistry()
