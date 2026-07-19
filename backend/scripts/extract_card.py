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


def chat(client, model, system: str, user: str, max_tokens: int = 8000) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=max_tokens,
        # DashScope reasoning models (e.g. deepseek-v4-pro) default to "thinking"
        # mode and can burn the whole token budget on hidden reasoning before
        # ever emitting the JSON answer. Harmless no-op on models that ignore it.
        extra_body={"enable_thinking": False},
    )
    content = resp.choices[0].message.content or ""
    return content.strip()


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
Compress each chain into ONE mechanism sentence that preserves the "because".

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

Also extract, for each chain, its EVALUATIVE RULE as a standalone item:
- evaluative_rules: the "therefore evaluative rule" link of each chain, restated
  as a short imperative decision heuristic the segment applies when weighing a
  purchase/adoption (e.g. "Judge a school by academic outcomes, not proximity",
  "Trust people who know your circumstances over institutional guarantees").
  Max 5, one per chain at most; drop chains whose rule is not a weighing/filtering
  heuristic. These drive HOW a persona reasons about wanting something — they must
  be rules of evaluation, never statements of who the person is.

Also extract:
- vocabulary: terms the segment actually uses, ATTESTED in the passages
  (participant voice preferred), 3-6 items
- objection_patterns: the questions this segment actually asks of a new
  product/policy, phrased first-person, 2-4 items
- confidence: one line per the paper's method/scope (e.g. "ethnographic,
  single region, fieldwork 2008-2012 — mechanisms durable, magnitudes unknown")
- comb_gaps: which of capability/opportunity/motivation the card does NOT
  cover (record, never invent coverage)

HARD RULES: no digits or currency amounts anywhere in mechanisms/vocabulary/
objection_patterns; claim_type is always "qualitative"; segment_tags come only
from Stage 3 output.

Return ONE JSON object:
{{"id": "{card_id}",
  "citation": {citations},
  "segment_tags": [...],
  "mechanisms": [...],
  "mechanism_provenance": [{{"mechanism_index": 0, "chain_id": "C1", "passages": ["P1"]}}],
  "evaluative_rules": [...],
  "evaluative_rule_provenance": [{{"rule_index": 0, "chain_id": "C1", "passages": ["P1"]}}],
  "vocabulary": [...], "objection_patterns": [...],
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
    for field in ("mechanisms", "vocabulary", "objection_patterns", "evaluative_rules"):
        for item in card.get(field, []):
            if re.search(r"\d", item):
                errs.append(f"NUMBER in {field}: {item!r}")
            if re.search(r"\bR\s?\d|percent|%", item, re.I):
                errs.append(f"CURRENCY/PERCENT in {field}: {item!r}")
    bad_tags = [t for t in card.get("segment_tags", []) if t not in vocab]
    if bad_tags:
        errs.append(f"TAGS outside closed vocabulary: {bad_tags} (allowed: {sorted(vocab)})")
    if card.get("claim_type") != "qualitative":
        errs.append(f"claim_type must be 'qualitative', got {card.get('claim_type')!r}")
    for field in ("id", "citation", "segment_tags", "mechanisms", "confidence"):
        if not card.get(field):
            errs.append(f"MISSING field: {field}")
    prov = card.get("mechanism_provenance", [])
    covered = {p.get("mechanism_index") for p in prov}
    for i in range(len(card.get("mechanisms", []))):
        if i not in covered:
            errs.append(f"Mechanism {i} has no provenance (chain/passages)")
    if not card.get("mechanisms"):
        errs.append("No mechanisms survived — paper may fail Stage 0 eligibility")
    if len(card.get("mechanisms", [])) > 5:
        errs.append("More than 5 mechanisms — merge or cut (findings, not mechanisms?)")
    # evaluative_rules are OPTIONAL (legacy cards predate them) but linted when present.
    rules = card.get("evaluative_rules", [])
    if rules:
        if len(rules) > 5:
            errs.append("More than 5 evaluative_rules — one per chain at most")
        rule_prov = card.get("evaluative_rule_provenance", [])
        covered_rules = {p.get("rule_index") for p in rule_prov}
        for i in range(len(rules)):
            if i not in covered_rules:
                errs.append(f"Evaluative rule {i} has no provenance (chain/passages)")
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
