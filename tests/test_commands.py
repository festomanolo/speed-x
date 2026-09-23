"""Tests for Speed-X native tools: Notes, Mail, Files, and intent routing using standard unittest."""

import tempfile
import unittest
from pathlib import Path
from speed_x.core.router import CommandRouter
from speed_x.tools.base import registry
from speed_x.tools.files import FileTool


class TestSpeedXCommands(unittest.TestCase):
    def setUp(self):
        self.router = CommandRouter()

    def test_registry_has_new_tools(self):
        tools = registry.list_tools()
        self.assertIn("notes", tools)
        self.assertIn("mail", tools)
        self.assertIn("files", tools)
        self.assertIn("create", tools["notes"])
        self.assertIn("update", tools["notes"])
        self.assertIn("send", tools["mail"])
        self.assertIn("create", tools["files"])

    def test_file_tool_make_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = FileTool()
            res = tool.execute("create", {"filename": "test_speedx.txt", "folder": tmp_dir, "content": "Hello Speed-X"})
            self.assertTrue(res.success)
            target = Path(tmp_dir) / "test_speedx.txt"
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "Hello Speed-X")

    def test_intent_routing_notes_create(self):
        cmd = "open notes app and write a new note"
        resp = self.router.process(cmd)
        self.assertEqual(resp.decision.domain, "notes")
        self.assertEqual(resp.decision.action, "create")
        self.assertTrue(resp.success)

    def test_intent_routing_notes_update(self):
        cmd = "update the existing one"
        resp = self.router.process(cmd)
        self.assertEqual(resp.decision.domain, "notes")
        self.assertEqual(resp.decision.action, "update")
        self.assertTrue(resp.success)

    def test_intent_routing_make_file(self):
        cmd = "make new file"
        resp = self.router.process(cmd)
        self.assertEqual(resp.decision.domain, "files")
        self.assertEqual(resp.decision.action, "create")
        self.assertTrue(resp.success)

    def test_intent_routing_send_email(self):
        cmd = "send email with a message"
        resp = self.router.process(cmd)
        self.assertEqual(resp.decision.domain, "mail")
        self.assertEqual(resp.decision.action, "send")
        self.assertTrue(resp.success)

    def test_swahili_intent_routing(self):
        res1 = self.router.process("andika note mpya kuhusu mkutano")
        self.assertEqual(res1.decision.domain, "notes")
        self.assertEqual(res1.decision.action, "create")

        res2 = self.router.process("tengeneza faili jipya")
        self.assertEqual(res2.decision.domain, "files")
        self.assertEqual(res2.decision.action, "create")

        res3 = self.router.process("tuma email")
        self.assertEqual(res3.decision.domain, "mail")
        self.assertEqual(res3.decision.action, "send")


if __name__ == "__main__":
    unittest.main()
