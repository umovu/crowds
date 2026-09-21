"""Model-off tests for poster closed labels (Step 2)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from test_poster_brief import ps  # noqa: E402


def test_junk_label_becomes_unclear():
    out = ps.parse_labels("primary: garbage\nsecondary: buy\nchannel: whatsapp")
    assert out["ask_label_primary"] == "unclear"
    assert out["ask_label_secondary"] == "buy"
    assert out["channel"] == "whatsapp"


def test_secondary_none_becomes_empty():
    out = ps.parse_labels("primary: sign_up\nsecondary: none\nchannel: website")
    assert out["ask_label_secondary"] == ""
    assert out["channel"] == "website"


def test_stub_reader_labels_are_valid():
    brief = ps.StubPosterReader().read(b"", "image/png")
    out = ps.parse_labels(brief)
    assert out["ask_label_primary"] in ps.ACTION_LABELS
    assert out["ask_label_secondary"] in ("", *ps.ACTION_LABELS)
    assert out["channel"] in ps.CHANNEL_LABELS
    assert out["ask_label_primary"] == "sign_up"
    assert out["ask_label_secondary"] == "buy"
    assert out["channel"] == "whatsapp"


def test_invalid_channel_becomes_none():
    out = ps.parse_labels("primary: buy\nsecondary: none\nchannel: carrier_pigeon")
    assert out["channel"] == "none"


def test_primary_action_wording_and_spaces():
    text = (
        "LABELS\n"
        "primary action: sign up\n"
        "secondary action: none\n"
        "channel: in person\n"
    )
    out = ps.parse_labels(text)
    assert out == {
        "ask_label_primary": "sign_up",
        "ask_label_secondary": "",
        "channel": "in_person",
    }


def test_bullet_and_numbered_lines():
    text = (
        "LABELS\n"
        "1. primary: visit\n"
        "- secondary: contact\n"
        "* channel: qr_code\n"
    )
    out = ps.parse_labels(text)
    assert out["ask_label_primary"] == "visit"
    assert out["ask_label_secondary"] == "contact"
    assert out["channel"] == "qr_code"


def test_labels_section_preferred_over_body_noise():
    text = (
        "THE ASK\nprimary: this is not a label line in the body\n"
        "channel: ignore_this\n\n"
        "LABELS\n"
        "primary: donate\n"
        "secondary: none\n"
        "channel: app\n"
    )
    out = ps.parse_labels(text)
    assert out["ask_label_primary"] == "donate"
    assert out["channel"] == "app"


def test_read_prompt_lists_closed_labels_and_guard():
    prompt = ps.READ_PROMPT
    assert "LABELS" in prompt
    assert "primary action" in prompt
    assert "secondary action" in prompt
    assert "buy, sign_up, apply, contact" in prompt
    assert "whatsapp, call, sms_ussd" in prompt
    assert "Do not say who it is aimed at" in prompt
    assert "Do not invent a label" in prompt


def test_read_poster_stores_labels_on_record():
    from app.config import Config

    root = tempfile.mkdtemp(prefix="poster_labels_")
    old = Config.POSTER_DATA_DIR
    Config.POSTER_DATA_DIR = root
    try:
        saved = ps.save_poster(b"fake-image-bytes", "image/png", "x.png")
        # Write a dummy image file path already set by save_poster
        with open(saved["image_path"], "wb") as fh:
            fh.write(b"x")
        record = ps.read_poster(saved["poster_id"], reader=ps.StubPosterReader())
        assert record["ask_label_primary"] == "sign_up"
        assert record["ask_label_secondary"] == "buy"
        assert record["channel"] == "whatsapp"
        assert record["original_ask_label_primary"] == "sign_up"
        # raw brief preserved
        assert "LABELS" in record["brief"]
        # re-read is cached, no change
        again = ps.read_poster(saved["poster_id"], reader=ps.StubPosterReader())
        assert again["brief"] == record["brief"]
    finally:
        Config.POSTER_DATA_DIR = old
