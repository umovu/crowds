"""
query_context — a local context block scoped to the place the pitch is about.

The daily national block (sa_context) reaches every persona in every run: the
same six lines about unemployment and the cost of living, whatever the pitch
was and wherever it is set. Personas differ by province and geotype; that block
does not, so it flattens the difference out.

This adds a SECOND, smaller block, searched only when the pitch actually names
a South African place. "A clinic in Sunnyside, Pretoria" gets Sunnyside/Tshwane
health news; a pitch that names no place gets nothing at all, and costs nothing.

Demand-driven and cached per place+subject, so a re-run of the same pitch is a
cache hit. Everything downstream is reused unchanged: the same Serper search,
the same distil rules, the same cheap-tier judge, the same fail-safe (no place,
no snippets, no model, or a failed judge -> national block only).

Search makes CONTEXT only. It never writes who a persona is, and it never
touches income, budget tier or affordability.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.query_context")

_CACHE_TTL_HOURS = float(os.environ.get("QUERY_CONTEXT_TTL_HOURS", "24"))

# Below this many usable snippets, there is not enough local news to write a
# grounded block from, and we leave the persona with the national block alone.
_MIN_SNIPPETS = 3


# ─────────────────────────────────────────────────────────────
# Gazetteer — the only places we will search for. Deliberately a
# hand-kept list, not a model: a place must be recognisable to the
# search engine AND specific enough that local news about it exists.
#
# Each entry maps a matchable name to the parent it should be searched
# WITH. "Sunnyside" alone is ambiguous (there is one in Pretoria and one
# in Johannesburg); "Sunnyside, Pretoria" is not. Provinces and metros
# are their own parent.
# ─────────────────────────────────────────────────────────────

_PROVINCES: Tuple[str, ...] = (
    "Gauteng",
    "Western Cape",
    "Eastern Cape",
    "Northern Cape",
    "KwaZulu-Natal",
    "Free State",
    "North West",
    "Mpumalanga",
    "Limpopo",
)

# Metro / city -> province.
_CITIES: Dict[str, str] = {
    "Johannesburg": "Gauteng",
    "Soweto": "Gauteng",
    "Pretoria": "Gauteng",
    "Tshwane": "Gauteng",
    "Ekurhuleni": "Gauteng",
    "Benoni": "Gauteng",
    "Kempton Park": "Gauteng",
    "Vereeniging": "Gauteng",
    "Vanderbijlpark": "Gauteng",
    "Krugersdorp": "Gauteng",
    "Randburg": "Gauteng",
    "Roodepoort": "Gauteng",
    "Sandton": "Gauteng",
    "Midrand": "Gauteng",
    "Cape Town": "Western Cape",
    "Stellenbosch": "Western Cape",
    "Paarl": "Western Cape",
    "Worcester": "Western Cape",
    "George": "Western Cape",
    "Mossel Bay": "Western Cape",
    "Durban": "KwaZulu-Natal",
    "eThekwini": "KwaZulu-Natal",
    "Pietermaritzburg": "KwaZulu-Natal",
    "Newcastle": "KwaZulu-Natal",
    "Richards Bay": "KwaZulu-Natal",
    "Port Shepstone": "KwaZulu-Natal",
    "Gqeberha": "Eastern Cape",
    "Port Elizabeth": "Eastern Cape",
    "East London": "Eastern Cape",
    "Mthatha": "Eastern Cape",
    "Queenstown": "Eastern Cape",
    "Bloemfontein": "Free State",
    "Welkom": "Free State",
    "Sasolburg": "Free State",
    "Kimberley": "Northern Cape",
    "Upington": "Northern Cape",
    "Springbok": "Northern Cape",
    "Polokwane": "Limpopo",
    "Thohoyandou": "Limpopo",
    "Tzaneen": "Limpopo",
    "Mokopane": "Limpopo",
    "Nelspruit": "Mpumalanga",
    "Mbombela": "Mpumalanga",
    "Witbank": "Mpumalanga",
    "eMalahleni": "Mpumalanga",
    "Secunda": "Mpumalanga",
    "Rustenburg": "North West",
    "Mahikeng": "North West",
    "Mafikeng": "North West",
    "Potchefstroom": "North West",
    "Klerksdorp": "North West",
    "Brits": "North West",
}

# Suburb / township -> the city it should be searched with. Ambiguous names
# (Sunnyside, Extension 2) are pinned to their most-searched instance; a pitch
# that also names the other city corrects it via the parent-hint pass below.
_SUBURBS: Dict[str, str] = {
    # Johannesburg
    "Alexandra": "Johannesburg",
    "Hillbrow": "Johannesburg",
    "Yeoville": "Johannesburg",
    "Braamfontein": "Johannesburg",
    "Diepsloot": "Johannesburg",
    "Orange Farm": "Johannesburg",
    "Lenasia": "Johannesburg",
    "Eldorado Park": "Johannesburg",
    "Westbury": "Johannesburg",
    "Rosebank": "Johannesburg",
    "Fordsburg": "Johannesburg",
    "Mayfair": "Johannesburg",
    "Orlando": "Soweto",
    "Diepkloof": "Soweto",
    "Meadowlands": "Soweto",
    "Pimville": "Soweto",
    "Dobsonville": "Soweto",
    # Pretoria / Tshwane
    "Sunnyside": "Pretoria",
    "Arcadia": "Pretoria",
    "Hatfield": "Pretoria",
    "Mamelodi": "Pretoria",
    "Atteridgeville": "Pretoria",
    "Soshanguve": "Pretoria",
    "Ga-Rankuwa": "Pretoria",
    "Hammanskraal": "Pretoria",
    "Centurion": "Pretoria",
    # Ekurhuleni
    "Tembisa": "Ekurhuleni",
    "Katlehong": "Ekurhuleni",
    "Thokoza": "Ekurhuleni",
    "Vosloorus": "Ekurhuleni",
    "Daveyton": "Ekurhuleni",
    "KwaThema": "Ekurhuleni",
    # Cape Town
    "Khayelitsha": "Cape Town",
    "Mitchells Plain": "Cape Town",
    "Gugulethu": "Cape Town",
    "Langa": "Cape Town",
    "Nyanga": "Cape Town",
    "Delft": "Cape Town",
    "Philippi": "Cape Town",
    "Dunoon": "Cape Town",
    "Bellville": "Cape Town",
    "Athlone": "Cape Town",
    "Manenberg": "Cape Town",
    "Elsies River": "Cape Town",
    "Observatory": "Cape Town",
    "Woodstock": "Cape Town",
    # Durban
    "Umlazi": "Durban",
    "KwaMashu": "Durban",
    "Chatsworth": "Durban",
    "Phoenix": "Durban",
    "Inanda": "Durban",
    "Cato Manor": "Durban",
    "Umhlanga": "Durban",
    "Pinetown": "Durban",
    # Eastern Cape
    "Motherwell": "Gqeberha",
    "New Brighton": "Gqeberha",
    "Mdantsane": "East London",
    # Free State / North West / Limpopo
    "Botshabelo": "Bloemfontein",
    "Mangaung": "Bloemfontein",
    "Ikageng": "Potchefstroom",
    "Seshego": "Polokwane",
}


def _compile(names) -> List[Tuple[str, re.Pattern]]:
    """Whole-word, case-insensitive patterns, longest name first.

    Longest-first matters: "Cape Town" must win over "Cape", and
    "Mitchells Plain" over any shorter fragment inside it.
    """
    out = []
    for name in sorted(names, key=len, reverse=True):
        out.append((name, re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", re.I)))
    return out


_SUBURB_PATTERNS = _compile(_SUBURBS)
_CITY_PATTERNS = _compile(_CITIES)
_PROVINCE_PATTERNS = _compile(_PROVINCES)


def detect_place(text: str) -> Optional[Dict[str, str]]:
    """The most specific South African place the text names, or None.

    Deterministic and model-free, by design: an LLM guessing at a place would
    invent one, and an invented place is an invented context block. Suburb beats
    city beats province, because "Sunnyside" is what makes the block local — the
    province alone is barely narrower than the national block we already have.

    Returns {"name", "parent", "label", "province"}; `label` is what to search
    and to show the persona.
    """
    if not text or not text.strip():
        return None

    for name, pat in _SUBURB_PATTERNS:
        if not pat.search(text):
            continue
        parent = _SUBURBS[name]
        # An ambiguous suburb pinned to the wrong city: if the text itself names
        # a different city, believe the text.
        for city, city_pat in _CITY_PATTERNS:
            if city != parent and city_pat.search(text):
                parent = city
                break
        province = _CITIES.get(parent, "")
        return {"name": name, "parent": parent,
                "label": f"{name}, {parent}", "province": province}

    for name, pat in _CITY_PATTERNS:
        if pat.search(text):
            province = _CITIES[name]
            return {"name": name, "parent": province,
                    "label": name, "province": province}

    for name, pat in _PROVINCE_PATTERNS:
        if pat.search(text):
            return {"name": name, "parent": "South Africa",
                    "label": name, "province": name}

    return None


# ─────────────────────────────────────────────────────────────
# Subject — what the pitch is about, reusing the subjects the national
# block is already filtered by, so "clinic" means the same thing here
# as it does there. Each subject carries the words that make a useful
# LOCAL search: "health" alone returns national policy, "clinic
# hospital" returns the place.
# ─────────────────────────────────────────────────────────────

_SUBJECT_SEARCH_WORDS: Dict[str, str] = {
    "health": "clinic hospital healthcare",
    "work": "jobs unemployment employment",
    "cost": "cost of living prices",
    "power": "electricity outages",
    "water": "water supply outages",
    "safety": "crime safety",
    "migration": "migrants community tensions",
    "poverty": "poverty grants housing",
}


def detect_subjects(text: str, limit: int = 2) -> List[str]:
    """The subjects the pitch touches, most-specific first, at most `limit`.

    Reuses sa_context._topics_in so a pitch is classified by one set of rules,
    not two that can drift apart.
    """
    from .sa_context import _topics_in
    found = _topics_in(text or "")
    # Stable order: follow _SUBJECT_SEARCH_WORDS, not set iteration order, so the
    # same pitch always builds the same queries and so hits the same cache entry.
    return [s for s in _SUBJECT_SEARCH_WORDS if s in found][:limit]


def build_queries(place: Dict[str, str], subjects: List[str]) -> List[str]:
    """2-3 searches: the place on its own, plus the place per subject.

    The bare place query is what catches "what is going on here at all"; the
    subject queries are what make the block about the pitch rather than about
    the suburb in general.
    """
    when = datetime.now().strftime("%B %Y")
    label = place["label"]
    queries = [f"{label} South Africa news {when}"]
    for s in subjects:
        queries.append(f"{label} {_SUBJECT_SEARCH_WORDS[s]} {when}")
    return queries[:3]


# ─────────────────────────────────────────────────────────────
# Cache — keyed by place + subjects, not by day, because the whole point
# is that a place is searched once and re-used by every later run that
# mentions it. Same 24h TTL and same snippet shape as the national block.
# ─────────────────────────────────────────────────────────────

def _enabled() -> bool:
    # Off by default until measured over ~10 real pitches (see the plan).
    return os.environ.get("QUERY_CONTEXT", "0").lower() not in ("0", "false", "no")


def _cache_key(place: Dict[str, str], subjects: List[str]) -> str:
    raw = place["label"].lower() + "|" + ",".join(subjects)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cache_path(key: str) -> str:
    return os.path.join(Config.DATA_ROOT, "cache", "query_context", f"{key}.json")


def _read_cache(key: str) -> Optional[str]:
    try:
        with open(_cache_path(key), "r", encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - float(d.get("ts", 0)) < _CACHE_TTL_HOURS * 3600:
            return d.get("block") or None
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def _write_cache(key: str, block: str, place: Dict[str, str]) -> None:
    try:
        path = _cache_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "place": place["label"], "block": block}, f)
    except OSError as e:
        logger.warning("Could not cache local context for %s: %s", place["label"], e)


# Searching a suburb by name returns a lot that is not local news: weather
# forecasts, property listings, hotel pages, map and directory entries. Left in,
# they crowd out the real snippets and the distil writes what it was given — a
# live run produced a NEAR YOU block whose only bullet was the temperature. These
# are dropped before the model sees anything.
_JUNK_PATTERNS = tuple(re.compile(p, re.I) for p in (
    r"\bweather\b", r"\bforecast\b", r"\btemperature", r"\bhumidity\b", r"\brainfall\b",
    r"\bhigh[s]? of \d", r"°",
    r"\bfor sale\b", r"\bto rent\b", r"\bproperty24\b", r"\bprivateproperty\b",
    r"\bbedroom (?:house|apartment|flat)\b", r"\basking price\b",
    r"\bbook (?:a|your) (?:room|stay|hotel)\b", r"\bguest ?house\b", r"\bbed and breakfast\b",
    r"\btripadvisor\b", r"\bbooking\.com\b", r"\bairbnb\b",
    r"\bget directions\b", r"\bopening hours\b.*\bmap\b", r"\bpostal code\b",
    r"\bwikipedia\b", r"\bis a suburb of\b", r"\bpopulation of the\b",
))


def _is_junk(snippet: str) -> bool:
    """True for search results that are not local news about the place."""
    return any(p.search(snippet or "") for p in _JUNK_PATTERNS)


def _gather_snippets(queries: List[str]) -> List[Dict[str, str]]:
    """Real search snippets for this place, each keeping its own link.

    Same shape as sa_context._gather_snippets, so _render_sources and the judge
    take these unchanged.
    """
    from .serper_service import SerperService
    serper = SerperService()
    if not serper.is_available():
        return []
    sources: List[Dict[str, str]] = []
    for q in queries:
        res = serper.search(q, num_results=6)
        if not res.get("success"):
            continue
        for item in res.get("results", []):
            sn = (item.get("snippet") or item.get("title") or "").strip()
            if sn and not _is_junk(sn):
                sources.append({
                    "snippet": sn,
                    "link": (item.get("link") or "").strip(),
                    "source": (item.get("source") or "").strip(),
                })
    return sources[:20]


def _distil_local(sources: List[Dict[str, str]], place: Dict[str, str]) -> Optional[str]:
    """Summarise the snippets into 3-5 LOCAL bullets. Returns None on any failure.

    Same rules as the national distil — summarise retrieved text only, never
    author a fact — plus one more: a bullet that is really a national fact does
    not belong here. The national block already says unemployment is 32.7%;
    repeating it under a local heading would tell a persona that it is a fact
    about their street.
    """
    snippets = [s["snippet"] for s in sources if s.get("snippet")]
    if not snippets:
        return None
    key = Config.LLM_API_KEY
    model = Config.LLM_MODEL_NAME
    if not (key and model):
        return None
    label = place["label"]
    today = datetime.now().strftime("%d %B %Y")
    joined = "\n".join(f"- {s}" for s in snippets)
    system = (
        f"You distil real web-search snippets into a short list of things that are "
        f"CURRENTLY true in {label}, South Africa, to ground a simulation. STRICT "
        f"RULES: use ONLY what the snippets support; never add facts not present in "
        f"them; include a number only if a snippet gives one. Every bullet must be "
        f"about {label}, or somewhere close enough that people there use it (a "
        f"neighbouring suburb's clinic counts) — drop anything that is a national "
        f"fact, a fact about a different city or province, or general background, "
        f"however interesting. "
        f"Every bullet must be something ordinary people there LIVE WITH: a service, "
        f"a shortage, a price, a closure, a queue. Write the CONDITION, not the "
        f"incident: never name a private individual — a victim, an accused, a "
        f"person in an incident — even when a snippet does, because this block is "
        f"read by simulated residents and one named person's misfortune is not a "
        f"condition anyone lives with. Naming a place or a facility is fine. "
        f"If the snippets support fewer "
        f"than three such bullets, output fewer. Output 3-5 short, plain "
        f"present-tense bullet lines. No preamble, no closing line."
    )
    user = f"Today is {today}.\n\nSNIPPETS:\n{joined}\n\nWhat is currently true in {label} (3-5 bullets):"

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
            max_tokens=400,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()

    try:
        from .judge_service import (get_judge_service, judge_best_of, record_judgement,
                                    sa_context_judge_enabled)
        if sa_context_judge_enabled():
            svc = get_judge_service(cheap=True)
            text, judge_result, regenerated = judge_best_of(
                generate=_generate,
                judge=lambda t: svc.judge_sa_context(t, snippets, place=label),
            )
            record_judgement("query_context", judge_result, regenerated=regenerated)
            # A local block that still fails after its one retry is DROPPED, and
            # the run keeps the national block alone. The national block cannot do
            # this — it is the only grounding there is, so a poor one still beats
            # none. A local block is extra, so a poor one is worse than none: a
            # weather forecast or a fact about another suburb, under a heading
            # that says NEAR YOU, is read as true of the persona's own street.
            # A judge that ERRORED is not a failed block (nothing was judged).
            if judge_result is not None and judge_result.errored:
                logger.warning("Local judge unavailable for %s; keeping the block", label)
            elif judge_result is not None and not judge_result.pass_:
                logger.info("Local context for %s failed the judge (%s); dropping it.",
                            label, (judge_result.reasoning or "")[:120])
                return None
        else:
            text = _generate()
        return text or None
    except Exception as e:
        logger.warning("Local context distil failed for %s: %s", place["label"], e)
        return None


def local_context(text: str) -> Optional[str]:
    """The 'NEAR YOU' block for this pitch, or None.

    Fails safe at every step — disabled, no place named, no search, no snippets,
    no model, or a failed judge all return None, and the caller is left with the
    national block exactly as it is today.
    """
    if not _enabled():
        return None
    place = detect_place(text)
    if not place:
        return None
    subjects = detect_subjects(text)
    key = _cache_key(place, subjects)
    cached = _read_cache(key)
    if cached is not None:
        return cached
    sources = _gather_snippets(build_queries(place, subjects))
    # Too little real local news to write 3-5 grounded bullets from. Padding a
    # thin search is exactly how a block ends up saying nothing, or saying
    # something national under a local heading.
    if len(sources) < _MIN_SNIPPETS:
        logger.info("Only %d usable local snippets for %s; skipping the local block.",
                    len(sources), place["label"])
        return None
    block = _distil_local(sources, place)
    if not block:
        return None
    from .sa_context import _render_sources
    today = datetime.now().strftime("%d %B %Y")
    framed = (
        f"NEAR YOU ({place['label']} — as of {today}) — local conditions where this\n"
        f"is set. These are facts about the AREA, not about your own household\n"
        f"income or budget:\n{block}"
        f"{_render_sources(sources)}"
    )
    _write_cache(key, framed, place)
    logger.info("Fetched local context for %s (%d snippets).", place["label"], len(sources))
    return framed
