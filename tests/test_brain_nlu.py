"""Tests for the layered decision brain: normalisation, durations, multi-step plans, fuzzy matching.

Everything here only *decides*; no tool is executed.
"""

import os
import unittest

os.environ["SPEEDX_LLM"] = "0"  # deterministic: rules + semantic layers only
os.environ["SPEEDX_CLOUD"] = "0"

from speed_x.core.brain import LayaBrain
from speed_x.core.nlu import normalize, parse_duration, parse_number, split_commands
from speed_x.core.router import CommandRouter, describe


class TestNLU(unittest.TestCase):
    def test_normalize_strips_wake_words_and_dictation_punctuation(self):
        self.assertEqual(
            normalize("Hey Speed X, can you please turn the volume up."), "turn the volume up"
        )
        self.assertEqual(normalize("Open Safari."), "Open Safari")
        self.assertEqual(normalize("Tafadhali cheza muziki sasa"), "cheza muziki")

    def test_numbers(self):
        self.assertEqual(parse_number("twenty five"), 25)
        self.assertEqual(parse_number("kumi na tano"), 15)
        self.assertEqual(parse_number("hamsini"), 50)
        self.assertEqual(parse_number("80 percent"), 80)

    def test_durations_english_and_swahili(self):
        self.assertEqual(parse_duration("ten minutes"), 600)
        self.assertEqual(parse_duration("an hour and a half"), 5400)
        self.assertEqual(parse_duration("1 hour 30 minutes"), 5400)
        self.assertEqual(parse_duration("half an hour"), 1800)
        self.assertEqual(parse_duration("dakika tano"), 300)
        self.assertEqual(parse_duration("dakika kumi na tano"), 900)
        self.assertEqual(parse_duration("saa moja na nusu"), 5400)

    def test_split(self):
        self.assertEqual(
            split_commands("open safari and then play music"), ["open safari", "play music"]
        )


class TestBrain(unittest.TestCase):
    def setUp(self):
        self.brain = LayaBrain()
        self.router = CommandRouter(self.brain)

    def plan(self, text):
        return [(d.domain, d.action) for d in self.router.preview(text)]

    def test_compound_command_becomes_two_steps(self):
        self.assertEqual(
            self.plan("open safari and play music"), [("apps", "open"), ("music", "play")]
        )
        self.assertEqual(
            self.plan("set a timer for ten minutes and remind me to water the plants"),
            [("timer", "set"), ("timer", "remind")],
        )

    def test_play_specific_song(self):
        steps = self.router.preview("open music and play nadina song")
        self.assertEqual(
            [(d.domain, d.action) for d in steps], [("apps", "open"), ("music", "play_song")]
        )
        self.assertEqual(steps[1].params, {"query": "nadina", "player": "Music"})
        song = self.router.preview("play shape of you by ed sheeran on spotify")[0].params
        self.assertEqual(
            song, {"query": "shape of you", "artist": "ed sheeran", "player": "Spotify"}
        )
        self.assertEqual(self.router.preview("cheza wimbo wa nadina")[0].params["query"], "nadina")
        self.assertEqual(self.plan("play some music"), [("music", "play")])
        self.assertEqual(self.plan("play the next one"), [("music", "next")])

    def test_content_with_and_stays_one_step(self):
        steps = self.router.preview("write a new note buy milk and eggs")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].params["body"], "buy milk and eggs")

    def test_redundant_open_is_dropped(self):
        self.assertEqual(self.plan("open notes app and write a new note"), [("notes", "create")])

    def test_volume_levels(self):
        d = self.brain.decide("Turn the volume up to 80 percent")
        self.assertEqual((d.action, d.params["level"]), ("set_volume", 80))
        d = self.brain.decide("weka sauti hamsini")
        self.assertEqual((d.action, d.params["level"]), ("set_volume", 50))

    def test_resume_the_document_is_not_music(self):
        d = self.brain.decide("where is my resume")
        self.assertEqual((d.domain, d.action, d.params["query"]), ("files", "search", "resume"))

    def test_reminders(self):
        d = self.brain.decide("remind me in 20 minutes to call mom")
        self.assertEqual((d.params["text"], d.params["seconds"]), ("call mom", 1200))
        d = self.brain.decide("nikumbushe kunywa maji baada ya dakika kumi")
        self.assertEqual((d.params["text"], d.params["seconds"]), ("kunywa maji", 600))

    def test_web(self):
        d = self.brain.decide("search for best pizza near me")
        self.assertEqual(
            (d.domain, d.action, d.params["query"]), ("web", "search", "best pizza near me")
        )
        d = self.brain.decide("play lofi beats on youtube")
        self.assertEqual((d.domain, d.action), ("web", "youtube"))
        d = self.brain.decide("go to github.com")
        self.assertEqual((d.domain, d.action), ("web", "open_url"))

    def test_spoken_email(self):
        d = self.brain.decide(
            "send email to alice at example dot com saying the meeting moved to 3"
        )
        self.assertEqual(d.params["recipient"], "alice@example.com")
        self.assertEqual(d.params["message"], "the meeting moved to 3")

    def test_filename(self):
        self.assertEqual(
            self.brain.decide("make a new file named todo.txt").params["filename"], "todo.txt"
        )
        self.assertEqual(
            self.brain.decide("create a file called notes dot md").params["filename"], "notes.md"
        )

    def test_semantic_layer_tolerates_asr_typos(self):
        d = self.brain.decide("valume up")
        self.assertEqual((d.domain, d.action, d.source), ("system", "volume_up", "semantic"))
        d = self.brain.decide("start the music")
        self.assertEqual((d.domain, d.action), ("music", "play"))

    def test_unknown_offers_suggestion(self):
        resp = self.router.process("wat time is it")
        self.assertFalse(resp.success)
        self.assertEqual(resp.suggestion, "what time is it")

    def test_pronoun_uses_last_opened_app(self):
        self.brain.last_app = "Calculator"
        d = self.brain.decide("close it")
        self.assertEqual((d.action, d.params["app"]), ("quit", "Calculator"))
        self.assertTrue(d.requires_confirmation)

    def test_preview_does_not_touch_context(self):
        self.brain.last_app = None
        self.router.preview("open calculator")
        self.assertIsNone(self.brain.last_app)

    def test_whatsapp_message_with_typo(self):
        steps = self.router.preview("open whatsapp and send message to manolo sayinh hi")
        self.assertEqual([(d.domain, d.action) for d in steps], [("messaging", "send")])
        self.assertEqual(steps[0].params, {"to": "manolo", "text": "hi", "app": "WhatsApp"})

    def test_message_phrasings(self):
        d = self.brain.decide("mwambie Juma kwamba nimefika")
        self.assertEqual((d.params["to"], d.params["text"]), ("Juma", "nimefika"))
        d = self.brain.decide("text mom that I'm on my way")
        self.assertEqual((d.params["to"], d.params["text"]), ("mom", "I'm on my way"))
        d = self.brain.decide("send hi to manolo on whatsapp")
        self.assertEqual((d.params["to"], d.params["app"]), ("manolo", "WhatsApp"))

    def test_open_whatsapp_then_message_without_and_or_saying(self):
        cases = {
            "open whatsapp send message to manolo saying hi": ("manolo", "hi"),
            "Open WhatsApp. Send message to Manolo saying hi.": ("Manolo", "hi"),
            "open whatsapp and send a message to manolo hi how are you": (
                "manolo",
                "hi how are you",
            ),
            "open whatsapp then message john hello there": ("john", "hello there"),
            "open whatsapp and tell john I'll be late": ("john", "I'll be late"),
            "fungua whatsapp tuma ujumbe kwa juma kwamba nimefika": ("juma", "nimefika"),
        }
        for phrase, (to, text) in cases.items():
            with self.subTest(phrase=phrase):
                steps = self.router.preview(phrase)
                self.assertEqual([(d.domain, d.action) for d in steps], [("messaging", "send")])
                self.assertEqual(
                    (steps[0].params["to"], steps[0].params["text"], steps[0].params["app"]),
                    (to, text, "WhatsApp"),
                )

    def test_message_name_and_text_without_saying(self):
        d = self.brain.decide("message john hello")
        self.assertEqual(
            (d.domain, d.params["to"], d.params["text"]), ("messaging", "john", "hello")
        )
        d = self.brain.decide("send message to Festo Manolo hello")
        self.assertEqual((d.params["to"], d.params["text"]), ("Festo Manolo", "hello"))
        d = self.brain.decide("open whatsapp send message to manolo")
        self.assertEqual(
            (d.params["to"], d.params["text"], d.params["app"]), ("manolo", "", "WhatsApp")
        )
        # Not messages:
        self.assertNotEqual(self.brain.decide("tell me a joke").domain, "messaging")
        self.assertNotEqual(self.brain.decide("tell john about the meeting").domain, "messaging")

    def test_sentence_is_never_an_app_name(self):
        d = self.brain.decide("open whatsapp and send message to manolo saying hi please now")
        self.assertNotEqual(
            d.params.get("app"), "whatsapp and send message to manolo saying hi please now"
        )

    def test_questions_are_answered(self):
        self.assertEqual(self.plan("eleza jinsi ya kupika chai"), [("assistant", "ask")])
        self.assertEqual(
            self.plan("open safari and tell me a joke"), [("apps", "open"), ("assistant", "ask")]
        )

    def test_content_reasoning_reads_then_thinks(self):
        self.assertEqual(
            self.plan("summarize what's on my screen"), [("screen", "read"), ("assistant", "think")]
        )
        self.assertEqual(
            self.plan("translate my clipboard to Swahili"),
            [("clipboard", "read"), ("assistant", "think")],
        )

    def test_chained_rule_steps(self):
        self.assertEqual(
            self.plan("nataka kusikiliza muziki kwa sauti ndogo"),
            [("system", "set_volume"), ("music", "play")],
        )

    def test_describe(self):
        self.assertEqual(describe(self.brain.decide("set a timer for 5 minutes")), "Timer · 5 min")


if __name__ == "__main__":
    unittest.main()
