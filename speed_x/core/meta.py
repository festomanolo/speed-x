"""Voice-command layer for Speed-X's own features (shortcuts, routines, dictionary, meetings,
updates, background agents, on-screen guide). Runs before the general brain so these phrases
never get mistaken for app/music commands. Returns typed decisions, or None."""

import re
from typing import List, Optional

from .brain import IntentDecision
from .routines import parse_routine
from .skills import parse_teaching


def _d(domain: str, act: str, said: str, **params) -> List[IntentDecision]:
    return [IntentDecision(domain, act, params, 0.97, False, "meta", said)]


def match(text: str) -> Optional[List[IntentDecision]]:
    t = re.sub(r"\s+", " ", text.strip())
    t = re.sub(r"^(?:hey |ok |okay )?(?:speed ?x|speedx)[,:]?\s+", "", t, flags=re.I)
    low = t.lower().rstrip(".!? ")

    # --- shortcuts the user teaches -------------------------------------------------------
    teach = parse_teaching(t)
    if teach:
        if teach["op"] == "teach":
            return _d("skills", "teach", t, name=teach["name"], action=teach["action"])
        if teach["op"] == "forget":
            return _d("skills", "forget", t, name=teach["name"])
        return _d("skills", "list", t)

    # --- routines -------------------------------------------------------------------------
    if re.fullmatch(r"(?:list|show|what are)(?: all)?(?: my)? routines?", low):
        return _d("routines", "list", t)
    m = re.fullmatch(r"(?:remove|delete|cancel|stop) (?:the )?routine (.+)", low)
    if m:
        return _d("routines", "remove", t, ref=m[1])
    r = parse_routine(t)
    if r:
        return _d("routines", "add", t, **r)

    # --- dictionary / dictation -----------------------------------------------------------
    m = re.fullmatch(r"(?:add|put) (.+?) (?:to|in|into) (?:my )?dictionary", t.rstrip(".!? "), re.I)
    if m:
        return _d("dictation", "add_word", t, word=m[1].strip(" \"'“”"))
    m = re.fullmatch(r"(?:remove|delete) (.+?) from (?:my )?dictionary", t.rstrip(".!? "), re.I)
    if m:
        return _d("dictation", "remove", t, word=m[1].strip(" \"'“”"))
    m = re.fullmatch(r"(?:in )?(?:my )?dictionary[,:]? [\"“']?(.+?)[\"”']? (?:means|is|becomes|should be) [\"“']?(.+?)[\"”']?", t.rstrip(".!? "), re.I)
    if m:
        return _d("dictation", "add_replace", t, heard=m[1], written=m[2])
    if re.fullmatch(r"(?:show|list|what(?:'s| is) in)(?: me)?(?: my)? dictionary", low):
        return _d("dictation", "list", t)
    if re.fullmatch(r"(?:dictation|typing) (?:stats|statistics)|how much have i dictated", low):
        return _d("dictation", "stats", t)

    # --- meetings -------------------------------------------------------------------------
    m = re.fullmatch(r"(?:start|begin)(?: a| the)? meeting(?: notes| copilot)?(?:\s+(?:called|named|about|for|on)\s+(.+))?", t.rstrip(".!? "), re.I)
    if m:
        return _d("meeting", "start", t, title=(m[1] or "").strip())
    if re.fullmatch(r"(?:end|stop|finish)(?: the| this)? meeting(?: notes)?", low):
        return _d("meeting", "stop", t)
    m = re.fullmatch(r"(?:meeting )?note[:,]? (.+)|note for the meeting[:,]? (.+)", t.rstrip(".!? "), re.I)
    if m and low.startswith(("meeting note", "note for the meeting")):
        return _d("meeting", "note", t, text=(m[1] or m[2]).strip())
    if re.fullmatch(r"(?:show|read)(?: me)?(?: my)?(?: the)?(?: last| latest)? meeting (?:notes|summary)|what did we decide", low):
        return _d("meeting", "last", t)
    if re.fullmatch(r"(?:list|show)(?: my)? meetings", low):
        return _d("meeting", "list", t)

    # --- updates --------------------------------------------------------------------------
    if re.fullmatch(r"(?:check for )?(?:speed ?x )?updates?|is there an update|check for (?:a )?(?:new )?version", low):
        return _d("update", "check", t)
    if re.fullmatch(r"(?:install|download|get) (?:the |an? )?(?:speed ?x )?update|update speed ?x|update yourself", low):
        return [IntentDecision("update", "install", {}, 0.97, True, "meta", t)]

    # --- background agents ----------------------------------------------------------------
    if re.fullmatch(r"(?:list|show)(?: my)?(?: background)? agents?", low):
        return _d("agents", "list", t)
    m = re.fullmatch(r"stop (?:all )?agents?(?: (.+))?", low)
    if m:
        return _d("agents", "stop", t, ref=(m[1] or "all").replace("agent ", "").strip())
    m = re.fullmatch(r"(?:in the background|in background|background|bg)[,:]?\s+(.+)", t.rstrip(".!? "), re.I) or re.fullmatch(
        r"(.+?)\s+in the background", t.rstrip(".!? "), re.I
    )
    if m:
        return _d("agents", "start", t, command=m[1].strip())

    # --- on-screen guide ------------------------------------------------------------------
    m = re.fullmatch(
        r"(?:show me where|where(?: do i| can i| should i)? (?:click|find|tap|press)|point (?:to|at)|highlight|circle)\s+(?:is |are |the |to |on )*(.+?)(?: is| are)?",
        t.rstrip(".!? "),
        re.I,
    )
    if m:
        return _d("ui", "show_where", t, query=m[1].strip())
    m = re.fullmatch(r"where(?:'s| is) (?:the )?(.+? (?:button|menu|icon|tab|toggle|field|checkbox|setting|option))", t.rstrip(".!? "), re.I)
    if m:
        return _d("ui", "show_where", t, query=m[1].strip())
    if re.fullmatch(r"(?:start|turn on|enable) (?:drawing|draw mode|the pen)|draw on (?:the )?screen", low):
        return _d("ui", "draw_start", t)
    if re.fullmatch(r"(?:stop|end|turn off|disable) (?:drawing|draw mode|the pen)", low):
        return _d("ui", "draw_stop", t)
    if re.fullmatch(r"clear (?:the |my )?(?:drawing|screen drawing|pen)", low):
        return _d("ui", "draw_clear", t)
    if re.fullmatch(r"(?:turn on|enable|start) (?:the )?wake ?word|always listen", low):
        return _d("ui", "wake_on", t)
    if re.fullmatch(r"(?:turn off|disable|stop) (?:the )?wake ?word", low):
        return _d("ui", "wake_off", t)
    if re.fullmatch(r"(?:check|open|show)(?: my)? (?:permissions|setup|onboarding)|set ?up speed ?x", low):
        return _d("ui", "permissions", t)
    return None
