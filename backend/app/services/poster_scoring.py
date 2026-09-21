"""Deterministic poster findings. This module deliberately has no LLM dependency."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# Words that carry no objection. A blocker built only from these is noise.
STOPWORDS = {
    "they", "them", "their", "this", "that", "there", "these", "those",
    "would", "could", "should", "know", "think", "just", "very", "really",
    "thing", "things", "does", "have", "with", "from", "about", "what",
    "when", "then", "than", "want", "like", "make", "made", "your",
    "youre", "dont", "cant", "wont", "some", "much", "more", "also",
    "even", "into", "over", "been", "being", "which", "will", "here",
    "only", "because", "before", "where", "while", "each", "same",
}

# Currency shape: R followed by digits (optionally with spaces/commas),
# e.g. R20, R1 250, R99.95. Matched by shape, never by a fixed amount.
_CURRENCY_RE = re.compile(r"\br\s*\d[\d\s,\.]*", re.IGNORECASE)

# Action keywords. No fixed amounts appear anywhere in this table — a price
# is evidence by shape (see _CURRENCY_RE), not by value.
ACTION_KEYWORDS = {
    "buy": ("buy", "purchase", "pay", "price", "cost", "fee"),
    "sign_up": ("sign up", "signup", "subscribe", "register", "join", "enter"),
    "apply": ("apply", "application", "grant", "loan"),
    "contact": ("call", "phone", "whatsapp", "message", "sms", "contact"),
    "visit": ("visit", "go to", "website", "shop", "branch"),
    "attend": ("attend", "come to", "event", "meeting"),
    "vote": ("vote", "ballot"),
    "donate": ("donate", "donation", "give money"),
    "none": ("just know", "awareness", "inform", "nothing to do"),
}


def score_ask_recall(primary: str, secondary: str, persona_labels: List[Dict[str, Any]]) -> Dict[str, Any]:
    expected = {primary} | ({secondary} if secondary else set())
    understood = sum(1 for item in persona_labels if item.get("label") in expected)
    misread_items = [item for item in persona_labels if item.get("label") not in expected]
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in misread_items:
        groups.setdefault(item.get("label") or "unclear", []).append(item)
    misreads = [
        {
            "label": label,
            "count": len(items),
            "words": [i.get("words", "") for i in items],
            "people": [
                {
                    "name": i.get("name", ""),
                    "segment": i.get("segment", ""),
                    "words": i.get("words", ""),
                }
                for i in items
            ],
        }
        for label, items in groups.items()
    ]
    misreads.sort(key=lambda m: (-m["count"], m["label"]))
    primary_count = sum(1 for i in persona_labels if i.get("label") == primary)
    secondary_count = sum(1 for i in persona_labels if secondary and i.get("label") == secondary)
    return {
        "understood": understood,
        "total": len(persona_labels),
        "misreads": misreads,
        "split": bool(secondary and primary_count and secondary_count),
        "primary_count": primary_count,
        "secondary_count": secondary_count,
    }


def claims_landed(claims_implied: str, answers: Iterable[str]) -> List[str]:
    claims = [c.strip() for c in re.split(r"[.;\n]+", claims_implied or "") if c.strip()]
    answer_list = list(answers)
    out: List[str] = []
    for claim in claims:
        words = set(re.findall(r"[a-z0-9]{4,}", claim.lower()))
        if not words:
            continue
        need = max(2, len(words) // 2)
        if any(len(words & set(re.findall(r"[a-z0-9]{4,}", (a or "").lower()))) >= need for a in answer_list):
            out.append(claim)
    return out


def _content_words(text: str) -> set:
    """Words that carry meaning — filler dropped. Deterministic, no model."""
    return {
        w for w in re.findall(r"[a-z]{4,}", (text or "").lower())
        if w not in STOPWORDS
    }


class TrustBlockerList(list):
    """Top trust-blocker lines, plus how many groups were found in total.

    Iterates like a plain list so locked tests keep working. Callers that
    care about the full room read `.total_groups`.
    """

    total_groups: int = 0


def trust_blockers(answers: Iterable[str]) -> TrustBlockerList:
    """Group answers by the objection they share; name each group in the
    people's own words. Top three groups, with counts of people.

    No transitive chaining. Groups form around a recurring content word:
    an answer joins the group for a word it actually contains. The group's
    name must contain that shared word — every member shares it by
    construction. A group that cannot be named honestly is dropped.

    Equal-sized groups are ordered by who raised the objection first in the
    room (earliest answer index), not by alphabet. `.total_groups` says how
    many distinct groups were found, so a top-three cut never hides that
    five objections existed.
    """
    empty = TrustBlockerList()
    empty.total_groups = 0
    items = [a.strip() for a in answers if (a or "").strip()]
    if not items:
        return empty
    word_sets = [_content_words(a) for a in items]

    # How many answers mention each content word. Only words shared by at
    # least two people can anchor a group.
    freq: Counter = Counter()
    for ws in word_sets:
        for w in ws:
            freq[w] += 1
    # Strongest first; equal frequency → stable alpha only for pivot pick order
    # (assignment), not for final ranking.
    pivots = sorted(
        ((w, c) for w, c in freq.items() if c >= 2),
        key=lambda wc: (-wc[1], wc[0]),
    )

    claimed: set = set()
    # (count, first_member_index, name)
    named = []
    for word, _count in pivots:
        members = [
            i for i in range(len(items))
            if i not in claimed and word in word_sets[i]
        ]
        if len(members) < 2:
            continue
        # Name with the shortest real sentence that contains the pivot word.
        best = None
        for m in members:
            for sentence in re.split(r"[.!?]+", items[m]):
                s = sentence.strip()
                if not s:
                    continue
                if word not in s.lower():
                    continue
                if best is None or len(s) < len(best) or (
                    len(s) == len(best) and s.lower() < best.lower()
                ):
                    best = s
        if best is None or word not in best.lower():
            # Cannot name the group with a phrase that carries the shared word.
            continue
        # Safety: every member must still share the pivot (true by construction).
        if not all(word in word_sets[m] for m in members):
            continue
        for m in members:
            claimed.add(m)
        named.append((len(members), min(members), best))

    # Rank: more people first; ties → the objection that came up earlier.
    named.sort(key=lambda row: (-row[0], row[1], row[2].lower()))
    total = len(items)
    out = TrustBlockerList(
        f"{name} — {count} of {total}" for count, _first, name in named[:3]
    )
    out.total_groups = len(named)
    return out


def label_action_from_text(text: str) -> str:
    """Closed-list action label from free text. Model-off path for ask answers.

    Scores every candidate label instead of taking the first one declared:
    an answer that names an action and mentions a price is the action.
    A price-only answer stays `buy` — currency is matched by shape, so no
    poster's own amount is baked in.
    """
    t = (text or "").lower()
    if not t.strip():
        return "unclear"

    # label -> (hit count, first position in text) for deterministic ties.
    scores: Dict[str, List] = {}
    for label, keys in ACTION_KEYWORDS.items():
        count = 0
        first = None
        for k in keys:
            start = 0
            while True:
                idx = t.find(k, start)
                if idx < 0:
                    break
                count += 1
                if first is None or idx < first:
                    first = idx
                start = idx + 1
        if count:
            scores[label] = [count, first]

    # A currency amount is evidence for buy, by shape only (R + digits).
    m = _CURRENCY_RE.search(t)
    if m:
        entry = scores.setdefault("buy", [0, None])
        entry[0] += 1
        entry[1] = m.start() if entry[1] is None else min(entry[1], m.start())

    if not scores:
        return "unclear"

    # A named action beats price-only evidence. Price counts as `buy` only
    # when no other action is named.
    named = {label: v for label, v in scores.items() if label != "buy"}
    pool = named or scores
    best = sorted(
        pool.items(),
        key=lambda kv: (-kv[1][0], kv[1][1], kv[0]),
    )[0][0]
    return best


def attention_stated(answers: Iterable[str]) -> Dict[str, Any]:
    """Counts of what people said about stopping — never a prediction."""
    stop, keep, other = 0, 0, 0
    quotes = []
    for raw in answers:
        text = (raw or "").strip()
        low = text.lower()
        if any(p in low for p in ("stop scrolling", "i would stop", "i'd stop", "would stop")):
            stop += 1
            if text:
                quotes.append(text)
        elif any(p in low for p in ("keep going", "scroll past", "keep scrolling", "would not stop")):
            keep += 1
        else:
            other += 1
    return {
        "said_they_would_stop": stop,
        "said_they_would_keep_going": keep,
        "other": other,
        "examples": quotes[:3],
    }


def worst_misread(misreads: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not misreads:
        return None
    top = misreads[0]
    people = top.get("people") or []
    if not people:
        return {
            "label": top.get("label"),
            "words": (top.get("words") or [""])[0],
            "name": "",
            "segment": "",
        }
    person = people[0]
    return {
        "label": top.get("label"),
        "words": person.get("words", ""),
        "name": person.get("name", ""),
        "segment": person.get("segment", ""),
    }


def build_findings(
    *,
    primary: str,
    secondary: str = "",
    persona_labels: List[Dict[str, Any]],
    claims_implied: str = "",
    claim_answers: Optional[Iterable[str]] = None,
    trust_answers: Optional[Iterable[str]] = None,
    attention_answers: Optional[Iterable[str]] = None,
    brief_edited: bool = False,
) -> Dict[str, Any]:
    recall = score_ask_recall(primary, secondary, persona_labels)
    blockers = trust_blockers(trust_answers or [])
    findings = {
        "understood": recall["understood"],
        "total": recall["total"],
        "misreads": recall["misreads"],
        "worst_misread": worst_misread(recall["misreads"]),
        "split": recall["split"],
        "primary": primary,
        "secondary": secondary or "",
        "primary_count": recall["primary_count"],
        "secondary_count": recall["secondary_count"],
        "claims_landed": claims_landed(claims_implied, claim_answers or []),
        # Plain list for JSON; total_groups is the full room count so a
        # top-three cut never pretends there were only three objections.
        "trust_blockers": list(blockers),
        "trust_groups_found": int(getattr(blockers, "total_groups", len(blockers))),
        "attention": attention_stated(attention_answers or []),
        "brief_edited": bool(brief_edited),
        "caveat": "This measures comprehension and stated reaction. It does not predict sales.",
    }
    return findings


def module_has_no_llm_import() -> bool:
    """Structural guard used by tests: this file must stay model-free."""
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "llm" in alias.name.lower():
                    return False
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "llm" in mod.lower() or any("llm" in (a.name or "").lower() for a in node.names):
                return False
    return True
