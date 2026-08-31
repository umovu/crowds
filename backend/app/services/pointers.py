"""Pointers — the job the user wants done, orthogonal to mode and depth.

Pure dict + string logic. No LLM, no I/O, so every function is unit-testable
with the model switched off. A pointer never sets the mode (`mode_detector`
keeps deciding) and never changes who is in the room beyond picking which
named `SEGMENTS` slice to draw from. See local-plans/POINTERS_AND_SLOTS.md.

A pointer carries:
  * `slots`         — ordered scaffold fields ({key, label, hint, required}).
  * `seed_slots`    — which slot values are allowed into the assembled seed
                      (`worry` is deliberately excluded: putting the worry in
                      the seed makes the room react to the worry instead of
                      the thing).
  * `summary_contract` — extra instruction appended to the panel summary
                      system prompt.
  * `auto_route`    — pick the segment from the seed text. `fit` refuses: the
                      pick IS the deliverable.

Import direction: this module may import from `panel_service`, never the
reverse (a cycle). If that ever proves awkward, pass `suggest_segments` in as
an argument rather than restructuring.
"""

from typing import Dict, List, Optional

from . import panel_service

# The buyer-shaped subset of SEGMENTS that the `fit` pointer ranks across.
# Six segments × two seats = a 12-person cast, exactly the free-tier cap.
FIT_SEGMENTS = [
    "professionals",
    "small_business",
    "informal_traders",
    "guardians",
    "youth",
    "unemployed",
]

POINTERS = {
    "land": {
        "label": "Test how a message lands",
        "blurb": "The honest first read on what you're putting out.",
        "slots": [
            {"key": "announcement", "label": "What are you putting out?",
             "hint": "A post, a price change, a new feature. Say it the way you'd say it to a person.",
             "required": True},
            {"key": "audience", "label": "Who is it for?",
             "hint": "Leave blank for a general South African mix.",
             "required": False},
            {"key": "change", "label": "What changes for them?",
             "hint": "What they'd have to do, pay, or give up.",
             "required": False},
            {"key": "worry", "label": "What are you worried about?",
             "hint": "One line. This shapes what we probe.",
             "required": False},
        ],
        "seed_slots": ["announcement", "audience", "change"],
        "summary_contract": (
            "Spread the read across warm, flat and negative reactions. "
            "If a specific worry is given below, add one closing line on "
            "whether that worry showed up on its own."
        ),
        "auto_route": True,
    },
    "breaks": {
        "label": "Find what stops people saying yes",
        "blurb": "Blockers only. Same run, sharper question.",
        "slots": [
            {"key": "announcement", "label": "What are you putting out?",
             "hint": "A post, a price change, a new feature. Say it the way you'd say it to a person.",
             "required": True},
            {"key": "audience", "label": "Who is it for?",
             "hint": "Leave blank for a general South African mix.",
             "required": False},
            {"key": "change", "label": "What changes for them?",
             "hint": "What they'd have to do, pay, or give up.",
             "required": False},
            {"key": "worry", "label": "What are you worried about?",
             "hint": "One line. This shapes what we probe.",
             "required": False},
        ],
        "seed_slots": ["announcement", "audience", "change"],
        "summary_contract": (
            "Report blockers only. No praise, no balance. Group the objections "
            "by how often each theme recurred, keeping each person's own words. "
            "Name the conditions that would flip a no to a maybe."
        ),
        "auto_route": True,
    },
    "fit": {
        "label": "Find out which group it's for",
        "blurb": "Same offer, six buyer groups. See who it lands with.",
        "slots": [
            {"key": "offer", "label": "What are you selling?",
             "hint": "The product and what it does.",
             "required": True},
            {"key": "price", "label": "What does it cost?",
             "hint": "Per month, once off, or free.",
             "required": False},
            {"key": "guess", "label": "Who do you think it's for?",
             "hint": "Optional. We'll tell you if you're right.",
             "required": False},
        ],
        "seed_slots": ["offer", "price"],
        "summary_contract": (
            "Answer as a ranked list, not a room. For each segment: how it "
            "landed, the single strongest reason, and the strongest objection. "
            "If a guess is given below, one line on whether it placed in the "
            "top group. Say when two segments are genuinely close rather than "
            "inventing a winner."
        ),
        "auto_route": False,
    },
    "ab": {
        "label": "Compare two ways of saying it",
        "blurb": "Two ways of saying it, one room, side by side.",
        "slots": [
            {"key": "version_a", "label": "Version A",
             "hint": "The first way of saying it.",
             "required": True},
            {"key": "version_b", "label": "Version B",
             "hint": "The second. Change one thing, not everything.",
             "required": True},
            {"key": "audience", "label": "Who is it for?",
             "hint": "Leave blank for a general South African mix.",
             "required": False},
            {"key": "decision", "label": "What are you deciding between?",
             "hint": "Price? Wording? Name?",
             "required": False},
        ],
        "seed_slots": ["version_a", "version_b", "audience", "decision"],
        "summary_contract": (
            "Compare the two versions side by side: who moved between them and "
            "why. If a decision is given below, answer that question directly "
            "in the first line. Where the two are genuinely close, say so "
            "rather than inventing a winner."
        ),
        "auto_route": True,
    },
}


def assemble_seed(pointer: str, slots: Dict[str, str]) -> str:
    """Slots -> seed text, per the templates in POINTERS_AND_SLOTS.md.

    Unknown pointer or empty slots -> "" so callers can fall back to the raw
    pitch. Only keys in `seed_slots` are used. `ab` needs no assembly: each
    version is already a full pitch, so callers pass the version directly.
    """
    if pointer not in POINTERS:
        return ""
    conf = POINTERS[pointer]
    values = {k: (slots.get(k) or "").strip() for k in conf["seed_slots"]}
    if pointer == "ab":
        return ""  # versions are the pitches; nothing to scaffold
    parts = [values.get(conf["slots"][0]["key"]) or ""]
    if pointer in ("land", "breaks"):
        if values.get("audience"):
            parts.append(f"It is aimed at {values['audience']}.")
        if values.get("change"):
            parts.append(f"For them, this means {values['change']}.")
    else:  # fit
        if values.get("price"):
            parts.append(f"It costs {values['price']}.")
    assembled = "\n".join(p for p in parts if p)
    return assembled


def summary_contract(pointer: str, slots: Optional[Dict[str, str]] = None) -> str:
    """The extra summary instruction, or "" when no pointer.

    When a pointer's contract references a specific concern (the `worry` /
    `guess` / `decision` slot), the value is appended so the LLM gets the
    concrete term without any of it touching the seed.
    """
    if pointer not in POINTERS:
        return ""
    conf = POINTERS[pointer]
    text = conf["summary_contract"]
    concern_keys = {"land": "worry", "breaks": "worry",
                    "fit": "guess", "ab": "decision"}
    key = concern_keys.get(pointer)
    if key and slots and (slots.get(key) or "").strip():
        text = f"{text}\nThe {key}: {slots[key].strip()}"
    return text


def route_segments(pointer: str, seed: str) -> List[str]:
    """Auto-routing. `fit` -> FIT_SEGMENTS. `auto_route` pointers -> whatever
    panel_service.suggest_segments returns, or ["everyone"] when it returns
    nothing. Never raises, and unknown pointers are a no-op ([])."""
    if pointer not in POINTERS:
        return []
    if pointer == "fit":
        return list(FIT_SEGMENTS)
    suggested = panel_service.suggest_segments(seed or "")
    return suggested or ["everyone"]


def missing_required(pointer: str, slots: Dict[str, str]) -> List[str]:
    """Required slot keys that are blank, so the API can 400 with a useful
    message instead of running a junk seed. Unknown pointer -> []."""
    if pointer not in POINTERS:
        return []
    return [
        s["key"]
        for s in POINTERS[pointer]["slots"]
        if s["required"] and not (slots.get(s["key"]) or "").strip()
    ]
