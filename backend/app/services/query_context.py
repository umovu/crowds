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

# City -> the Stats SA metro it falls in, using the exact `Metro_code` labels the
# persona library carries (GHS/QLFS share these 17 codes). Only the eight metros
# are listed: a city with no entry is a non-metro town, and the caller falls back
# to the province, which is the truth for it anyway.
#
# The point of this map is that the cast picker can only match what the survey
# measured. Survey geography stops at the metro, so "Sunnyside" and "Soweto"
# both resolve to their metro here even though the CONTEXT block still searches
# the suburb by name. Local facts go suburb-deep; the people stay metro-deep.
_CITY_METROS: Dict[str, str] = {
    "Johannesburg": "GP - City of Johannesburg",
    "Soweto": "GP - City of Johannesburg",
    "Randburg": "GP - City of Johannesburg",
    "Roodepoort": "GP - City of Johannesburg",
    "Sandton": "GP - City of Johannesburg",
    "Midrand": "GP - City of Johannesburg",
    "Pretoria": "GP - City of Tshwane",
    "Tshwane": "GP - City of Tshwane",
    "Ekurhuleni": "GP - Ekurhuleni",
    "Benoni": "GP - Ekurhuleni",
    "Kempton Park": "GP - Ekurhuleni",
    "Cape Town": "WC - City of Cape Town",
    "Durban": "KZN - eThekwini",
    "eThekwini": "KZN - eThekwini",
    "Gqeberha": "EC - Nelson Mandela Bay",
    "Port Elizabeth": "EC - Nelson Mandela Bay",
    "East London": "EC - Buffalo City",
    "Bloemfontein": "FS - Mangaung",
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

    Returns {"name", "parent", "label", "province", "metro"}; `label` is what to
    search and to show the persona, and `metro` ("" when the place is not in one)
    is how far down the CAST can honestly follow — the surveys stop at the metro.
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
        return {"name": name, "parent": parent, "label": f"{name}, {parent}",
                "province": province, "metro": _CITY_METROS.get(parent, "")}

    for name, pat in _CITY_PATTERNS:
        if pat.search(text):
            province = _CITIES[name]
            return {"name": name, "parent": province, "label": name,
                    "province": province, "metro": _CITY_METROS.get(name, "")}

    for name, pat in _PROVINCE_PATTERNS:
        if pat.search(text):
            return {"name": name, "parent": "South Africa", "label": name,
                    "province": name, "metro": ""}

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
    not two that can drift apart, and then widens that with the typed reader
    when it is on — "a backup battery for when the lights go out" is a power
    pitch that no word list catches, and an uncaught subject means the local
    search never asks about the thing the pitch is actually about.
    """
    from .pitch_subjects import subjects as _widen
    from .sa_context import _topics_in
    found = _widen(text or "", _topics_in(text or ""),
                   vocabulary=list(_SUBJECT_SEARCH_WORDS))
    # Stable order: follow _SUBJECT_SEARCH_WORDS, not set iteration order, so the
    # same pitch always builds the same queries and so hits the same cache entry.
    return [s for s in _SUBJECT_SEARCH_WORDS if s in found][:limit]


# Words that say nothing about what a pitch is about. Dropped before the pitch's
# own words go into a search, so "a new app for a clinic" searches "clinic".
_FILLER = frozenset("""
the and but for with without into onto from about over under than then that this
these those what which who whom whose when where why how our ours you your yours
their theirs they them its are was were been being will would can could should
may might must not yes all any each some more most very just also plus per via
want wants need needs new another idea ideas app apps service services business
businesses offering offer offers launch launching people residents person
south africa african local area near around based help helps make makes get gets
one two three like think thinking going who's it's we're i'm
""".split())


def pitch_words(text: str, place: Dict[str, str], limit: int = 5) -> List[str]:
    """The pitch's own content words, in the order written, at most `limit`.

    This is what makes the search about the question the user actually asked,
    not only about the subject a word list filed it under: "chronic medicine
    delivery in Sunnyside" searches for chronic medicine delivery, not just
    "clinic hospital healthcare". Place names are dropped (the place is already
    in every query), as are filler words and numbers. Model-free.
    """
    placed = {w.lower() for part in (place.get("label", ""), place.get("province", ""))
              for w in re.findall(r"[A-Za-z]+", part)}
    out: List[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z'-]*[A-Za-z]", text or ""):
        low = w.lower()
        if len(low) < 3 or low in _FILLER or low in placed or low in out:
            continue
        out.append(low)
        if len(out) >= limit:
            break
    return out


def build_queries(place: Dict[str, str], subjects: List[str],
                  words: Optional[List[str]] = None) -> List[str]:
    """2-3 searches: the place on its own, the place with the pitch's own words,
    then the place per subject.

    The bare place query is what catches "what is going on here at all"; the
    pitch-words query is what ties the search to the question actually asked;
    the subject queries catch the wider topic when the pitch's words are too
    narrow for local news to mention.
    """
    when = datetime.now().strftime("%B %Y")
    label = place["label"]
    queries = [f"{label} South Africa news {when}"]
    if words:
        queries.append(f"{label} {' '.join(words)} {when}")
    for s in subjects:
        queries.append(f"{label} {_SUBJECT_SEARCH_WORDS[s]} {when}")
    return queries[:3]


# How each search is run. "news": Google News only. "both": news and the whole
# web. "fallback": news first, the whole web only when news comes up short.
_NEWS, _BOTH, _FALLBACK = "news", "both", "fallback"

# The search for what people there already use instead of the pitch, asked the
# way a resident would ask it. "free government existing alternative" found
# pages ABOUT the topic (a Tembisa water-tank pitch got stormwater drainage);
# "where do people in Tembisa get water-tank refill" finds where they get it.
def _alternatives_query(label: str, words: List[str], when: str) -> str:
    return f"where do people in {label} get {' '.join(words[:3])} {when}"


def plan_searches(place: Dict[str, str], subjects: List[str],
                  words: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Every search a pitch runs, each tagged with how to run it and what it is for.

    The place-news search is news only: it asks what is going on there now. The
    pitch-words search reads news AND the web, because the specific thing a
    pitch is about (a pickup point, a clinic's hours) lives on a health or city
    page far more often than in the news. Subject searches fall back to the web
    only when news is short. The last search, only when the pitch has words of
    its own, asks what people there use today instead.
    """
    out = []
    for i, q in enumerate(build_queries(place, subjects, words)):
        mode = _NEWS if i == 0 else (_BOTH if words and i == 1 else _FALLBACK)
        out.append({"q": q, "mode": mode, "kind": "local"})
    if words:
        when = datetime.now().strftime("%B %Y")
        out.append({"q": _alternatives_query(place["label"], words, when),
                    "mode": _BOTH, "kind": "alternatives"})
        # Free public programmes are national and rarely named with the suburb:
        # the resident-style search alone lost Sunnyside's free chronic-medicine
        # pickup programme (CCMDD), the option that pitch most had to answer.
        out.append({"q": f"free government {' '.join(words[:3])} programme South Africa {when}",
                    "mode": _BOTH, "kind": "alternatives"})
    return out


def search_plan(text: str) -> Optional[Dict[str, Any]]:
    """What a pitch WOULD search for, without searching. None when it names no place.

    Everything here is decided before any request goes out, so the screen can
    show the user exactly what is about to be searched, and why.
    """
    place = detect_place(text)
    if not place:
        return None
    subjects = detect_subjects(text)
    words = pitch_words(text, place)
    searches = plan_searches(place, subjects, words)
    return {"place": place, "subjects": subjects, "words": words,
            "searches": searches, "queries": [x["q"] for x in searches]}


# ─────────────────────────────────────────────────────────────
# Cache — keyed by place + subjects, not by day, because the whole point
# is that a place is searched once and re-used by every later run that
# mentions it. Same 24h TTL and same snippet shape as the national block.
# ─────────────────────────────────────────────────────────────

def _enabled() -> bool:
    # Off by default until measured over ~10 real pitches (see the plan).
    return os.environ.get("QUERY_CONTEXT", "0").lower() not in ("0", "false", "no")


def _cache_key(place: Dict[str, str], subjects: List[str],
               words: Optional[List[str]] = None) -> str:
    # The pitch's words are part of the key (sorted, so word order does not
    # matter): the same suburb asked about a different thing is a different search.
    raw = (place["label"].lower() + "|" + ",".join(subjects)
           + "|" + ",".join(sorted(words or [])))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cache_path(key: str) -> str:
    return os.path.join(Config.DATA_ROOT, "cache", "query_context", f"{key}.json")


def _read_cache(key: str) -> Optional[Dict[str, Any]]:
    try:
        with open(_cache_path(key), "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("block") and time.time() - float(d.get("ts", 0)) < _CACHE_TTL_HOURS * 3600:
            return d
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def _write_cache(key: str, block: str, place: Dict[str, str],
                 sources: Optional[List[Dict[str, str]]] = None) -> None:
    try:
        path = _cache_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "place": place["label"], "block": block,
                       "sources": sources or []}, f)
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
    # Job adverts: a live Sunnyside run turned "is hiring a Technical Assistant"
    # into a local fact.
    r"\bis hiring\b", r"\bvacanc(?:y|ies)\b", r"\bapply now\b", r"\bjob (?:opening|advert)",
))


# Sites whose snippets are posts, clips or listings rather than reporting. A
# live Sunnyside run cited Instagram, Facebook, YouTube and an expo page.
_JUNK_SITES = (
    "instagram.com", "facebook.com", "youtube.com", "tiktok.com", "twitter.com",
    "x.com", "linkedin.com", "pinterest.com", "reddit.com", "quora.com",
    "eventbrite", "allevents", "expo.com", "yelp.", "tripadvisor", "booking.com",
    "airbnb", "property24", "privateproperty", "gumtree", "wikipedia.org",
)


def _is_junk_site(link_or_source: str) -> bool:
    """True when the result comes from a social, event, listing or directory site."""
    low = (link_or_source or "").lower()
    return any(site in low for site in _JUNK_SITES)


def _is_junk(snippet: str) -> bool:
    """True for search results that are not local news about the place."""
    return any(p.search(snippet or "") for p in _JUNK_PATTERNS)


def _gather_snippets(searches: List[Any]) -> List[Dict[str, str]]:
    """Real search snippets for this place, each keeping its own link.

    Same shape as sa_context._gather_snippets, so _render_sources and the judge
    take these unchanged, plus a "kind" saying which search found it. Takes
    plan_searches() entries; a bare query string runs as a local fallback search.
    """
    from .serper_service import SerperService
    serper = SerperService()
    if not serper.is_available():
        return []
    sources: List[Dict[str, str]] = []
    seen: set = set()

    def _take(res, kind: str) -> int:
        added = 0
        if not res.get("success"):
            return 0
        for item in res.get("results", []):
            sn = (item.get("snippet") or item.get("title") or "").strip()
            link = (item.get("link") or "").strip()
            src = (item.get("source") or "").strip()
            if not sn or _is_junk(sn) or _is_junk_site(link or src) or (link and link in seen):
                continue
            seen.add(link)
            sources.append({"snippet": sn, "link": link, "source": src, "kind": kind})
            added += 1
        return added

    for s in searches:
        if isinstance(s, str):
            s = {"q": s, "mode": _FALLBACK, "kind": "local"}
        q, mode, kind = s["q"], s.get("mode", _FALLBACK), s.get("kind", "local")
        got = _take(serper.search(q, num_results=6, news=True), kind)
        if mode == _BOTH or (mode == _FALLBACK and got < _MIN_SNIPPETS):
            _take(serper.search(q, num_results=6), kind)
    return sources[:24]


# Full articles are read only for the best couple of results, and only the
# paragraphs about the place or the pitch are kept: a snippet is two lines,
# the paragraph around it is where the queue length or the pickup point is.
_MAX_PAGES = 2
_PAGE_CHARS = 3000


def _read_pages(sources: List[Dict[str, str]], place: Dict[str, str],
                words: List[str]) -> List[Dict[str, str]]:
    """Read the best 1-2 result pages in full; return their relevant paragraphs
    as extra sources (same shape, same kind). Empty on any failure or no reader."""
    try:
        from .jina_service import JinaService
        reader = JinaService()
        if not reader.is_available():
            return []
    except Exception:  # noqa: BLE001
        return []
    terms = [t.lower() for t in [place.get("name", "")] + list(words or []) if t]

    def _hits(text: str) -> int:
        low = (text or "").lower()
        return sum(1 for t in terms if t in low)

    ranked = sorted((s for s in sources if s.get("link")),
                    key=lambda s: _hits(s.get("snippet", "")), reverse=True)
    out: List[Dict[str, str]] = []
    for s in ranked:
        if len(out) >= _MAX_PAGES or _hits(s.get("snippet", "")) == 0:
            break
        res = reader.scrape(s["link"], timeout=20.0)
        if not res.get("success"):
            continue
        keep, size = [], 0
        for para in re.split(r"\n\s*\n", res.get("content") or ""):
            para = para.strip()
            # Menus and link lists: their link addresses carry the pitch's words
            # ("...taxi-fares-in-limpopo/#"), so drop any paragraph of links and
            # judge the rest on its words alone, not its URLs.
            if para.count("](") >= 2:
                continue
            para = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", para).strip()
            if len(para) < 60 or _hits(para) == 0 or _is_junk(para):
                continue
            keep.append(para)
            size += len(para)
            if size >= _PAGE_CHARS:
                break
        if keep:
            out.append({"snippet": " ".join(keep)[:_PAGE_CHARS], "link": s["link"],
                        "source": s.get("source", ""), "kind": s.get("kind", "local")})
    return out


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
        f"Leave out street addresses, awards, rankings and nominations, and "
        f"one-off events (a single march, a single memorandum) unless the "
        f"snippets show they keep happening — none of these is a condition. "
        f"If the snippets support fewer "
        f"than three such bullets, output fewer. Output 3-5 short, plain "
        f"present-tense bullet lines. No preamble, no closing line."
    )
    user = f"Today is {today}.\n\nSNIPPETS:\n{joined}\n\nWhat is currently true in {label} (3-5 bullets):"
    return _run_distil(system, user, snippets, label, "query_context", max_tokens=400)


def _distil_alternatives(sources: List[Dict[str, str]], place: Dict[str, str],
                         words: List[str]) -> Optional[str]:
    """1-3 bullets on what people there use TODAY instead of the pitch. None on failure.

    Same grounding rules as the local block. This is what a persona weighs a
    pitch against ("why pay when I collect it free at the clinic?"), so it only
    names options the snippets show exist; it never judges them or the pitch.
    """
    snippets = [s["snippet"] for s in sources if s.get("snippet")]
    if not snippets or not (Config.LLM_API_KEY and Config.LLM_MODEL_NAME):
        return None
    label = place["label"]
    need = " ".join(words or []) or "this"
    today = datetime.now().strftime("%d %B %Y")
    joined = "\n".join(f"- {s}" for s in snippets)
    system = (
        f"You read real web-search snippets and list what people in {label}, South "
        f"Africa, can ALREADY use today for: {need}. STRICT RULES: use ONLY what the "
        f"snippets support; never add an option not present in them; include a "
        f"number or price only if a snippet gives one. List an option ONLY if a "
        f"person could pick it INSTEAD of {need}: it meets the same need in their "
        f"hands today (a government programme, a free service, a shop, an app). "
        f"Something merely about the same topic does not count: for a water-tank "
        f"refill, a water truck or a tank supplier counts; pipe upgrades or drainage "
        f"works do not. It must be available in or near {label} or across South "
        f"Africa. Name the option and what it does. Never rate it, never compare it "
        f"to anything, never name a private individual. If the snippets show no "
        f"such option, output nothing at all: an empty list is correct then. "
        f"Output 1-3 short, plain present-tense bullet lines. No preamble."
    )
    user = f"Today is {today}.\n\nSNIPPETS:\n{joined}\n\nWhat people there can already use (1-3 bullets):"
    return _run_distil(system, user, snippets, label, "query_context_alternatives",
                       max_tokens=250, alternatives=True)


def _run_distil(system: str, user: str, snippets: List[str], label: str,
                tag: str, max_tokens: int, alternatives: bool = False) -> Optional[str]:
    """Generate, judge against the snippets, retry once; None if it still fails."""
    key = Config.LLM_API_KEY
    model = Config.LLM_MODEL_NAME

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
            max_tokens=max_tokens,
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Keep bullet lines only ("nothing found" prose is not a fact), written
        # the one way the block and the screen read them.
        return "\n".join("- " + l.strip()[1:].strip() for l in text.splitlines()
                         if l.strip()[:1] in ("-", "*", "•") and l.strip()[1:].strip())

    try:
        from .judge_service import (get_judge_service, judge_best_of, record_judgement,
                                    sa_context_judge_enabled)
        if sa_context_judge_enabled():
            svc = get_judge_service(cheap=True)
            text, judge_result, regenerated = judge_best_of(
                generate=_generate,
                judge=lambda t: svc.judge_sa_context(t, snippets, place=label,
                                                     alternatives=alternatives),
            )
            record_judgement(tag, judge_result, regenerated=regenerated)
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
        logger.warning("Local context distil failed for %s: %s", label, e)
        return None


def local_context(text: str) -> Optional[str]:
    """The 'NEAR YOU' block for this pitch, or None.

    Fails safe at every step — disabled, no place named, no search, no snippets,
    no model, or a failed judge all return None, and the caller is left with the
    national block exactly as it is today.
    """
    if not _enabled():
        return None
    report = local_report(text)
    return report["block"] if report else None


def _source_list(sources: List[Dict[str, str]], limit: int = 8,
                 place: str = "") -> List[Dict[str, str]]:
    """Deduplicated {source, link} pairs — the same list the block's footer cites.

    With `place`, results whose text names the place come first, so the few
    sources shown are the ones about it rather than whichever the search
    happened to return first (a football site, for a Polokwane pitch).
    """
    if place:
        low = place.lower()
        sources = sorted(sources, key=lambda s: low not in (s.get("snippet") or "").lower())
    seen, out = set(), []
    for s in sources:
        label = s.get("source") or s.get("link")
        if not label or label in seen:
            continue
        seen.add(label)
        out.append({"source": label, "link": s.get("link") or ""})
    return out[:limit]


_ALT_HEADING = "WHAT PEOPLE THERE USE TODAY"


def _points(block: Optional[str], section: str = "local") -> List[str]:
    """The bullet lines of one section of a framed block ("local" or
    "alternatives"), without the headings or the sources footer."""
    out, current = [], "local"
    for line in (block or "").splitlines():
        if line.startswith("Sources searched"):
            break
        if line.startswith(_ALT_HEADING):
            current = "alternatives"
        elif line.startswith("- ") and current == section:
            out.append(line[2:].strip())
    return out


def local_report(text: str) -> Optional[Dict[str, Any]]:
    """The local search for this pitch AND what happened to it, or None if no place.

    Not gated by QUERY_CONTEXT: panels call this directly (the flag still gates
    the sim path through local_context). Returns:
      place, subjects, queries  — what was searched, decided before searching
      status                    — "found", "cached", "thin" or "dropped"
      block                     — the framed NEAR YOU block for the prompt, or None
      points, alternatives      — the block's local facts, and what people there
                                  already use instead of the pitch
      sources                   — where they came from
    """
    plan = search_plan(text)
    if not plan:
        return None
    place = plan["place"]
    report: Dict[str, Any] = {
        "place": place["label"], "subjects": plan["subjects"], "queries": plan["queries"],
        "status": "", "block": None, "points": [], "alternatives": [], "sources": [],
    }
    key = _cache_key(place, plan["subjects"], plan["words"])
    cached = _read_cache(key)
    if cached is not None:
        report.update(status="cached", block=cached["block"],
                      sources=cached.get("sources") or [])
        report["points"] = _points(report["block"])
        report["alternatives"] = _points(report["block"], "alternatives")
        return report
    sources = _gather_snippets(plan["searches"])
    sources = sources + _read_pages(sources, place, plan["words"])
    local = [s for s in sources if s.get("kind", "local") == "local"]
    alt_sources = [s for s in sources if s.get("kind") == "alternatives"]
    # Too little real local news to write 3-5 grounded bullets from. Padding a
    # thin search is exactly how a block ends up saying nothing, or saying
    # something national under a local heading.
    block = _distil_local(local, place) if len(local) >= _MIN_SNIPPETS else None
    alts = (_distil_alternatives(alt_sources, place, plan["words"])
            if len(alt_sources) >= 2 else None)
    if not block and not alts:
        thin = len(local) < _MIN_SNIPPETS and len(alt_sources) < 2
        logger.info("No local block for %s (%d local, %d alternative snippets).",
                    place["label"], len(local), len(alt_sources))
        report["status"] = "thin" if thin else "dropped"
        return report
    from .sa_context import _render_sources
    today = datetime.now().strftime("%d %B %Y")
    body = block or ""
    if alts:
        body += (("\n" if body else "") + f"{_ALT_HEADING} (options that already exist, "
                 f"from search; weigh the idea against these):\n{alts}")
    framed = (
        f"NEAR YOU ({place['label']} — as of {today}) — local conditions where this\n"
        f"is set. These are facts about the AREA, not about your own household\n"
        f"income or budget:\n{body}"
        f"{_render_sources(sources)}"
    )
    listed = _source_list(sources, place=place["name"])
    _write_cache(key, framed, place, listed)
    logger.info("Fetched local context for %s (%d snippets).", place["label"], len(sources))
    report.update(status="found", block=framed, points=_points(framed),
                  alternatives=_points(framed, "alternatives"), sources=listed)
    return report
