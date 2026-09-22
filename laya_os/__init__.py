"""Backward compatibility alias: laya_os -> speed_x."""
import sys
import speed_x

sys.modules["laya_os"] = speed_x
__all__ = ["speed_x"]
__version__ = "1.0.0"
