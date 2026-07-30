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
import uuid
from datetime import datetime
from typing import Dict, Optional, Protocol

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

# What the vision model is asked for. Description only: every word on the
# poster, what is pictured, the layout, the claim. Deliberately NOT asked: who
# it is aimed at, which segment it suits, or how well it would perform.
READ_PROMPT = """You are looking at a poster or advertisement, most likely from South Africa.

Describe it so that someone who cannot see it understands exactly what is on it.

Use exactly these six headings, in this order, and nothing else. Write the
heading, then your answer under it. Do not restate the instructions.

TEXT ON THE POSTER
    Every word, transcribed exactly, including the small print. After each
    piece, note how prominent it is: headline, body, or footnote.

WHAT IS PICTURED
    People (apparent age, dress), objects, setting, logos, branding. Say so
    plainly if the poster is text only.

LAYOUT
    What the eye hits first, second, third.

CLAIMS
    What it states outright, and separately, what it only implies.

THE ASK
    What the reader is asked to do, and how to do it.

PRICE SHOWN
    One line. List every price, fee or amount that appears, separated by
    commas. If no amount appears anywhere, write: none

Report only what is actually on the poster. Do not judge whether it is good.
Do not say who it is aimed at, do not describe an audience or a market, and do
not guess who would respond to it. Choosing who sees this is not your job.
"""

# Poster-shaped questions. A poster is met while scrolling, so the useful
# reactions are about attention and trust, not willingness to pay. No question
# here asks for a click probability or any other score.
POSTER_QUESTIONS = [
    "What is this asking you to do?",
    "Would you stop scrolling for this, or keep going? Say why.",
    "What feels off about it, if anything?",
    "Do you trust whoever is behind this? What would make you trust them more?",
]


class PosterReader(Protocol):
    """Reads image bytes into a text brief."""

    def read(self, image_bytes: bytes, mime_type: str) -> str: ...


class VisionPosterReader:
    """The real reader — one call to the vision tier per poster."""

    def __init__(self, max_tokens: int = 8000, temperature: float = 0.2):
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
            "Headline: SAVE R500, GET R7 000 BACK.\n"
            "Offer: a savings club paying out every December.\n"
            "Call to action: join before 31 July, WhatsApp the number shown.\n"
            "PRICE SHOWN: R500 per month"
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
    record["brief"] = reader.read(image_bytes, record["mime_type"])
    record["read_at"] = datetime.now().isoformat()
    _write_record(poster_id, record)
    return record
