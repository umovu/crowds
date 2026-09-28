"""
Mechanism-card extractor — programmatic Stages 1-4 of docs/EXTRACTION_PROTOCOL.md.

The LLM harvests passages, chains them, scopes them and drafts the card;
deterministic code then runs the Stage-5 contamination lint. Output is a
draft worksheet + card JSON for HUMAN PROOFREADING — nothing this script
produces is a shipped card until a person signs off Stage 5.

Usage:
  <venv-python> backend/scripts/extract_card.py \
      --card-id ainslie-communal-cattle \
      --paper path/to/paper1.txt [--paper path/to/paper2.txt ...] \
      --citation "Ainslie (2013), JSAS" [--citation "..." ...] \
      [--extra-tags communal_farmer,livestock_owner] [--research-tier]

Papers must be plain text (.txt/.md). Convert PDFs first.
Outputs: docs/extraction/<card-id>.worksheet.md + <card-id>.card.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
MAIN_REPO_ROOT = Path("D:/Fub-agentsociety")
load_dotenv(MAIN_REPO_ROOT / ".env")

MAX_PAPER_CHARS = 300_000  # per paper; covers full text for all current sources except
                           # book-length works (those need manual chapter-slicing first)


def get_client(research_tier: bool, model_override: str | None, base_url_override: str | None,
               api_key_override: str | None):
    if model_override or base_url_override or api_key_override:
        # Explicit override (e.g. a ModelScope-hosted model) — env vars are the fallback
        # for whichever piece isn't overridden, never the source of truth once overriding.
        model = model_override or sys.exit("--model required when overriding base-url/api-key")
        base = base_url_override or sys.exit("--base-url required when overriding model")
        key = (api_key_override or os.environ.get("DASHSCOPE_API_KEY")
               or os.environ.get("MODELSCOPE_API_KEY") or os.environ.get("LLM_API_KEY"))
        if not key:
            sys.exit("No API key: pass --api-key or set DASHSCOPE_API_KEY")
        return OpenAI(api_key=key, base_url=base), model

    prefix = "LLM" if research_tier else "SIM_LLM"
    key = os.environ.get(f"{prefix}_API_KEY")
    base = os.environ.get(f"{prefix}_BASE_URL")
    model = os.environ.get(f"{prefix}_MODEL") or os.environ.get(f"{prefix}_MODEL_NAME")
    if not (key and base and model):
        sys.exit(f"Missing {prefix}_* env vars")
    return OpenAI(api_key=key, base_url=base), model


def closed_vocabulary(extra: list[str]) -> set[str]:
    data = json.loads(
        (MAIN_REPO_ROOT / "backend/app/data/persona_library/personas.json").read_text(encoding="utf-8")
    )
    vocab = {p["actor_archetype"] for p in data["personas"] if p.get("actor_archetype")}
    return vocab | set(extra)


def thinking_off(model: str) -> dict:
    """Provider-specific switch that turns reasoning ("thinking") mode off.

    Reasoning models default it on. Qwen reads `enable_thinking`; DeepSeek reads
    `thinking.type` and silently ignores the Qwen flag — it then returns the whole
    answer in `reasoning_content` with an EMPTY `content`, which surfaced here as
    "No JSON in model reply" on every Stage 1 call. Same shapes as
    app/__init__._disable_thinking_on_litellm, which fixed this for the sim path.
    """
    name = (model or "").lower()
    if "deepseek" in name:
        return {"thinking": {"type": "disabled"}}
    if "qwen" in name:
        return {"enable_thinking": False}
    return {}


# ── Spend cap ────────────────────────────────────────────────────────────────
# Card building shares a wallet with the hosted product, so every call made through
# chat() is costed from the provider's own token counts and added to a ledger, and a
# call that could push the ledger past CARD_SPEND_CAP_USD is refused before it is made.
# Rates are DeepSeek V4 Pro's (USD per million tokens; verified 2026-09-18), doubled in
# peak hours. Every model is costed at Pro rates, so a cheaper model only over-counts.
SPEND_LEDGER = WORKTREE_ROOT / "docs" / "extraction" / ".spend.json"
RATES = {"in": 0.66, "cached": 0.022, "out": 1.98}
PEAK_UTC_HOURS = set(range(1, 4)) | set(range(6, 10))  # weekdays


class SpendCapReached(RuntimeError):
    pass


def _peak(now=None) -> bool:
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    return now.weekday() < 5 and now.hour in PEAK_UTC_HOURS


def call_cost(prompt_tokens: int, cached_tokens: int, completion_tokens: int, peak: bool) -> float:
    fresh = max(0, prompt_tokens - cached_tokens)
    usd = (fresh * RATES["in"] + cached_tokens * RATES["cached"] + completion_tokens * RATES["out"]) / 1e6
    return usd * (2 if peak else 1)


def spent() -> dict:
    try:
        return json.loads(SPEND_LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"usd": 0.0, "calls": 0, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}


def _cap() -> float | None:
    raw = (os.environ.get("CARD_SPEND_CAP_USD") or "").strip()
    return float(raw) if raw else None


def _check_cap(system: str, user: str, max_tokens: int) -> None:
    cap = _cap()
    if cap is None:
        return
    worst = call_cost((len(system) + len(user)) // 3, 0, max_tokens, _peak())
    so_far = spent()["usd"]
    if so_far + worst > cap:
        raise SpendCapReached(f"Spend cap ${cap:.2f}: ${so_far:.4f} spent, and this call could cost "
                              f"up to ${worst:.4f}. Raise CARD_SPEND_CAP_USD to go on.")


def _record(resp) -> None:
    u = getattr(resp, "usage", None)
    if u is None:
        return
    prompt, out = u.prompt_tokens or 0, u.completion_tokens or 0
    cached = getattr(u, "prompt_cache_hit_tokens", None)
    if cached is None:
        details = getattr(u, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
    led = spent()
    led["usd"] = round(led["usd"] + call_cost(prompt, cached or 0, out, _peak()), 6)
    led["calls"] += 1
    led["prompt_tokens"] += prompt
    led["cached_tokens"] += cached or 0
    led["completion_tokens"] += out
    SPEND_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    SPEND_LEDGER.write_text(json.dumps(led, indent=1), encoding="utf-8")


def chat(client, model, system: str, user: str, max_tokens: int = 8000) -> str:
    _check_cap(system, user, max_tokens)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=max_tokens,
        extra_body=thinking_off(model),
    )
    _record(resp)
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        # An empty answer is a transport/mode failure, not malformed JSON: a repair pass
        # would hand the model an empty "previous reply" and accept whatever comes back.
        raise RuntimeError(
            f"Model {model} returned an empty answer (finish_reason="
            f"{resp.choices[0].finish_reason}). Usually reasoning mode still on, or the "
            "token budget spent before any output.")
    return content


def parse_json_block(text: str):
    """Extract the first JSON object/array from a model reply."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError(f"No JSON in model reply:\n{text[:500]}")
    return json.loads(raw[start:])


def chat_json(client, model, system: str, user: str, max_tokens: int = 8000):
    """chat() + parse_json_block() with one repair retry.

    Models occasionally emit malformed JSON (unescaped quotes inside a
    quoted passage, or truncation) — retry once by handing the broken
    output back and asking for a strict fix rather than failing the whole
    extraction on one bad response.
    """
    reply = chat(client, model, system, user, max_tokens)
    try:
        return parse_json_block(reply)
    except (json.JSONDecodeError, ValueError) as e:
        debug_path = WORKTREE_ROOT / "docs" / "extraction" / "_last_failed_reply.txt"
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(reply, encoding="utf-8")
        print(f"  (JSON parse failed: {e} — raw reply saved to {debug_path} — retrying with a repair pass)")
        repair_user = (
            "Your previous reply was not valid JSON. Reproduce the SAME content "
            "as valid, complete JSON: escape every double-quote inside a string "
            "value as \\\", do not truncate, and output ONLY the JSON, no "
            "markdown fences, no commentary.\n\nPREVIOUS (broken) REPLY:\n" + reply
        )
        repaired = chat(client, model, system, repair_user, max_tokens)
        try:
            return parse_json_block(repaired)
        except (json.JSONDecodeError, ValueError) as e2:
            debug_path2 = WORKTREE_ROOT / "docs" / "extraction" / "_last_failed_repair.txt"
            debug_path2.write_text(repaired, encoding="utf-8")
            raise ValueError(
                f"Repair pass also failed ({e2}). Original saved to {debug_path}, "
                f"repair attempt saved to {debug_path2}."
            ) from e2


SYSTEM = (
    "You are an evidence extractor for a South African policy-simulation project. "
    "You follow the extraction protocol EXACTLY. You never invent content that is "
    "not supported by the paper text. You never carry a statistic, percentage, "
    "currency amount or sample size into any output field. You output only the "
    "requested JSON, no commentary."
)

STAGE1_PROMPT = """STAGE 1 — HARVEST (thematic synthesis).
From the paper text below, extract every passage where the paper explains WHY
people in the target segment act as they do (reasoning, motivations, evaluative
rules). Ignore pure outcomes/correlations/statistics.

Target segment(s): {segments}

Return JSON array; each item:
{{"id": "P1", "passage": "<verbatim quote or close paraphrase>",
  "voice": "participant" | "author-interpretation",
  "location": "<section heading or approximate position>",
  "source": "{source}"}}

Rules: 5-20 passages. Prefer participant quotes. If the paper documents no
segment reasoning at all, return [].

PAPER TEXT:
{text}"""

STAGE2_PROMPT = """STAGE 2 — CHAIN (process tracing).
Group the harvested passages below into AT MOST 5 causal chains. Each chain is
an entity-activity sequence:
  actor's situation -> therefore evaluative rule -> therefore behaviour ->
  therefore how a NEW product/policy gets read.
Every link must cite passage IDs. If a link has no supporting passage, mark it
"[inferred]".

Return JSON array; each item:
{{"id": "C1", "chain": "<the full arrow-form chain>",
  "passages": ["P1","P2"], "inferred_links": ["<any [inferred] link or empty>"]}}

PASSAGES:
{passages}"""

STAGE3_PROMPT = """STAGE 3 — SCOPE (realist CMO).
For each chain, write the CMO sentence and scope it.

segment_tags is a REQUIRED, non-empty selection from this closed list — these
are archetype CATEGORIES the chain's people belong to, not literal
descriptions, so map by underlying situation, not exact wording. Example: a
paper describing "unemployed women relying on grants and irregular income" is
the archetype grant_dependent_survivor and/or unemployed_youth, even though
neither phrase appears in the paper. You MUST select at least one tag from
this list for every chain — leaving segment_tags empty is a FAILURE, not a
safe default:
{vocab}

negative_scope is for OTHER tags from the SAME list that do NOT apply (to
prevent over-binding later) — it does not replace populating segment_tags,
and it is not where you park chains you're unsure how to tag.

Do NOT invent a tag outside the list above.

Every tag you select must be traceable to the chain's own passages (P-numbers
already attached to the chain). Do not add a tag because it seems plausible
for "township life" in general — only because the chain's specific passages
describe that situation. For each tag, give the passage ID(s) that justify it;
a tag with no justifying passage must not be included.

Return JSON array; each item:
{{"chain_id": "C1",
  "cmo": "For [segment], in [context], [mechanism], producing [outcome pattern].",
  "segment_tags": ["at least one tag from the list, required"],
  "segment_tags_justification": {{"tag_name": ["P1", "P2"]}},
  "negative_scope": "does NOT apply to <other tags from the list>",
  "region": "<province/site from the paper>", "year_range": "<fieldwork years>"}}

CHAINS:
{chains}"""

STAGE4_PROMPT = """STAGE 4 — FORMALIZE (draft card).
Compress each chain into ONE claim: a single mechanism sentence that preserves the
"because", kept together with everything that belongs to it (its chain, passages,
evaluative rule, objections and vocabulary).

Write it as a general decision RULE, not a first-person adoption statement.
Do NOT write "I would adopt a new product if..." or any variant — that is a
template artefact, not a mechanism. Instead state the underlying rule plainly,
the way these examples do:
- "Trust is the binding constraint: face-to-face accountability with people
  who know your circumstances beats institutional guarantees"
- "The lump sum is mentally earmarked for a deliberate purchase, not absorbed
  into daily spending"
A good mechanism is a compact causal claim a persona could apply, unprompted,
to a scenario the paper never discussed — it is not a hypothetical sentence
about "a new product". Drop descriptive findings that aren't decision rules.

Inside each claim, also extract:
- evaluative_rules: the chain's "therefore evaluative rule" link, restated as a
  short imperative decision heuristic the segment applies when weighing a
  purchase/adoption (e.g. "Judge a school by academic outcomes, not proximity",
  "Trust people who know your circumstances over institutional guarantees").
  Usually one per claim; leave it out when the rule is not a weighing/filtering
  heuristic. These drive HOW a persona reasons about wanting something — they must
  be rules of evaluation, never statements of who the person is.
- objections: the questions this segment actually asks of a new product/policy
  BECAUSE of this claim, phrased first-person, 0-1 per claim (2-4 across the card)
- vocabulary: terms the segment uses when reasoning this way, ATTESTED in the
  passages (participant voice preferred), 1-2 per claim (3-6 across the card)
- needs: always [] in a draft. The human reviewer writes who each claim is about
  from persona facts; never guess it.

For the card, also extract:
- confidence: one line per the paper's method/scope (e.g. "ethnographic,
  single region, fieldwork 2008-2012 — mechanisms durable, magnitudes unknown")
- comb_gaps: which of capability/opportunity/motivation the card does NOT
  cover (record, never invent coverage)

HARD RULES: no digits or currency amounts anywhere in claim text, objections,
vocabulary or evaluative rules; claim_type is "qualitative" or "mixed_methods";
segment_tags come only from Stage 3 output.

Return ONE JSON object:
{{"id": "{card_id}",
  "citation": {citations},
  "segment_tags": [...],
  "claims": [{{"text": "...", "needs": [], "chain_id": "C1", "passages": ["P1"],
              "evaluative_rules": ["..."], "objections": ["..."], "vocabulary": ["..."]}}],
  "claim_type": "qualitative", "region": "...", "year_range": "...",
  "confidence": "...", "comb_gaps": [...]}}

CHAINS:
{chains}

CMO SCOPES:
{scopes}

PASSAGES (for vocabulary attestation):
{passages}"""


def lint_card(card: dict, vocab: set[str]) -> list[str]:
    """Deterministic Stage-5 contamination checks. Returns list of violations."""
    errs = []
    claims = card.get("claims", [])
    for i, claim in enumerate(claims):
        words = [claim.get("text", ""), *claim.get("objections", []),
                 *claim.get("vocabulary", []), *claim.get("evaluative_rules", [])]
        for item in words:
            if re.search(r"\d", item):
                errs.append(f"NUMBER in claim {i}: {item!r}")
            if re.search(r"\bR\s?\d|percent|%", item, re.I):
                errs.append(f"CURRENCY/PERCENT in claim {i}: {item!r}")
        if not claim.get("chain_id") or not claim.get("passages"):
            errs.append(f"Claim {i} has no provenance (chain/passages)")
        if "needs" not in claim:
            errs.append(f"Claim {i} has no needs rule (a draft uses [])")
    bad_tags = [t for t in card.get("segment_tags", []) if t not in vocab]
    if bad_tags:
        errs.append(f"TAGS outside closed vocabulary: {bad_tags} (allowed: {sorted(vocab)})")
    if card.get("claim_type") not in ("qualitative", "mixed_methods"):
        errs.append(f"claim_type must be 'qualitative' or 'mixed_methods', got {card.get('claim_type')!r}")
    for field in ("id", "citation", "segment_tags", "claims", "confidence"):
        if not card.get(field):
            errs.append(f"MISSING field: {field}")
    if not claims:
        errs.append("No claims survived — paper may fail Stage 0 eligibility")
    if len(claims) > 5:
        errs.append("More than 5 claims — merge or cut (findings, not mechanisms?)")
    return errs


def write_worksheet(path: Path, card_id: str, citations: list[str], papers: list[str],
                    passages, chains, scopes, card, lint_errs):
    lines = [f"# Worksheet: {card_id}", "",
             "> DRAFT — machine-extracted (Stages 1-4). Stage 5 human sign-off REQUIRED",
             "> before this card ships. Proofread every passage against the paper.", "",
             "Sources:"]
    lines += [f"- {c}" for c in citations]
    lines += ["", "## Stage 0 — Eligibility", "",
              f"- Verdict: {'PASS (machine)' if passages else 'REJECT — no reasoning passages found'}",
              "", "## Stage 1 — Harvested passages", "",
              "| ID | Passage | Voice | Location |", "|----|---------|-------|----------|"]
    for p in passages:
        text = p["passage"].replace("|", "/").replace("\n", " ")
        lines.append(f"| {p['id']} | {text} | {p['voice']} | {p.get('location','')} |")
    lines += ["", "## Stage 2 — Chains", ""]
    for c in chains:
        lines += [f"### {c['id']} (from {', '.join(c.get('passages', []))})", "",
                  f"> {c['chain']}", ""]
        if c.get("inferred_links"):
            for link in c["inferred_links"]:
                if link:
                    lines.append(f"- **[inferred] needs reviewer sign-off:** {link}")
            lines.append("")
    lines += ["## Stage 3 — CMO scope", ""]
    for s in scopes:
        lines += [f"- **{s['chain_id']}**: {s['cmo']}",
                  f"  - segment_tags: {s.get('segment_tags')}",
                  f"  - tag justification (passage IDs): {s.get('segment_tags_justification', {})}",
                  f"  - negative scope: {s.get('negative_scope','')}",
                  f"  - region/years: {s.get('region','')} / {s.get('year_range','')}"]
    lines += ["", "## Stage 4 — Draft card", "", "```json",
              json.dumps(card, indent=2, ensure_ascii=False), "```", "",
              f"- COM-B gaps recorded: {card.get('comb_gaps', [])}", "",
              "## Stage 5 — Gate", ""]
    if lint_errs:
        lines += ["**Deterministic lint: FAILED**", ""]
        lines += [f"- [ ] FIX: {e}" for e in lint_errs]
    else:
        lines += ["Deterministic lint: PASSED (numbers/tags/fields/provenance)"]
    lines += ["", "Human checklist (cannot be automated):", "",
              "- [ ] Passages are faithful to the paper (spot-check against source)",
              "- [ ] Chains follow from passages; `[inferred]` links approved or deleted",
              "- [ ] Vocabulary genuinely attested, not plausible-sounding",
              "- [ ] No identity claims (paper shapes reasoning, never who a persona is)",
              "- [ ] Confidence line is honest about method and scope",
              "- Reviewer: ______  Date: ______  Sign-off: YES / NO", "",
              "## Stage 6 — Validation", "",
              "- Unseen scenario used:", "- Runs / output files:",
              "- Straw-in-the-wind: | Hoop: | Smoking gun: | Doubly decisive:",
              "- Verdict: SHIP / PROVENANCE-ONLY / BACK TO STAGE 4", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--card-id", required=True)
    ap.add_argument("--paper", action="append", required=True,
                    help="plain-text paper file (.txt/.md); repeat for a cluster")
    ap.add_argument("--citation", action="append", required=True,
                    help="citation string, one per --paper (order-matched)")
    ap.add_argument("--segments", default="",
                    help="hint: target segment(s) for Stage 1, e.g. 'communal farmers'")
    ap.add_argument("--extra-tags", default="",
                    help="comma-separated tags to allow beyond current library archetypes "
                         "(e.g. planned archetypes like communal_farmer)")
    ap.add_argument("--research-tier", action="store_true",
                    help="use LLM_* (research tier) instead of SIM_LLM_*; extraction is "
                         "offline+one-time so higher quality can be worth it")
    ap.add_argument("--model", default=None,
                    help="override model id, e.g. a ModelScope-hosted model "
                         "(deepseek-ai/DeepSeek-V3). Requires --base-url too.")
    ap.add_argument("--base-url", default=None,
                    help="override API base URL, e.g. ModelScope's "
                         "https://api-inference.modelscope.cn/v1")
    ap.add_argument("--api-key", default=None,
                    help="override API key; falls back to MODELSCOPE_API_KEY or LLM_API_KEY env var")
    args = ap.parse_args()

    client, model = get_client(args.research_tier, args.model, args.base_url, args.api_key)
    extra = [t.strip() for t in args.extra_tags.split(",") if t.strip()]
    vocab = closed_vocabulary(extra)
    segments = args.segments or ", ".join(extra) or "see paper"

    # Stage 1 per paper (cluster rule: passages pooled)
    passages, pid = [], 1
    for path_str, cite in zip(args.paper, args.citation):
        text = Path(path_str).read_text(encoding="utf-8", errors="replace")[:MAX_PAPER_CHARS]
        print(f"Stage 1: harvesting {path_str} ({len(text)} chars)...")
        items = chat_json(client, model, SYSTEM,
                          STAGE1_PROMPT.format(segments=segments, source=cite, text=text))
        if not isinstance(items, list) or not all(isinstance(it, dict) for it in items):
            sys.exit(f"Stage 1: {path_str} came back as {type(items).__name__} of "
                     f"{sorted({type(i).__name__ for i in items}) if isinstance(items, list) else '-'}"
                     " — expected a list of passage objects. Nothing written.")
        for it in items:
            it["id"] = f"P{pid}"; it["source"] = cite; pid += 1
        passages += items
    print(f"  {len(passages)} passages")
    if not passages:
        sys.exit("Stage 0/1: no reasoning passages found — paper fails eligibility. "
                 "Nothing written.")

    pj = json.dumps(passages, indent=2, ensure_ascii=False)
    print("Stage 2: chaining...")
    chains = chat_json(client, model, SYSTEM, STAGE2_PROMPT.format(passages=pj))
    print(f"  {len(chains)} chains")

    cj = json.dumps(chains, indent=2, ensure_ascii=False)
    print("Stage 3: scoping (CMO)...")
    scopes = chat_json(client, model, SYSTEM,
                       STAGE3_PROMPT.format(vocab=sorted(vocab), chains=cj))
    untagged = [s.get("chain_id") for s in scopes if not s.get("segment_tags")]
    if untagged:
        sys.exit(f"Stage 3: chain(s) {untagged} came back with no segment_tags — "
                 "extraction stopped before wasting a Stage 4 call. Re-run, or the "
                 "paper's population may not map onto the closed vocabulary at all "
                 "(a real coverage gap, not a prompt bug).")

    print("Stage 4: drafting card...")
    card = chat_json(client, model, SYSTEM, STAGE4_PROMPT.format(
        card_id=args.card_id, citations=json.dumps(args.citation),
        chains=cj, scopes=json.dumps(scopes, indent=2, ensure_ascii=False), passages=pj))

    print("Stage 5 (deterministic part): linting...")
    errs = lint_card(card, vocab)
    for e in errs:
        print(f"  LINT: {e}")

    out_dir = WORKTREE_ROOT / "docs" / "extraction"
    out_dir.mkdir(parents=True, exist_ok=True)
    ws = out_dir / f"{args.card_id}.worksheet.md"
    cj_path = out_dir / f"{args.card_id}.card.json"
    write_worksheet(ws, args.card_id, args.citation, args.paper,
                    passages, chains, scopes, card, errs)
    cj_path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDraft worksheet: {ws}\nDraft card:      {cj_path}")
    print("Lint:", "FAILED — fix before review" if errs else "passed")
    print("NEXT: proofread the worksheet against the paper, complete the human "
          "checklist, then validate (Stage 6).")


if __name__ == "__main__":
    main()
