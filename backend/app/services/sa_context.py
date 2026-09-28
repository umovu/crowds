"""
sa_context — current South African grounding, refreshed from live web search.

The hardcoded SA narrative ("load-shedding destroying small businesses") went
stale: agents kept raising a 2022-23 crisis as if it were current. This detects
what is ACTUALLY salient now via a web-search check and distils the real
snippets (the LLM SUMMARISES retrieved text — it never authors facts) into a
short, dated "current realities" block.

Cost is bounded: cached once per day (one batch of searches + one small
summarise call), shared across all sims via the data volume, so the per-run COGS
impact is effectively zero. Fails safe — returns None if search/LLM are
unavailable or disabled, and the caller falls back to the (softened) static
block. Disable entirely with SA_CONTEXT_DYNAMIC=0.

A checked snapshot (SA_CONTEXT_SNAPSHOT_PATH, else DATA_ROOT/sa_context_snapshot.json)
takes precedence over live search, so the block works with no network or model
access at all. Each snapshot claim carries its own date, source, scope and
expiry; expired claims are dropped rather than passed off as current.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger
from .serper_service import SerperService

logger = get_logger("fub.sa_context")

_CACHE_TTL_HOURS = float(os.environ.get("SA_CONTEXT_TTL_HOURS", "24"))


def _enabled() -> bool:
    return os.environ.get("SA_CONTEXT_DYNAMIC", "1").lower() not in ("0", "false", "no")


def _cache_path() -> str:
    return os.path.join(Config.DATA_ROOT, "cache", "sa_context.json")


def _snapshot_path() -> str:
    return os.path.join(Config.DATA_ROOT, "sa_context_snapshot.json")


def _checked_snapshot() -> Optional[Dict[str, Any]]:
    p = os.environ.get("SA_CONTEXT_SNAPSHOT_PATH") or _snapshot_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("claims"), list):
            return d
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _snapshot_fresh(d: Dict[str, Any]) -> bool:
    claims = d.get("claims") or []
    now = time.time()
    for c in claims:
        exp = c.get("expires_at")
        if exp is not None:
            try:
                if now > float(exp):
                    return False
            except (ValueError, TypeError):
                return False
    fetched = d.get("fetched_at")
    if fetched is not None:
        try:
            if now - float(fetched) > _CACHE_TTL_HOURS * 3600:
                return False
        except (ValueError, TypeError):
            pass
    return True


def format_snapshot(snapshot: Dict[str, Any]) -> Optional[str]:
    claims = snapshot.get("claims") or []
    if not claims:
        return None
    now = time.time()
    lines = []
    for c in claims:
        exp = c.get("expires_at")
        if exp is not None:
            try:
                if now > float(exp):
                    continue
            except (ValueError, TypeError):
                continue
        text = (c.get("text") or "").strip()
        if not text:
            continue
        date = (c.get("date") or "date unknown").strip()
        src = (c.get("source") or "").strip()
        scope = (c.get("scope") or "").strip()
        line = f"- {text} [{date}"
        if scope:
            line += f", {scope}"
        if src:
            line += f", {src}"
        line += "]"
        lines.append(line)
    if not lines:
        return None
    fetched = snapshot.get("fetched_at")
    asof = snapshot.get("as_of") or (datetime.fromtimestamp(float(fetched), tz=timezone.utc).strftime("%d %B %Y") if fetched else datetime.now(timezone.utc).strftime("%d %B %Y"))
    header = f"CURRENT SOUTH AFRICAN CONTEXT (source-based, as of {asof}) — treat as current evidence; do NOT assume past crises still apply unless listed:"
    return header + "\n" + "\n".join(lines)


# Topics the static SA block asserts as ongoing crises. If current evidence says
# one of them has eased, the two blocks contradict each other and the static
# framing is the stale half. Keyed by topic -> words that name it.
_CRISIS_TOPICS: Dict[str, tuple] = {
    "load-shedding": ("load-shedding", "load shedding", "loadshedding"),
    "electricity supply": ("blackout", "power cuts"),
    "water supply": ("water shedding", "water cuts", "water outages"),
    "fuel price": ("fuel price", "petrol price"),
    "unemployment": ("unemployment",),
    "crime": ("crime", "violent crime"),
}

_EASED_WORDS = ("eased", "easing", "ended", "over", "suspended", "resolved",
                "improved", "improving", "no load", "without load", "declined",
                "fallen", "falling", "lower")


def detect_conflicts(current: Any, static_text: str) -> List[str]:
    """Name the topics where current evidence contradicts the static SA block.

    `current` may be a rendered block (str) or a list of snapshot claim dicts.
    A conflict is reported only when the static text asserts a topic AND the
    current evidence describes that same topic as having eased. Reporting only;
    nothing is rewritten here — the plan forbids a refresh editing stored text.
    """
    if isinstance(current, str):
        texts = [current.lower()]
    else:
        texts = [(c.get("text") or "").lower() for c in (current or [])]
    low = static_text.lower()
    out: List[str] = []
    for topic, words in _CRISIS_TOPICS.items():
        if not any(w in low for w in words):
            continue
        for t in texts:
            for w in words:
                idx = t.find(w)
                if idx < 0:
                    continue
                # Only look at the sentence the topic appears in, so an "eased"
                # about some other topic in the same block does not count.
                start = t.rfind(".", 0, idx) + 1
                end = t.find(".", idx)
                sentence = t[start: end if end > 0 else len(t)]
                if any(e in sentence for e in _EASED_WORDS):
                    out.append(
                        f"current evidence says '{topic}' has eased, but the static "
                        f"SA block still asserts it as ongoing"
                    )
                    break
            else:
                continue
            break
    return out


def _read_cache() -> Optional[str]:
    snap = _checked_snapshot()
    if snap and _snapshot_fresh(snap):
        formatted = format_snapshot(snap)
        if formatted:
            return formatted
        if snap.get("claims"):
            logger.warning("Snapshot claims all expired; falling back to cache/live")
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("claims"), list):
            snap2 = d
            if _snapshot_fresh(snap2):
                fmt = format_snapshot(snap2)
                if fmt:
                    return fmt
            return None
        if time.time() - float(d.get("ts", 0)) < _CACHE_TTL_HOURS * 3600:
            return d.get("block") or None
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def _write_cache(block: str) -> None:
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        entry = {"ts": time.time(), "block": block}
        from . import data_model
        data_model.warn_if_off_model(logger, "SA context cache", "sa_context_cache", entry)
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(entry, f)
    except OSError as e:
        logger.warning("Could not cache SA context: %s", e)


def _link(item: Dict[str, Any]) -> str:
    """A search result's address. SerperService returns it as `url`; reading only
    `link` left every block without a single source."""
    return (item.get("link") or item.get("url") or "").strip()


def _site(link: str) -> str:
    """news24.com from https://www.news24.com/..., to name a source in a word."""
    host = re.sub(r"^https?://", "", link or "").split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


# Places a claim about South Africa today should not come from: social posts,
# video, forums, encyclopedias, and company blogs selling something (a solar
# installer's "why load-shedding still matters" post). Blocked by site, not by
# topic, so the news that remains is left to say what it says.
_UNTRUSTED_SITES = ("facebook.com", "instagram.com", "tiktok.com", "twitter.com", "x.com",
                    "youtube.com", "reddit.com", "linkedin.com", "pinterest.com", "quora.com",
                    "medium.com", "wikipedia.org", "fandom.com")


def _trusted(link: str) -> bool:
    site = _site(link)
    if not site or any(site == s or site.endswith("." + s) for s in _UNTRUSTED_SITES):
        return False
    return not re.search(r"/blogs?/", link)


def _gather_snippets() -> List[Dict[str, str]]:
    """Pull real search snippets on what is currently pressing in SA.

    Each entry keeps its own link so the rendered block can cite where a claim
    came from — an unsourced claim must never be presented as current evidence.
    """
    serper = SerperService()
    if not serper.is_available():
        return []
    when = datetime.now().strftime("%B %Y")
    queries = [
        f"most pressing issues facing ordinary South Africans {when}",
        f"is load shedding still a problem in South Africa {when}",
        f"South Africa cost of living unemployment crime {when}",
        # Health salience (clinic stock-outs, NHI moves) — one more cached query,
        # same daily batch; _distil still only summarises what comes back.
        f"South African public health clinics medicine shortages {when}",
        # Fuel moves on the first Wednesday of every month and feeds taxi fares
        # and food prices; the fixed petrol figure in sa_world_facts lags it.
        f"South Africa petrol diesel price change {when}",
    ]
    sources: List[Dict[str, str]] = []
    for q in queries:
        res = serper.search(q, num_results=6)
        if not res.get("success"):
            continue
        for item in res.get("results", []):
            sn = (item.get("snippet") or item.get("title") or "").strip()
            if sn and _trusted(_link(item)):
                sources.append({
                    "snippet": sn,
                    "link": _link(item),
                    "source": (item.get("source") or _site(_link(item))).strip(),
                })
    return sources[:30]


def _render_sources(sources: List[Dict[str, str]]) -> str:
    """A deduplicated 'where this came from' footer for the distilled block."""
    seen, lines = set(), []
    for s in sources:
        label = s.get("source") or s.get("link")
        if not label or label in seen:
            continue
        seen.add(label)
        link = s.get("link")
        lines.append(f"- {label}" + (f" ({link})" if link and link != label else ""))
    if not lines:
        return ""
    return "\nSources searched (snippets only, not independently verified):\n" + "\n".join(lines[:8])


def _distil(sources: List[Dict[str, str]]) -> Optional[str]:
    """Summarise the snippets into 6-8 current-reality bullets, grounded ONLY in
    the retrieved text (no LLM-authored facts). Returns None on any failure."""
    snippets = [s["snippet"] for s in sources if s.get("snippet")]
    if not snippets:
        return None
    key = Config.LLM_API_KEY
    model = Config.LLM_MODEL_NAME
    if not (key and model):
        return None
    today = datetime.now().strftime("%d %B %Y")
    joined = "\n".join(f"- {s}" for s in snippets)
    system = (
        "You distil real web-search snippets into a short list of CURRENT realities "
        "facing ordinary South Africans, to ground a simulation. STRICT RULES: use "
        "ONLY what the snippets support; never add facts not present in them; if a "
        "past crisis (e.g. load-shedding) is described as eased or resolved, reflect "
        "that or omit it; include a number only if a snippet gives one. Every bullet "
        "must be something ordinary South Africans LIVE WITH — searches return "
        "continental news and political topic lists, and bullets about wars "
        "elsewhere or lists of election issues tell a simulated person nothing. "
        "When the snippets carry news on it, give each of these at least one bullet: "
        "jobs, the cost of living, fuel prices, electricity, public health. "
        "Output 6-8 "
        "short, plain present-tense bullet lines. No preamble, no closing line."
    )
    user = f"Today is {today}.\n\nSNIPPETS:\n{joined}\n\nCurrent realities (6-8 bullets):"
    def _generate(prev_judge=None) -> str:
        from openai import OpenAI
        retry_hint = ""
        if prev_judge is not None and prev_judge.reasoning:
            retry_hint = (
                f"\n\nA previous draft scored low. Fix this while using ONLY facts the "
                f"snippets support:\n{prev_judge.reasoning}"
            )
        client = OpenAI(api_key=key, base_url=Config.LLM_BASE_URL or None)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                       {"role": "user", "content": user + retry_hint}],
            extra_body=Config.llm_extra_body() or None,
            max_tokens=500,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    try:
        from .judge_service import (get_judge_service, judge_best_of, record_judgement,
                                    sa_context_judge_enabled)
        # Judged on the sim tier and on by default: this block is written once a
        # day and reaches every persona prompt, and the cheap tier scored the
        # same as the Plus tier on tests/data/sa_context_cases.json.
        if sa_context_judge_enabled():
            svc = get_judge_service(cheap=True)
            text, judge_result, regenerated = judge_best_of(
                generate=_generate,
                judge=lambda t: svc.judge_sa_context(t, snippets),
            )
            record_judgement("sa_context", judge_result, regenerated=regenerated)
        else:
            text = _generate()
        return text or None
    except Exception as e:
        logger.warning("SA context distil failed: %s", e)
        return None


# Subjects a current-context claim can be about. A claim reaches a panel prompt only
# when the question touches one of the same subjects. Stems match at a word start
# ("unemploy" finds "unemployment") but never inside a word ("work" not in "network").
_REALITY_TOPICS: Dict[str, tuple] = {
    "health": ("clinic", "hospital", "medicine", "medical", "doctor", "nurse", "health",
               "patient", "pharmac", "chronic"),
    "work": ("job", "jobs", "work", "employ", "unemploy", "salary", "salaries", "wage",
             "hiring", "income"),
    "cost": ("price", "prices", "cost", "costs", "afford", "fee", "fees", "rand",
             "expensive", "cheap", "pay", "paying", "budget", "cost of living"),
    "power": ("electricity", "power", "load shedding", "load-shedding", "load reduction",
              "eskom", "blackout", "outage"),
    "water": ("water", "tap", "taps", "pipe", "pipes", "sanitation"),
    "safety": ("crime", "safe", "safety", "security", "police", "theft"),
    "migration": ("foreign", "foreigner", "immigra", "migrant", "border"),
    "poverty": ("poverty", "poor", "inequality", "grant", "grants", "sassa"),
}
_PRICE_RE = re.compile(r"\bR\s?\d")


# A news claim is about the cost of living only when it is about what households
# pay. "Crime costs the economy R700 billion" says "costs" and names rands, and
# was reaching every priced pitch as a cost-of-living point.
_CLAIM_COST_WORDS = ("price", "prices", "cost of living", "living cost", "afford",
                     "expensive", "inflation", "household", "budget", "fuel", "petrol",
                     "rent", "tariff", "food", "basic cost", "a month")


def _first_at(low: str, words) -> Optional[int]:
    hits = [m.start() for w in words
            for m in [re.search(r"(?<![a-z0-9])" + re.escape(w), low)] if m]
    return min(hits) if hits else None


def _topics_in(text: str) -> set:
    low = (text or "").lower()
    found = {t for t, words in _REALITY_TOPICS.items() if _first_at(low, words) is not None}
    if _PRICE_RE.search(text or ""):
        found.add("cost")
    return found


def _claim_subject(claim: str) -> Optional[str]:
    """The one subject a news claim is about: the one it names first.

    A pitch keeps a claim only on its main subject, not a passing word, so "Crime
    costs the economy R700 billion" is about crime and stays out of a clinic room."""
    low = (claim or "").lower()
    words = {**_REALITY_TOPICS, "cost": _CLAIM_COST_WORDS}
    at = {t: i for t, ws in words.items() if (i := _first_at(low, ws)) is not None}
    return min(at, key=at.get) if at else None


def relevant_realities(block: Optional[str], question: str, limit: int = 3) -> Optional[str]:
    """Only the current-context claims this question touches.

    The full block went into every panel prompt: eight claims, all bad news
    (unemployment, medicine shortages, immigration, cost of living), whatever the
    question was about. Now a claim is kept only if it shares a subject with the
    question, at most `limit`, in source order; if none does, the whole block (header
    and sources footer too) is dropped. Deterministic, no model.
    """
    if not block:
        return None
    wanted = _topics_in(question)
    if not wanted:
        return None
    header, matching, footer, in_footer = [], [], [], False
    for line in block.splitlines():
        if line.startswith("Sources searched"):
            in_footer = True
        if in_footer:
            footer.append(line)
        elif line.startswith("- "):
            if _claim_subject(line[2:]) in wanted:
                matching.append(line)
        elif not matching:
            header.append(line)
    # One claim per subject first, then the rest in order: three cost-of-living
    # lines used to fill every slot and push out the clinic one a diabetes pitch
    # is about.
    first, seen = [], set()
    for line in matching:
        subject = _claim_subject(line[2:])
        if subject not in seen:
            seen.add(subject)
            first.append(line)
    picked = set((first + [l for l in matching if l not in first])[:limit])
    kept = [l for l in matching if l in picked]
    if not kept:
        return None
    out = "\n".join(header + kept)
    if footer:
        out += "\n" + "\n".join(footer)
    return out


_SOURCE_LINE = re.compile(r"^- (?P<label>.+?)(?: \((?P<link>https?://[^)]+)\))?$")


def _points_and_sources(block: Optional[str]) -> Tuple[List[str], List[Dict[str, str]]]:
    """The claim bullets and the sources footer of a rendered block, as lists."""
    points: List[str] = []
    sources: List[Dict[str, str]] = []
    in_footer = False
    for line in (block or "").splitlines():
        if line.startswith("Sources searched"):
            in_footer = True
            continue
        if not line.startswith("- "):
            continue
        if in_footer:
            m = _SOURCE_LINE.match(line.strip())
            if m:
                sources.append({"label": m["label"], "link": m["link"] or ""})
        else:
            points.append(line[2:].strip())
    return points, sources


def news_for_pitch(pitch: str) -> Dict[str, Any]:
    """What today's web search found, and which of it this pitch's room will hear.

    Same calls the round makes (current_sa_realities, then relevant_realities), so
    what the page shows is what the personas are given, and a cold cache is filled
    here rather than by every persona at once. No new search or model call.
    """
    if not _enabled():
        return {"enabled": False}
    saved = _read_cache() is not None
    block = current_sa_realities()
    if not block:
        return {"enabled": True, "found": False, "from_saved": saved}
    everything, _ = _points_and_sources(block)
    used, _ = _points_and_sources(relevant_realities(block, pitch))
    _, sources = _points_and_sources(block)
    as_of = re.search(r"as of ([^)]+?)\)", block)
    return {"enabled": True, "found": True, "from_saved": saved,
            "as_of": as_of.group(1) if as_of else None,
            "total": len(everything), "points": used, "sources": sources}


def current_sa_realities(snapshot: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if not _enabled():
        return None
    if snapshot is not None:
        fmt = format_snapshot(snapshot)
        if fmt:
            return fmt
        return None
    snap = _checked_snapshot()
    if snap and _snapshot_fresh(snap):
        fmt = format_snapshot(snap)
        if fmt:
            return fmt
    cached = _read_cache()
    if cached is not None:
        return cached
    sources = _gather_snippets()
    block = _distil(sources)
    if not block:
        if snap:
            fmt = format_snapshot(snap)
            if fmt:
                logger.warning("Live SA context refresh failed; using last unexpired snapshot")
                return fmt
        return None
    today = datetime.now().strftime("%d %B %Y")
    framed = (
        f"CURRENT SOUTH AFRICAN CONTEXT (source-based, as of {today}) —\n"
        f"treat these as the up-to-date reality; do NOT assume a past crisis still\n"
        f"applies unless it appears below:\n{block}"
        f"{_render_sources(sources)}"
    )
    _write_cache(framed)
    logger.info("Refreshed current SA context from live search.")
    return framed
