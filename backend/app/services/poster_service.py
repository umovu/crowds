"""
PosterService — turn an uploaded poster into a text brief.

The whole point of the split: the vision model reads the image ONCE, into words.
Personas only ever see those words, so a panel of 40 costs one vision call, not
forty. It also keeps the hard rule enforceable — the reader describes the poster
and nothing else. It does not decide who should see it (that stays with the
curated library) and it does not score anything.

The reader is an interface so the upload → brief → pitch path is testable with
the model switched off. `StubPosterReader` needs no key and no network.
"""

import json
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Protocol, Tuple

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("fub.poster_service")

ALLOWED_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}

MAX_BYTES = 8 * 1024 * 1024
ACTION_LABELS = (
    "buy", "sign_up", "apply", "contact", "visit", "attend", "vote", "donate", "none", "unclear",
)
CHANNEL_LABELS = (
    "whatsapp", "call", "sms_ussd", "website", "app", "in_person", "qr_code", "none",
)

# What the vision model is asked for. Description only: every word on the
# poster, what is pictured, the layout, the claim. Deliberately NOT asked: who
# it is aimed at, which segment it suits, or how well it would perform.
READ_PROMPT = """You are looking at a poster or advertisement, most likely from South Africa.

Describe it so that someone who cannot see it understands exactly what is on it.

Use exactly these headings, in this order, and nothing else. Write the
heading, then your answer under it. Do not restate the instructions.

TEXT ON THE POSTER
    Every word, transcribed exactly, including the small print. After each
    piece, note how prominent it is: headline, body, or footnote. For any
    price or amount, say whether it sits in its own bubble, box, or large
    type, or just inside a sentence.

WHAT IS PICTURED
    People (apparent age, dress), objects, setting, logos, branding. Say so
    plainly if the poster is text only.

LAYOUT
    What the eye hits first, second, third.

CLAIMS
    Two parts. Write them under these two headings, exactly:
    States outright: what the poster writes in plain words. Transcribe it;
    do not interpret or add.
    Implies: what the poster never says, but invites a reader to infer —
    unstated benefits, a cost hidden by wording like "from only", a reward
    implied to be proven. This part must be different from the stated part:
    do not repeat a stated claim, and must not restate an idea already said.
    If there is no real implication, write: none

THE ASK
    What the reader is asked to do, and how to do it.

PRICE SHOWN
    One line per amount. For every price, fee or amount that appears, write
    the figure and whether it is recurring and over what period (for example
    per month, per year, once, or unclear). If no amount appears anywhere,
    write: none

LABELS
    Write exactly three lines, nothing else under this heading:
    primary action: <label>
    secondary action: <label or none>
    channel: <label>
    Primary and secondary must each be one of: buy, sign_up, apply, contact,
    visit, attend, vote, donate, none, unclear.
    Channel must be one of: whatsapp, call, sms_ussd, website, app, in_person,
    qr_code, none.
    Do not invent a label. If the ask is not clear, use unclear.

    Decide the two labels from the poster's own elements, not from intent:
    - The main button or call is the primary action.
    - A price or amount in its own bubble, box, or large type, sitting apart
      from the button, is a second ask of its own: secondary action is buy.
      Do not fold that price into the primary ask.
    - No such separate second ask: secondary action must be none.
    - Three competing asks: primary is unclear, secondary is none.
    Never more than two asks.

Report only what is actually on the poster. Do not judge whether it is good.
Do not say who it is aimed at, do not describe an audience or a market, and do
not guess who would respond to it. Choosing who sees this is not your job.
"""

# Poster-shaped questions. A poster is met while scrolling, so the useful
# reactions are about attention and trust, not willingness to pay. No question
# here asks for a click probability or any other score.
# Stable short ids — answers are keyed by these, never by array index.
POSTER_QUESTION_SPECS: List[Tuple[str, str]] = [
    ("ask", "What is this asking you to do?"),
    ("attention", "Would you stop scrolling for this, or keep going? Say why."),
    ("off", "What feels off about it, if anything?"),
    ("trust", "Do you trust whoever is behind this? What would make you trust them more?"),
]
POSTER_QUESTIONS = [q for _, q in POSTER_QUESTION_SPECS]
POSTER_QUESTION_IDS = [qid for qid, _ in POSTER_QUESTION_SPECS]

BRIEF_HEADINGS = (
    "TEXT ON THE POSTER",
    "WHAT IS PICTURED",
    "LAYOUT",
    "CLAIMS",
    "THE ASK",
    "PRICE SHOWN",
)

EMPTY_FIELDS = {
    "text": "",
    "pictured": "",
    "layout": "",
    "claims_stated": "",
    "claims_implied": "",
    "ask": "",
    "price": "",
}


class PosterReader(Protocol):
    """Reads image bytes into a text brief."""

    def read(self, image_bytes: bytes, mime_type: str) -> str: ...


class VisionPosterReader:
    """The real reader — one call to the vision tier per poster."""

    def __init__(self, max_tokens: int = 8000, temperature: float = 0):
        self.max_tokens = max_tokens
        self.temperature = temperature

    def read(self, image_bytes: bytes, mime_type: str) -> str:
        client = LLMClient.for_vision()
        text = client.chat(
            messages=[LLMClient.image_message(READ_PROMPT, image_bytes, mime_type)],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if not text.strip():
            # Reasoning models spend the whole budget thinking when it is tight.
            raise RuntimeError(
                "The vision model returned nothing. Raise max_tokens and retry."
            )
        stats = client.get_stats()
        logger.info(
            f"Poster read with {client.model}: "
            f"{stats['prompt_tokens']}+{stats['completion_tokens']} tokens, "
            f"${stats['estimated_cost_usd']:.4f}"
        )
        return text.strip()


class StubPosterReader:
    """Fixed brief, no model. Lets the upload → brief → pitch path be asserted
    with the LLM switched off."""

    def __init__(self, brief: Optional[str] = None):
        self.brief = brief or (
            "TEXT ON THE POSTER\n"
            "SAVE R500, GET R7 000 BACK. (headline)\n"
            "Join before 31 July. (body)\n\n"
            "WHAT IS PICTURED\n"
            "A family and a savings logo.\n\n"
            "LAYOUT\n"
            "Headline first, then offer and button.\n\n"
            "CLAIMS\n"
            "It states outright that you save R500, and separately, what it only implies: a December payout.\n\n"
            "THE ASK\n"
            "Sign up by WhatsApp before 31 July.\n\n"
            "PRICE SHOWN\n"
            "R500 per month\n\n"
            "LABELS\n"
            "primary: sign_up\n"
            "secondary: buy\n"
            "channel: whatsapp"
        )

    def read(self, image_bytes: bytes, mime_type: str) -> str:
        return self.brief


def _poster_dir(poster_id: str) -> str:
    return os.path.join(Config.POSTER_DATA_DIR, poster_id)


def save_poster(image_bytes: bytes, mime_type: str, filename: str = "") -> Dict:
    """Persist an uploaded poster under DATA_ROOT, the same way sims and panels
    persist. Returns the stored record without a brief."""
    if mime_type not in ALLOWED_MIME:
        raise ValueError(
            f"Unsupported image type '{mime_type}'. Use PNG, JPG or WebP."
        )
    if not image_bytes:
        raise ValueError("Empty upload")
    if len(image_bytes) > MAX_BYTES:
        raise ValueError(
            f"Image is {len(image_bytes) / 1e6:.1f} MB — the limit is "
            f"{MAX_BYTES / 1e6:.0f} MB."
        )

    poster_id = f"poster_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    directory = _poster_dir(poster_id)
    os.makedirs(directory, exist_ok=True)

    image_path = os.path.join(directory, f"poster{ALLOWED_MIME[mime_type]}")
    with open(image_path, "wb") as fh:
        fh.write(image_bytes)

    record = {
        "poster_id": poster_id,
        "filename": filename,
        "mime_type": mime_type,
        "bytes": len(image_bytes),
        "image_path": image_path,
        "created_at": datetime.now().isoformat(),
        "brief": None,
        "fields": dict(EMPTY_FIELDS),
        "ask_label_primary": None,
        "ask_label_secondary": None,
        "channel": None,
        "brief_edited": False,
        "frozen": False,
    }
    _write_record(poster_id, record)
    return record


def _write_record(poster_id: str, record: Dict) -> None:
    with open(os.path.join(_poster_dir(poster_id), "poster.json"), "w",
              encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)


def get_poster(poster_id: str) -> Optional[Dict]:
    path = os.path.join(_poster_dir(poster_id), "poster.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_poster(poster_id: str, reader: Optional[PosterReader] = None) -> Dict:
    """Read a stored poster into a brief and persist it.

    The brief is cached: reading the same poster twice does not pay for a second
    vision call. Pass a reader to override (tests pass StubPosterReader).
    """
    record = get_poster(poster_id)
    if not record:
        raise FileNotFoundError(f"Poster {poster_id} not found")
    if record.get("brief"):
        return record

    with open(record["image_path"], "rb") as fh:
        image_bytes = fh.read()

    reader = reader or VisionPosterReader()
    brief = reader.read(image_bytes, record["mime_type"])
    record["brief"] = brief
    record["original_brief"] = brief
    record["fields"] = parse_brief(brief)
    record["original_fields"] = dict(record["fields"])
    labels = parse_labels(brief)
    record.update(labels)
    record["original_ask_label_primary"] = labels["ask_label_primary"]
    record["original_ask_label_secondary"] = labels["ask_label_secondary"]
    record["original_channel"] = labels["channel"]
    record["brief_edited"] = False
    record["frozen"] = False
    record["read_at"] = datetime.now().isoformat()
    _write_record(poster_id, record)
    return record


def parse_brief(text: str) -> Dict[str, str]:
    """Extract the fixed read headings without changing the original brief."""
    source = text or ""
    fields = dict(EMPTY_FIELDS)
    names = {
        "TEXT ON THE POSTER": "text",
        "WHAT IS PICTURED": "pictured",
        "LAYOUT": "layout",
        "CLAIMS": "claims",
        "THE ASK": "ask",
        "PRICE SHOWN": "price",
    }
    upper = source.upper()
    # Cut LABELS section off so it does not pollute PRICE SHOWN.
    labels_at = upper.find("\nLABELS")
    if labels_at < 0:
        labels_at = upper.find("LABELS\n")
    body = source if labels_at < 0 else source[:labels_at]
    body_upper = body.upper()
    found = sorted(
        (body_upper.find(h), h) for h in BRIEF_HEADINGS if body_upper.find(h) >= 0
    )
    for index, (start, heading) in enumerate(found):
        end = found[index + 1][0] if index + 1 < len(found) else len(body)
        value = body[start + len(heading):end].strip()
        if heading == "CLAIMS":
            parts = re.split(
                r"(?:,\s*)?(?:and\s+)?separately,?\s*what it only implies\s*[:\-]?",
                value,
                maxsplit=1,
                flags=re.I,
            )
            if len(parts) == 1:
                parts = re.split(
                    r"\bimplies\b\s*[:\-]?",
                    value,
                    maxsplit=1,
                    flags=re.I,
                )
            stated = parts[0].strip()
            # Strip the prompt scaffolding ("States outright:") — the human
            # edits this field, so it must hold only the claim itself.
            stated = re.sub(
                r"^\s*(?:it\s+)?states\s+outright(?:\s+that)?\s*[:\-]?\s*",
                "",
                stated,
                flags=re.I,
            ).strip()
            implied = parts[1].strip() if len(parts) == 2 else ""
            implied = re.sub(r"^\s*[:\-]\s*", "", implied).strip()
            fields["claims_stated"] = stated
            fields["claims_implied"] = implied
        else:
            fields[names[heading]] = value
    return fields


def _normalize_label_token(raw: str) -> str:
    """Collapse model phrasing into a closed-list token. Never invents a label."""
    token = (raw or "").strip().lower()
    token = re.sub(r"^[\-\*\d\.\)\s]+", "", token)
    token = token.split("(")[0].strip()
    token = re.sub(r"[^a-z0-9_\s\-]+", "", token)
    token = token.replace("-", "_").replace(" ", "_")
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def parse_labels(text: str) -> Dict[str, str]:
    """Pull primary/secondary/channel from the read text.

    Prefers a LABELS section when present. Unknown action → unclear.
    Unknown channel → none. secondary none → empty string.
    """
    source = text or ""
    upper = source.upper()
    labels_at = upper.find("\nLABELS")
    if labels_at < 0:
        labels_at = upper.find("LABELS\n")
    if labels_at < 0 and upper.startswith("LABELS"):
        labels_at = 0
    section = source[labels_at:] if labels_at >= 0 else source

    values: Dict[str, str] = {}
    for line in section.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_n = _normalize_label_token(key)
        # Accept primary / primary_action / primaryaction
        key_n = key_n.replace("_action", "").replace("action_", "")
        values[key_n] = _normalize_label_token(value)

    primary = values.get("primary", "unclear")
    secondary = values.get("secondary", "none")
    channel = values.get("channel", "none")

    return {
        "ask_label_primary": primary if primary in ACTION_LABELS else "unclear",
        "ask_label_secondary": (
            "" if secondary in ("", "none")
            else (secondary if secondary in ACTION_LABELS else "unclear")
        ),
        "channel": channel if channel in CHANNEL_LABELS else "none",
    }


def brief_from_fields(fields: Dict[str, str], labels: Optional[Dict[str, str]] = None) -> str:
    """Rebuild a plain-text brief from edited fields. No model call."""
    f = {**EMPTY_FIELDS, **(fields or {})}
    claims = f.get("claims_stated") or ""
    if f.get("claims_implied"):
        claims = (
            f"{claims.rstrip()}\n"
            f"and separately, what it only implies: {f['claims_implied']}"
        ).strip()
    parts = [
        f"TEXT ON THE POSTER\n{f.get('text', '')}",
        f"WHAT IS PICTURED\n{f.get('pictured', '')}",
        f"LAYOUT\n{f.get('layout', '')}",
        f"CLAIMS\n{claims}",
        f"THE ASK\n{f.get('ask', '')}",
        f"PRICE SHOWN\n{f.get('price', '') or 'none'}",
    ]
    if labels:
        parts.append(
            "LABELS\n"
            f"primary: {labels.get('ask_label_primary') or 'unclear'}\n"
            f"secondary: {labels.get('ask_label_secondary') or 'none'}\n"
            f"channel: {labels.get('channel') or 'none'}"
        )
    return "\n\n".join(parts).strip() + "\n"


def update_poster(
    poster_id: str,
    *,
    fields: Optional[Dict[str, str]] = None,
    ask_label_primary: Optional[str] = None,
    ask_label_secondary: Optional[str] = None,
    channel: Optional[str] = None,
) -> Dict:
    """Human correction of the brief. Never re-calls vision. Freezes after a round."""
    record = get_poster(poster_id)
    if not record:
        raise FileNotFoundError(f"Poster {poster_id} not found")
    if record.get("frozen"):
        raise ValueError(
            "This brief is frozen after a panel round. Start a new run to edit."
        )
    if not record.get("brief"):
        raise ValueError("Poster has not been read yet")

    # Keep the original read once.
    if "original_brief" not in record:
        record["original_brief"] = record.get("brief")
        record["original_fields"] = dict(record.get("fields") or EMPTY_FIELDS)
        record["original_ask_label_primary"] = record.get("ask_label_primary")
        record["original_ask_label_secondary"] = record.get("ask_label_secondary")
        record["original_channel"] = record.get("channel")

    next_fields = dict(record.get("fields") or EMPTY_FIELDS)
    if fields:
        for key in EMPTY_FIELDS:
            if key in fields and fields[key] is not None:
                next_fields[key] = str(fields[key])

    primary = ask_label_primary if ask_label_primary is not None else record.get("ask_label_primary")
    secondary = ask_label_secondary if ask_label_secondary is not None else record.get("ask_label_secondary")
    ch = channel if channel is not None else record.get("channel")

    if primary is not None and primary not in ACTION_LABELS:
        raise ValueError(f"Invalid primary action '{primary}'")
    if secondary not in (None, "") and secondary not in ACTION_LABELS:
        raise ValueError(f"Invalid secondary action '{secondary}'")
    if secondary == "none":
        secondary = ""
    if ch is not None and ch not in CHANNEL_LABELS:
        raise ValueError(f"Invalid channel '{ch}'")

    labels = {
        "ask_label_primary": primary or "unclear",
        "ask_label_secondary": secondary or "",
        "channel": ch or "none",
    }
    record["fields"] = next_fields
    record.update(labels)
    record["brief"] = brief_from_fields(next_fields, labels)
    record["brief_edited"] = True
    record["edited_at"] = datetime.now().isoformat()
    _write_record(poster_id, record)
    return record


def freeze_poster(poster_id: str) -> Dict:
    """Lock the brief after a round so old results never silently change."""
    record = get_poster(poster_id)
    if not record:
        raise FileNotFoundError(f"Poster {poster_id} not found")
    record["frozen"] = True
    record["frozen_at"] = datetime.now().isoformat()
    _write_record(poster_id, record)
    return record
