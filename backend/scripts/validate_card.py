"""
Automated Stage-5 pre-screen for mechanism-card worksheets.

This is NOT a replacement for a human reading the paper — it is a credible
first pass that does the parts which can be checked mechanically for real,
so a human only has to look at what got flagged instead of everything.

Two layers:
  1. Deterministic (no LLM, no trust required):
     - passage faithfulness: fuzzy-matches every harvested passage against
       the actual source texts on disk. A passage that doesn't fuzzy-match
       anything is a real red flag (fabrication or paraphrase drift), not
       a model opinion.
     - vocabulary attestation: same check for the card's `vocabulary` terms.
     - re-runs the Stage-5 contamination lint from extract_card.py.
  2. LLM-judge (one call per card, explicitly a second opinion, not ground
     truth): does each mechanism follow from its cited chain/passages, any
     identity claims, is the confidence line honest about method/scope.

Output per card: <card-id>.validation_report.md next to the worksheet, plus
a verdict: AUTO-APPROVED / NEEDS HUMAN REVIEW / REJECTED. Only NEEDS HUMAN
REVIEW and REJECTED are worth a human's time; AUTO-APPROVED still means
"nothing detectable was wrong", not "definitely correct" — say so to anyone
downstream who asks.

Usage:
  <venv-python> backend/scripts/validate_card.py --card-id stokvels-calibration
  <venv-python> backend/scripts/validate_card.py --all
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_card import get_client, chat_json, lint_card, closed_vocabulary  # noqa: E402

EXTRACTION_DIR = Path(__file__).resolve().parents[2] / "docs" / "extraction"
SOURCES_DIR = EXTRACTION_DIR / "sources"
FUZZY_MATCH_THRESHOLD = 0.55  # below this, a passage is flagged as unverifiable


STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "that", "this", "with", "as", "by", "it", "be", "which",
    "at", "from", "their", "its", "they", "he", "she", "we", "i", "you",
    "not", "but", "have", "has", "had", "will", "would", "could", "should",
    "than", "then", "so", "such", "these", "those", "there", "when", "who",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower())
            if len(w) > 3 and w not in STOPWORDS}


def word_ngrams(text: str, n: int = 6) -> set[str]:
    words = text.split()
    if len(words) < n:
        return set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def load_source_corpus() -> dict[str, dict]:
    """All source texts on disk: normalized text + precomputed significant-word
    set per file (precomputed once — this is the expensive regex pass, and it
    would otherwise re-run per passage per file, which is the real perf cost).
    Also computes each word's document frequency across the corpus, needed to
    down-weight generic words (see best_fuzzy_match).
    """
    corpus = {}
    for f in SOURCES_DIR.glob("*.txt"):
        text = normalize(f.read_text(encoding="utf-8", errors="replace"))
        if text:
            corpus[f.name] = {"text": text, "words": significant_words(text)}
    doc_freq: dict[str, int] = {}
    for entry in corpus.values():
        for w in entry["words"]:
            doc_freq[w] = doc_freq.get(w, 0) + 1
    n_docs = len(corpus)
    corpus["_doc_freq"] = doc_freq
    corpus["_n_docs"] = n_docs
    return corpus


def _idf(word: str, doc_freq: dict, n_docs: int) -> float:
    import math
    return math.log(n_docs / (1 + doc_freq.get(word, 0)))


def best_fuzzy_match(passage: str, corpus: dict[str, dict]) -> tuple[str, float]:
    """Find the source file most likely to contain this passage.

    Two-tier check, NOT SequenceMatcher.quick_ratio() — quick_ratio is a fast
    upper-bound estimate that overestimates similarity on short/unrelated
    strings badly enough to pass a fabricated passage (verified in testing).

    Tier 1 (strong signal): a distinctive 6-word shingle from the passage
    appears verbatim in a source — reliable for near-verbatim participant
    quotes, short-circuits with score 1.0.
    Tier 2 (weaker signal, for paraphrased author-interpretation passages):
    IDF-weighted word overlap, not plain overlap fraction. Plain overlap
    against a huge document (e.g. a 977k-char thesis) is nearly useless —
    generic words like "members" or "decided" appear in almost any large
    text, inflating the score regardless of topical relevance (verified in
    testing: a fabricated Mars/bitcoin sentence scored 0.64 against an
    unrelated source on plain overlap). Weighting each matched word by how
    RARE it is across the whole corpus means only matches on distinctive,
    topic-specific vocabulary (stokvel, kraal, grocery) drive the score up;
    generic word matches barely move it.
    """
    p = normalize(passage)
    if len(p) < 15:
        return ("", 0.0)  # too short to judge reliably
    p_words = significant_words(p)
    if not p_words:
        return ("", 0.0)
    p_ngrams = word_ngrams(p, 6)

    doc_freq, n_docs = corpus["_doc_freq"], corpus["_n_docs"]
    total_idf = sum(_idf(w, doc_freq, n_docs) for w in p_words) or 1.0

    best_file, best_score = "", 0.0
    for fname, entry in corpus.items():
        if fname.startswith("_"):
            continue
        text, text_words = entry["text"], entry["words"]
        if p_ngrams and any(ng in text for ng in p_ngrams):
            return (fname, 1.0)
        matched_idf = sum(_idf(w, doc_freq, n_docs) for w in p_words if w in text_words)
        score = matched_idf / total_idf
        if score > best_score:
            best_score, best_file = score, fname
    return (best_file, round(best_score, 3))


def parse_worksheet(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    passages = []
    for m in re.finditer(
        r"^\|\s*(P\d+)\s*\|\s*(.*?)\s*\|\s*(participant|author-interpretation)\s*\|\s*(.*?)\s*\|\s*$",
        text, re.M,
    ):
        passages.append({"id": m.group(1), "passage": m.group(2),
                         "voice": m.group(3), "location": m.group(4)})

    chains = []
    for m in re.finditer(r"^### (C\d+).*?\n\n> (.+?)(?=\n\n|\Z)", text, re.S | re.M):
        chains.append({"id": m.group(1), "chain": m.group(2).strip()})

    inferred = re.findall(r"\*\*\[inferred\] needs reviewer sign-off:\*\* (.+)", text)

    card_match = re.search(r"## Stage 4 — Draft card\s*\n\s*```json\s*\n(.*?)\n```", text, re.S)
    card = json.loads(card_match.group(1)) if card_match else None

    return {"passages": passages, "chains": chains, "inferred_links": inferred, "card": card}


JUDGE_SYSTEM = (
    "You are a skeptical second reviewer checking a machine-drafted mechanism "
    "card before it ships into a production system. You are NOT the original "
    "extractor — assume it may have made mistakes and look for them. Be "
    "concrete: cite the specific mechanism, chain, or passage ID that is the "
    "problem. If nothing is wrong, say so plainly rather than inventing a "
    "concern to seem thorough."
)

JUDGE_PROMPT = """Review this mechanism card draft against its own chains and passages.

Check each of these, one by one:

1. MECHANISM-CHAIN FIT: for each mechanism in the card, does it actually
   follow from the chain and passages cited as its provenance? Flag any
   mechanism that overstates, contradicts, or drifts from what its cited
   chain/passages support.
2. IDENTITY CLAIMS: does any mechanism, vocabulary term, or objection pattern
   assert who a person IS (their identity, character, worth) rather than a
   reasoning pattern they use? Papers should shape reasoning, never author
   identity. Flag violations.
3. INFERRED LINKS: for each [inferred] chain link listed, is it a reasonable
   inference from the passages, or an unsupported leap? Recommend APPROVE or
   REJECT for each.
4. CONFIDENCE HONESTY: does the card's `confidence` field accurately reflect
   the method and scope of the passages (sample type, region, single vs
   multi-source), or does it overstate certainty?

CARD:
{card}

CHAINS:
{chains}

INFERRED LINKS FLAGGED BY EXTRACTOR:
{inferred}

Return ONE JSON object:
{{"mechanism_chain_fit": [{{"mechanism_index": 0, "verdict": "OK"|"CONCERN", "note": "..."}}],
  "identity_claim_violations": ["<quote the violating text, or empty list>"],
  "inferred_link_verdicts": [{{"link": "...", "verdict": "APPROVE"|"REJECT", "note": "..."}}],
  "confidence_honesty": {{"verdict": "OK"|"CONCERN", "note": "..."}},
  "overall_recommendation": "AUTO-APPROVED"|"NEEDS HUMAN REVIEW"|"REJECTED",
  "summary": "one or two sentences"}}"""


def validate_one(card_id: str, client, model) -> dict:
    ws_path = EXTRACTION_DIR / f"{card_id}.worksheet.md"
    card_path = EXTRACTION_DIR / f"{card_id}.card.json"
    if not ws_path.exists():
        return {"card_id": card_id, "error": f"no worksheet at {ws_path}"}

    parsed = parse_worksheet(ws_path)
    card = json.loads(card_path.read_text(encoding="utf-8")) if card_path.exists() else parsed["card"]
    if card is None:
        return {"card_id": card_id, "error": "could not locate card JSON"}

    corpus = load_source_corpus()

    # ── Deterministic layer ──────────────────────────────────────────────
    passage_flags = []
    for p in parsed["passages"]:
        fname, score = best_fuzzy_match(p["passage"], corpus)
        if score < FUZZY_MATCH_THRESHOLD:
            passage_flags.append({"id": p["id"], "passage": p["passage"][:150],
                                  "best_match": fname, "score": score})

    vocab_flags = []
    for term in card.get("vocabulary", []):
        if not any(normalize(term) in entry["text"]
                  for fname, entry in corpus.items() if not fname.startswith("_")):
            vocab_flags.append(term)

    vocab = closed_vocabulary([t for t in card.get("segment_tags", [])])
    lint_errs = lint_card(card, vocab)

    # ── LLM-judge layer ───────────────────────────────────────────────────
    judge_raw = chat_json(client, model, JUDGE_SYSTEM, JUDGE_PROMPT.format(
        card=json.dumps(card, indent=2, ensure_ascii=False),
        chains=json.dumps(parsed["chains"], indent=2, ensure_ascii=False),
        inferred=json.dumps(parsed["inferred_links"], indent=2, ensure_ascii=False),
    ))

    # ── Aggregate verdict ────────────────────────────────────────────────
    hard_fail = bool(lint_errs) or len(passage_flags) > max(2, len(parsed["passages"]) * 0.15)
    judge_concern = (
        judge_raw.get("overall_recommendation") != "AUTO-APPROVED"
        or any(m.get("verdict") == "CONCERN" for m in judge_raw.get("mechanism_chain_fit", []))
        or judge_raw.get("identity_claim_violations")
        or judge_raw.get("confidence_honesty", {}).get("verdict") == "CONCERN"
    )
    if hard_fail:
        verdict = "REJECTED"
    elif judge_concern or vocab_flags or passage_flags:
        verdict = "NEEDS HUMAN REVIEW"
    else:
        verdict = "AUTO-APPROVED"

    return {
        "card_id": card_id, "verdict": verdict,
        "lint_errs": lint_errs, "passage_flags": passage_flags,
        "vocab_flags": vocab_flags, "judge": judge_raw,
        "n_passages": len(parsed["passages"]),
    }


def write_report(result: dict):
    path = EXTRACTION_DIR / f"{result['card_id']}.validation_report.md"
    lines = [f"# Validation report: {result['card_id']}", "",
             f"**Verdict: {result['verdict']}**", "",
             "> Automated pre-screen, not a substitute for reading the source paper.",
             "> AUTO-APPROVED means nothing detectable was wrong, not that it is",
             "> definitely correct.", "", "## Deterministic checks", "",
             f"- Contamination lint: {'FAILED — ' + '; '.join(result['lint_errs']) if result['lint_errs'] else 'passed'}",
             f"- Passage faithfulness: {result['n_passages'] - len(result['passage_flags'])}/{result['n_passages']} "
             f"passages fuzzy-matched a source file (threshold {FUZZY_MATCH_THRESHOLD})"]
    if result["passage_flags"]:
        lines.append("  - **Flagged passages (best match too weak — check these first):**")
        for f in result["passage_flags"]:
            lines.append(f"    - {f['id']} (best match {f['best_match']!r}, score {f['score']}): {f['passage']}")
    if result["vocab_flags"]:
        lines.append(f"- Vocabulary NOT found verbatim in any source: {result['vocab_flags']}")
    else:
        lines.append("- Vocabulary: all terms found in source text")

    j = result["judge"]
    lines += ["", "## LLM second-opinion review", "",
              f"- Summary: {j.get('summary', '')}", "",
              "**Mechanism-chain fit:**"]
    for m in j.get("mechanism_chain_fit", []):
        lines.append(f"  - mechanism {m.get('mechanism_index')}: {m.get('verdict')} — {m.get('note', '')}")
    if j.get("identity_claim_violations"):
        lines.append(f"\n**Identity-claim violations flagged:** {j['identity_claim_violations']}")
    if j.get("inferred_link_verdicts"):
        lines.append("\n**Inferred-link verdicts:**")
        for link in j["inferred_link_verdicts"]:
            lines.append(f"  - {link.get('verdict')}: {link.get('link')} — {link.get('note', '')}")
    lines.append(f"\n**Confidence honesty:** {j.get('confidence_honesty', {})}")
    lines += ["", "## What you still need to do",
              "", "- [ ] Spot-check the flagged passages above against the actual paper"
                   if result["passage_flags"] else
                   "- [x] No passages flagged — spot-checking optional but recommended",
              "- [ ] Read the LLM judge's concerns (if any) and agree/disagree",
              "- Reviewer: ______  Date: ______  Final sign-off: YES / NO"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--card-id", help="validate a single card")
    ap.add_argument("--all", action="store_true", help="validate every worksheet in docs/extraction")
    ap.add_argument("--research-tier", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()

    if not args.card_id and not args.all:
        sys.exit("Pass --card-id <id> or --all")

    client, model = get_client(args.research_tier, args.model, args.base_url, args.api_key)

    if args.all:
        card_ids = sorted(p.stem.replace(".worksheet", "")
                          for p in EXTRACTION_DIR.glob("*.worksheet.md"))
    else:
        card_ids = [args.card_id]

    summary = []
    for cid in card_ids:
        print(f"Validating {cid}...")
        result = validate_one(cid, client, model)
        if "error" in result:
            print(f"  SKIP: {result['error']}")
            continue
        path = write_report(result)
        print(f"  {result['verdict']} -> {path}")
        summary.append((cid, result["verdict"]))

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    for cid, verdict in summary:
        print(f"  {verdict:20s} {cid}")
    approved = sum(1 for _, v in summary if v == "AUTO-APPROVED")
    review = sum(1 for _, v in summary if v == "NEEDS HUMAN REVIEW")
    rejected = sum(1 for _, v in summary if v == "REJECTED")
    print(f"\n{approved} auto-approved, {review} need human review, {rejected} rejected, "
          f"of {len(summary)} total.")
    if review or rejected:
        print("Only the flagged ones need your time — read their .validation_report.md files.")


if __name__ == "__main__":
    main()
