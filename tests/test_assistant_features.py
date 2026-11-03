"""Tests for learn & replay, dictation, routines, meetings, updater, agents and the voice-command layer.

Nothing touches the user's real ~/.config/speed_x data or the network.
"""

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["SPEEDX_LLM"] = "0"
os.environ["SPEEDX_CLOUD"] = "0"

from speed_x.core import dictation, meta, updater
from speed_x.core.agents import AgentManager
from speed_x.core.meeting import MeetingManager, summarize
from speed_x.core.routines import RoutineStore, describe_when, parse_routine, parse_time
from speed_x.core.skills import SkillStore, gist, parse_teaching


def tmp() -> Path:
    return Path(tempfile.mkdtemp())


def step(domain, action, **params):
    return {"domain": domain, "action": action, "params": params, "confirm": False}


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.store = SkillStore(tmp() / "skills.json", resolve_app=lambda n: n.title() if n in ("mail", "notes", "safari") else None)

    def test_replay_same_words_any_order_and_filler(self):
        steps = [step("apps", "open", app="Safari"), step("music", "play")]
        self.store.learn("open safari and play music", steps)
        for phrase in ("um, play music and open safari please", "OPEN Safari and play music"):
            hit = self.store.find(phrase)
            self.assertIsNotNone(hit, phrase)
            self.assertEqual([s["action"] for s in hit.steps], ["open", "play"])

    def test_app_pattern_generalises(self):
        self.store.learn("open safari and play music", [step("apps", "open", app="Safari"), step("music", "play")])
        hit = self.store.find("open mail and play music")
        self.assertEqual(hit.steps[0]["params"]["app"], "Mail")
        self.assertIsNone(self.store.find("open zzzz and play music"))

    def test_order_matters_for_words_the_steps_use(self):
        self.store.learn("notes left mail right", [step("w", "place", a="notes", b="left"), step("w", "place", a="mail", b="right")])
        self.assertIsNone(self.store.find("mail left notes right"))

    def test_never_learns_volatile_sensitive_or_deictic(self):
        self.assertIsNone(self.store.learn("tell bob hi", [step("messaging", "send", to="bob", text="hi")]))
        self.assertIsNone(self.store.learn("note milk", [step("notes", "create", text="milk")]))
        self.assertIsNone(self.store.learn("close it and play music", [step("apps", "quit", app="X"), step("music", "play")]))
        s = step("system", "sleep"); s["confirm"] = True
        self.assertIsNone(self.store.learn("night night", [s]))

    def test_failed_replay_dropped_after_two_strikes_but_taught_survives(self):
        self.store.learn("do thing", [step("music", "play")])
        self.assertFalse(self.store.mark_failed("do thing"))
        self.assertTrue(self.store.mark_failed("do thing"))
        self.assertIsNone(self.store.find("do thing"))
        self.store.learn("focus mode", [step("apps", "open", app="Notes")], mine=True)
        for _ in range(5):
            self.store.mark_failed("focus mode")
        self.assertIsNotNone(self.store.find("focus mode"))

    def test_expiry_keeps_taught_drops_stale_learned(self):
        self.store.learn("stale one", [step("music", "play")])
        self.store.learn("mine one", [step("music", "pause")], mine=True)
        for v in self.store._skills.values():
            v["at"] = v["used"] = 1
        self.store._save()
        reloaded = SkillStore(self.store.path)
        self.assertEqual([k for k, _ in reloaded.names()], ["mine one"])

    def test_persistence_roundtrip(self):
        self.store.learn("open safari and play music", [step("apps", "open", app="Safari"), step("music", "play")])
        again = SkillStore(self.store.path)
        self.assertIsNotNone(again.find("play music open safari"))

    def test_teaching_phrases(self):
        self.assertEqual(parse_teaching("When I say focus mode, close slack and open notes")["name"], "focus mode")
        self.assertEqual(parse_teaching("when I say study, open notes")["action"], "open notes")
        self.assertEqual(parse_teaching("forget the shortcut focus mode")["op"], "forget")
        self.assertEqual(parse_teaching("what shortcuts do I have")["op"], "list")
        self.assertIsNone(parse_teaching("open safari"))
        self.assertEqual(gist("um could you open Safari please"), ["open", "safari"])


class TestDictation(unittest.TestCase):
    def setUp(self):
        self.d = dictation.Dictionary(tmp() / "d.json")

    def test_fillers_punctuation_and_caps(self):
        self.assertEqual(dictation.cleanup("um so i think uh we should go comma okay question mark"), "So I think we should go, okay?")

    def test_correction_only_between_numbers(self):
        self.assertEqual(dictation.cleanup("meet at four actually five"), "Meet at five")
        self.assertEqual(dictation.cleanup("i actually like it"), "I actually like it")

    def test_scratch_that_drops_the_clause(self):
        self.assertEqual(dictation.cleanup("send it to bob period send it to alice scratch that send it to carol"), "Send it to bob. Send it to carol")

    def test_new_line_and_paragraph(self):
        self.assertEqual(dictation.cleanup("hello new line world new paragraph bye"), "Hello\nWorld\n\nBye")

    def test_dictionary_snaps_and_replaces(self):
        self.d.add_word("Kilimanjaro")
        self.d.add_replace("my email", "me@example.com")
        out = dictation.cleanup("climb kili man jaro and write my email", self.d)
        self.assertEqual(out, "Climb Kilimanjaro and write me@example.com")
        self.assertFalse(self.d.add_word("kilimanjaro"))  # already there

    def test_dictionary_does_not_mangle_normal_words(self):
        self.d.add_word("Nadina")
        self.assertEqual(dictation.cleanup("play a song now", self.d), "Play a song now")

    def test_stats(self):
        p = tmp() / "s.json"
        dictation.record("one two three", p)
        s = dictation.record("four five", p)
        self.assertEqual((s["today"], s["total"], s["sessions"]), (5, 5, 2))
        self.assertEqual(dictation.read_stats(p)["today"], 5)


class TestRoutines(unittest.TestCase):
    def test_parse_times(self):
        self.assertEqual(parse_time("9am"), (9, 0))
        self.assertEqual(parse_time("8:30 pm"), (20, 30))
        self.assertEqual(parse_time("12am"), (0, 0))
        self.assertEqual(parse_time("noon"), (12, 0))
        self.assertIsNone(parse_time("25:00"))

    def test_parse_routine_forms(self):
        r = parse_routine("every weekday at 8:30 open mail and play music")
        self.assertEqual((r["time"], r["days"], r["command"]), ("08:30", [0, 1, 2, 3, 4], "open mail and play music"))
        self.assertEqual(parse_routine("at 9pm every day, lock screen")["time"], "21:00")
        self.assertEqual(parse_routine("open safari every monday and friday at 7am")["days"], [0, 4])
        self.assertEqual(parse_routine("create a routine: every sunday at noon open notes")["days"], [6])
        self.assertIsNone(parse_routine("open safari"))
        self.assertEqual(describe_when([0, 1, 2, 3, 4], "08:30"), "every weekday at 8:30 AM")

    def test_due_once_per_day_with_grace(self):
        store = RoutineStore(tmp() / "r.json")
        store.add("09:00", list(range(7)), "open mail")
        monday = dt.datetime(2026, 11, 2, 9, 5)  # a Monday
        self.assertEqual(len(store.due(dt.datetime(2026, 11, 2, 8, 59))), 0)
        self.assertEqual(len(store.due(monday)), 1)
        self.assertEqual(len(store.due(monday)), 0)  # not twice
        self.assertEqual(len(store.due(dt.datetime(2026, 11, 3, 9, 50))), 0)  # too late (grace)

    def test_weekday_only_and_persistence_and_remove(self):
        store = RoutineStore(tmp() / "r.json")
        r = store.add("09:00", [0, 1, 2, 3, 4], "open mail")
        self.assertEqual(store.add("09:00", [0, 1, 2, 3, 4], "Open Mail")["id"], r["id"])  # dedup
        self.assertEqual(len(store.due(dt.datetime(2026, 11, 7, 9, 1))), 0)  # Saturday
        again = RoutineStore(store.path)
        self.assertEqual(len(again.items), 1)
        self.assertEqual(len(again.remove("mail")), 1)
        self.assertEqual(again.items, [])


class TestMeeting(unittest.TestCase):
    def test_summary_extracts_actions_decisions_questions(self):
        lines = [
            "We decided to ship on Friday.",
            "I'll send the deck to Sam by tomorrow.",
            "Who owns the billing migration?",
            "Billing migration needs more tests and billing review.",
        ]
        s = summarize(lines)
        self.assertTrue(any("deck" in a for a in s["actions"]))
        self.assertTrue(any("ship" in d for d in s["decisions"]))
        self.assertEqual(s["questions"], ["Who owns the billing migration?"])
        self.assertIn("billing", s["topics"])

    def test_session_saves_markdown(self):
        m = MeetingManager(tmp(), recap=lambda t: "A short recap.")
        self.assertFalse(m.add_line("nothing yet"))
        m.start("Weekly Sync")
        m.add_line("I will write the report.")
        m.add_line("I will write the report.")  # duplicate partial dropped
        m.add_note("Remember budget")
        path = m.stop()
        text = path.read_text()
        self.assertIn("# Weekly Sync", text)
        self.assertIn("- [ ] I will write the report.", text)
        self.assertIn("A short recap.", text)
        self.assertEqual(text.count("I will write the report."), 2)  # action + transcript, not 3
        self.assertIn("Remember budget", m.last_summary())
        self.assertFalse(m.active)


class TestUpdater(unittest.TestCase):
    def test_version_compare(self):
        self.assertTrue(updater.is_newer("1.0.1", "1.0.0"))
        self.assertTrue(updater.is_newer("v1.1", "1.0.9"))
        self.assertFalse(updater.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(updater.is_newer("0.9.9", "1.0.0"))

    def test_check_and_download_verifies_size(self):
        rel = {"tag_name": "v9.9.9", "html_url": "https://example/r", "body": "x",
               "assets": [{"name": "SpeedX.dmg", "browser_download_url": "https://example/a.dmg", "size": 4}]}
        info = updater.check(fetch=lambda url, timeout=6.0: json.dumps(rel).encode())
        self.assertTrue(info["newer"])
        opened = []
        ok, _ = updater.download_and_open(info, dest=tmp(), fetch=lambda u, t=0: b"1234", opener=opened.append)
        self.assertTrue(ok and len(opened) == 1)
        ok, msg = updater.download_and_open(info, dest=tmp(), fetch=lambda u, t=0: b"12", opener=opened.append)
        self.assertFalse(ok)
        self.assertEqual(len(opened), 1)  # a short download is never opened

    def test_offline_is_not_an_error(self):
        def boom(url, timeout=6.0):
            raise OSError("offline")
        self.assertFalse(updater.check(fetch=boom)["ok"])

    def test_non_https_asset_refused(self):
        ok, _ = updater.download_and_open({"dmg_url": "http://evil/x.dmg"}, dest=tmp())
        self.assertFalse(ok)


class TestAgents(unittest.TestCase):
    def test_runs_and_can_stop(self):
        mgr = AgentManager()
        def runner(cmd, agent):
            agent.steps = [{"label": "x", "success": True}]
            agent.status = "done"
        a = mgr.start("open mail", runner, sync=True)
        self.assertEqual(a.status, "done")
        b = mgr.start("slow", lambda c, ag: None, sync=True)
        self.assertEqual(mgr.stop("nope"), [])
        self.assertEqual([x.id for x in mgr.list()], [a.id, b.id])

    def test_runner_crash_is_contained(self):
        mgr = AgentManager()
        def runner(cmd, agent):
            raise ValueError("bad")
        a = mgr.start("x", runner, sync=True)
        self.assertEqual(a.status, "failed")


class TestMeta(unittest.TestCase):
    def route(self, text):
        found = meta.match(text)
        return (found[0].domain, found[0].action, found[0].params) if found else None

    def test_routing(self):
        self.assertEqual(self.route("list routines")[:2], ("routines", "list"))
        self.assertEqual(self.route("every day at 7am play music")[:2], ("routines", "add"))
        self.assertEqual(self.route("add Nadina to my dictionary")[2], {"word": "Nadina"})
        self.assertEqual(self.route("start a meeting called Weekly Sync")[2], {"title": "Weekly Sync"})
        self.assertEqual(self.route("end meeting")[:2], ("meeting", "stop"))
        self.assertEqual(self.route("meeting note: call Sam")[2], {"text": "call Sam"})
        self.assertEqual(self.route("open calculator in the background")[2], {"command": "open calculator"})
        self.assertEqual(self.route("show me where the share button is")[2], {"query": "share button"})
        self.assertEqual(self.route("turn on wake word")[:2], ("ui", "wake_on"))
        self.assertEqual(self.route("Speed X, check for updates")[:2], ("update", "check"))

    def test_install_update_needs_confirmation(self):
        self.assertTrue(meta.match("install the update")[0].requires_confirmation)

    def test_ordinary_commands_pass_through(self):
        for text in ("open safari", "play music", "set a timer for ten minutes", "what time is it"):
            self.assertIsNone(meta.match(text), text)


class TestRouterLearning(unittest.TestCase):
    """End to end: a multi-step plan is learned and replayed; a stale replay falls back."""

    def setUp(self):
        from speed_x.core import router as router_mod
        from speed_x.tools.base import ToolResult, registry

        self.router_mod = router_mod
        self.store = SkillStore(tmp() / "s.json", resolve_app=lambda n: None)
        p = mock.patch.object(router_mod, "skills", self.store)
        p.start()
        self.addCleanup(p.stop)
        self.calls = []
        self.fail_music = False
        outer = self

        class Fake:
            def execute(self, action, params=None):
                outer.calls.append(action)
                if action == "play" and outer.fail_music:
                    return ToolResult(False, "no")
                return ToolResult(True, "ok")

        for name in ("apps", "music"):
            p = mock.patch.dict(registry._tools, {name: Fake()})
            p.start()
            self.addCleanup(p.stop)
        self.router = router_mod.CommandRouter()

    def test_learn_then_replay_skips_the_brain(self):
        r = self.router
        first = r.process("open safari and play music")
        self.assertTrue(first.success)
        self.assertEqual(len(self.store.names()), 1)
        with mock.patch.object(r.brain, "plan", side_effect=AssertionError("brain must not run")):
            second = r.process("play music and open safari")
        self.assertTrue(second.success)
        self.assertEqual(second.steps[0].decision.source, "skill")

    def test_failed_replay_falls_back_and_strikes(self):
        r = self.router
        r.process("open safari and play music")
        key = self.store.names()[0][0]
        self.fail_music = True
        resp = r.process("open safari and play music")
        self.assertFalse(resp.success)
        self.assertEqual(self.store._skills[key]["fails"], 1)  # struck once, then the brain redid it (no loop)


if __name__ == "__main__":
    unittest.main()
