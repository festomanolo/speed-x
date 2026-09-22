"""Unit tests for Laya OS tools, brain, guardrails, and router."""

import unittest
from laya_os.core.brain import LayaBrain
from laya_os.core.guardrails import guardrails
from laya_os.core.router import CommandRouter
from laya_os.tools.apps import normalize_app_name
from laya_os.tools.base import registry


class TestLayaOS(unittest.TestCase):

    def test_tool_registry(self):
        tools = registry.list_tools()
        self.assertIn("system", tools)
        self.assertIn("apps", tools)
        self.assertIn("music", tools)
        self.assertIn("clipboard", tools)
        self.assertIn("files", tools)
        self.assertIn("workspaces", tools)
        self.assertIn("screen", tools)

    def test_app_normalization(self):
        self.assertEqual(normalize_app_name("safari"), "Safari")
        self.assertEqual(normalize_app_name("browser"), "Safari")
        self.assertEqual(normalize_app_name("vscode"), "Visual Studio Code")
        self.assertEqual(normalize_app_name("code"), "Visual Studio Code")
        self.assertEqual(normalize_app_name("chrome"), "Google Chrome")

    def test_guardrails(self):
        # Sensitive actions
        is_sens, _ = guardrails.requires_confirmation("system", "lock_screen")
        self.assertTrue(is_sens)
        is_sens, _ = guardrails.requires_confirmation("system", "sleep")
        self.assertTrue(is_sens)

        # Safe actions
        is_sens, _ = guardrails.requires_confirmation("system", "volume_up")
        self.assertFalse(is_sens)
        is_sens, _ = guardrails.requires_confirmation("music", "play")
        self.assertFalse(is_sens)

    def test_bilingual_brain_english(self):
        brain = LayaBrain()

        dec = brain.decide("play music")
        self.assertEqual(dec.domain, "music")
        self.assertEqual(dec.action, "play")

        dec = brain.decide("volume up")
        self.assertEqual(dec.domain, "system")
        self.assertEqual(dec.action, "volume_up")

        dec = brain.decide("open Safari")
        self.assertEqual(dec.domain, "apps")
        self.assertEqual(dec.action, "open")
        self.assertEqual(dec.params.get("app"), "Safari")

        dec = brain.decide("find pdf research")
        self.assertEqual(dec.domain, "files")
        self.assertEqual(dec.action, "find_pdf")

        dec = brain.decide("take screenshot")
        self.assertEqual(dec.domain, "screen")
        self.assertEqual(dec.action, "capture")

        dec = brain.decide("read screen")
        self.assertEqual(dec.domain, "screen")
        self.assertEqual(dec.action, "read")

    def test_bilingual_brain_swahili(self):
        brain = LayaBrain()

        dec = brain.decide("cheza muziki")
        self.assertEqual(dec.domain, "music")
        self.assertEqual(dec.action, "play")

        dec = brain.decide("ongeza sauti")
        self.assertEqual(dec.domain, "system")
        self.assertEqual(dec.action, "volume_up")

        dec = brain.decide("fungua Safari")
        self.assertEqual(dec.domain, "apps")
        self.assertEqual(dec.action, "open")
        self.assertEqual(dec.params.get("app"), "Safari")

        dec = brain.decide("anza coding")
        self.assertEqual(dec.domain, "workspaces")
        self.assertEqual(dec.action, "activate")
        self.assertEqual(dec.params.get("workspace"), "coding")

        dec = brain.decide("funga kioo")
        self.assertEqual(dec.domain, "system")
        self.assertEqual(dec.action, "lock_screen")
        self.assertTrue(dec.requires_confirmation)

        dec = brain.decide("piga screenshot")
        self.assertEqual(dec.domain, "screen")
        self.assertEqual(dec.action, "capture")

        dec = brain.decide("soma kioo")
        self.assertEqual(dec.domain, "screen")
        self.assertEqual(dec.action, "read")

    def test_router_flow(self):
        router = CommandRouter()

        # Sensitive command requires confirmation
        resp = router.process("lock screen")
        self.assertTrue(resp.needs_confirmation)

        # Non-sensitive command executes directly
        resp = router.process("inspect clipboard")
        self.assertTrue(resp.success)
        self.assertEqual(resp.decision.domain, "clipboard")


if __name__ == "__main__":
    unittest.main()
