"""cache_typed_tilt — one typed call per answer-sheet pitch, saved to disk.

Separated from scoring so threshold tuning costs nothing: fetch once, then
sweep offline against `scripts/out/typed_tilt_answers.json`.
"""
import json
import os
import sys

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")
BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

_ENV = os.path.join(BACKEND, "..", ".env")
if os.path.exists(_ENV):
    for line in open(_ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("TYPESAFE_") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

OUT = os.path.join(BACKEND, "scripts", "out", "typed_tilt_answers.json")


def main():
    from app.services.persona_retrieval import (_PROVINCES, _RELEVANCE_LEVELS,
                                                _archetype_descriptions, get_library)
    from app.utils import typesafe_client as ts
    from check_cast_cases import CASES

    descriptions = _archetype_descriptions(get_library().all())
    questions = {
        arch: ts.score_question(
            f"How much does this announcement or product land on this group of "
            f"South Africans: {desc}", _RELEVANCE_LEVELS)
        for arch, desc in descriptions.items()
    }
    questions["_province"] = ts.choice_question(
        "Which South African province does this name or clearly point at?",
        {p: None for p in _PROVINCES} | {"not_stated": "No province is named or implied"})

    cases = json.load(open(CASES, encoding="utf-8"))["cases"]
    out = {}
    for case in cases:
        answers = ts.ask(case["pitch"], questions)
        if answers is None:
            print("FAILED", case["id"])
            continue
        out[case["id"]] = answers
        print("ok", case["id"])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nwrote {len(out)} case(s) -> {OUT}")


if __name__ == "__main__":
    main()
