"""Tests for stateful tools: persisted timers, voice-editable workspaces, and their rules.

Nothing here touches the user's real ~/.config/speed_x data or launches apps.
"""

import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ["SPEEDX_LLM"] = "0"
os.environ["SPEEDX_CLOUD"] = "0"

from speed_x.core.brain import LayaBrain
from speed_x.core.memory import memory
from speed_x.tools import timer as timer_mod
from speed_x.tools import workspaces as ws_mod


class TestTimerPersistence(unittest.TestCase):
    def setUp(self):
        self.store = Path(tempfile.mkdtemp()) / "timers.json"
        self.fired = []
        patcher = mock.patch.object(timer_mod, "_notify", lambda title, msg: self.fired.append(msg))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_timer_is_saved_and_restored(self):
        first = timer_mod.TimerTool(store=self.store)
        first.execute("set", {"seconds": 600, "label": "tea"})
        self.assertEqual(json.loads(self.store.read_text())[0]["label"], "tea")
        for t in first._timers:
            t["handle"].cancel()  # simulate the engine stopping

        second = timer_mod.TimerTool(store=self.store)
        self.assertEqual([t["label"] for t in second._timers], ["tea"])
        self.assertIn("tea", second.execute("list").message)
        second.execute("cancel")
        self.assertEqual(json.loads(self.store.read_text()), [])

    def test_timer_missed_while_off_notifies_once(self):
        self.store.write_text(
            json.dumps(
                [
                    {"label": "oven", "ends": time.time() - 60},
                    {"label": "old", "ends": time.time() - 2 * 86400},
                ]
            )
        )
        tool = timer_mod.TimerTool(store=self.store)
        self.assertEqual([t["label"] for t in tool._timers], ["oven"])  # stale one dropped
        tool._timers[0]["handle"].join(3)
        self.assertEqual(len(self.fired), 1)
        self.assertIn("while Speed-X was off", self.fired[0])
        self.assertEqual(json.loads(self.store.read_text()), [])


class TestWorkspaces(unittest.TestCase):
    def setUp(self):
        saved = copy.deepcopy(memory._data)
        self.addCleanup(setattr, memory, "_data", saved)
        for patcher in (
            mock.patch.object(memory, "save", lambda: None),
            mock.patch.object(ws_mod, "resolve_app", lambda name: name.title()),
            mock.patch.object(ws_mod, "running_app_names", lambda: ["Finder", "Safari", "Figma"]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tool = ws_mod.WorkspaceTool()

    def test_create_add_save_delete(self):
        res = self.tool.execute(
            "create", {"workspace": "Writing", "apps": "pages, safari and notes"}
        )
        self.assertTrue(res.success)
        self.assertEqual(memory.get_workspace("writing")["apps"], ["Pages", "Safari", "Notes"])

        self.tool.execute("add", {"workspace": "writing", "apps": "slack"})
        self.assertEqual(memory.get_workspace("writing")["apps"][-1], "Slack")

        self.tool.execute("save_current", {"workspace": "design"})
        self.assertEqual(
            memory.get_workspace("design")["apps"], ["Safari", "Figma"]
        )  # Finder left out

        self.assertTrue(self.tool.execute("delete", {"workspace": "writing"}).success)
        self.assertIsNone(memory.get_workspace("writing"))
        self.assertFalse(self.tool.execute("delete", {"workspace": "writing"}).success)


class TestSpotifyLookup(unittest.TestCase):
    def test_play_song_resolves_uri_then_plays_it(self):
        from speed_x.tools import music as music_mod
        from speed_x.tools import spotify_api

        responses = iter(
            [
                {"access_token": "tok", "expires_in": 3600},
                {
                    "tracks": {
                        "items": [
                            {
                                "uri": "spotify:track:abc",
                                "name": "Nadina",
                                "artists": [{"name": "Mbosso"}],
                            }
                        ]
                    }
                },
            ]
        )

        class Res:
            def __init__(self, body):
                self.body = json.dumps(body).encode()

            def read(self, *a):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        scripts = []
        tool = music_mod.MusicTool()
        tool._run_applescript = lambda s, timeout=8.0: scripts.append(s) or ""
        with (
            mock.patch.object(spotify_api, "credentials", lambda: ("id", "secret")),
            mock.patch.object(spotify_api, "_token", ("", 0.0)),
            mock.patch.object(
                spotify_api.urllib.request, "urlopen", lambda req, timeout: Res(next(responses))
            ),
        ):
            res = tool.execute("play_song", {"query": "nadina", "player": "Spotify"})
        self.assertTrue(res.success)
        self.assertEqual(res.message, "Playing Nadina by Mbosso on Spotify.")
        self.assertEqual(scripts, ['tell application "Spotify" to play track "spotify:track:abc"'])


class TestNewRules(unittest.TestCase):
    def setUp(self):
        self.brain = LayaBrain()

    def decide(self, text):
        steps = self.brain.plan(text, allow_llm=False, commit=False)
        self.assertEqual(len(steps), 1, steps)
        return steps[0].domain, steps[0].action, steps[0].params

    def test_workspace_voice_commands(self):
        self.assertEqual(
            self.decide("create a workspace called writing with pages and safari"),
            ("workspaces", "create", {"workspace": "writing", "apps": "pages and safari"}),
        )
        self.assertEqual(
            self.decide("save my current apps as design")[:2], ("workspaces", "save_current")
        )
        self.assertEqual(
            self.decide("add slack to the coding workspace")[:2], ("workspaces", "add")
        )
        self.assertEqual(
            self.decide("start writing workspace"),
            ("workspaces", "activate", {"workspace": "writing"}),
        )
        self.assertTrue(
            self.brain.plan("delete the writing workspace", allow_llm=False, commit=False)[
                0
            ].requires_confirmation
        )

    def test_clipboard_and_window(self):
        self.assertEqual(self.decide("clear my clipboard")[:2], ("clipboard", "clear"))
        self.assertEqual(self.decide("what window am i in")[:2], ("screen", "active_window"))
        self.assertEqual(self.decide("niko kwenye app gani")[:2], ("screen", "active_window"))


if __name__ == "__main__":
    unittest.main()
