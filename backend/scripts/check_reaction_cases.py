"""
check_reaction_cases — score the objection reader against a hand-written answer sheet.

The question this answers: **for a named library persona, does what they said get
read as the right walls — and does their measured record stop the ones they are not
entitled to?** Each case in tests/data/reaction_cases.json names a real persona, a
pitch, the reaction text, the walls that must survive and the walls that must not.

Shapes the rules around a reaction, never the persona: the sheet asserts on
`objections.read`, the vocab and the grounds table. It never writes identity.

Two readers can be scored against the same sheet:

  word    `objections.read` — substring cues plus the mood rule. The default.
          LLM-free: runs on the real library with the typed reader off, so a
          failure is a rule to fix, not a model that drifted.
  typed   `objections.read_walls_typed` — one yes/no question per wall, built from
          that wall's own `definition` block. Needs TYPESAFE_API_KEY and costs a
          few cents; only runs when you ask for it with `--typed`.

Whichever reader answers, the GROUNDS RULE is applied afterwards exactly as
`objections._read_all` applies it in production: the reader says what was said,
the person's measured record says who may say it. So the two columns differ only
in the reading, never in the entitlement.

Run:  python scripts/check_reaction_cases.py            # word reader only
      python scripts/check_reaction_cases.py --typed    # both, side by side
"""

import argparse
import json
import os
import sys

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-placeholder")

BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND)

CASES = os.path.join(BACKEND, "tests", "data", "reaction_cases.json")


def _persona(name):
    """The library record for a named persona, or None if the library dropped them."""
    from app.services.persona_library import get_library

    for person in get_library().all():
        if person.get("name") == name:
            return person
    return None


def load_cases():
    with open(CASES, encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def _grounded(walls, facts):
    """The walls this person's own record lets them keep."""
    from app.services import objections

    return [w for w in walls if objections.has_grounds(w, facts) is not False]


def _problems(case, said, read):
    """What is wrong with one case, given what a reader saw (`said`) and what
    survived the grounds rule (`read`). Empty means it passes."""
    problems = []
    for wall in case.get("want", []):
        if wall in read:
            continue
        if wall in said:
            problems.append(f"{wall} was said but the grounds rule dropped it")
        else:
            problems.append(f"{wall} never read from the reaction")
    for wall in case.get("avoid", []):
        if wall in read:
            why = ("the grounds rule let it through" if wall in said
                   else "the reader invented it")
            problems.append(f"{wall} survived — {why}")
    return problems


def case_problems(case):
    """What the word reader gets wrong on one case. Empty means it passes."""
    from app.services import objections

    person = _persona(case["persona"])
    if person is None:
        return [f"no persona named {case['persona']} in the library"]

    facts = objections.persona_facts(person)
    return _problems(case,
                     said=objections.read(case["reaction"])["walls"],
                     read=objections.read(case["reaction"], facts)["walls"])


def typed_problems(cases):
    """What the typed reader gets wrong, per case, in `cases` order.

    One list of problems per case, or None for the whole run when the tier is
    unavailable. Every reaction goes in one batched pass.
    """
    from app.services import objections

    os.environ["FUB_TYPED_WALLS"] = "1"
    if not objections.typed_reading_enabled():
        return None

    seen = objections.read_walls_typed([c["reaction"] for c in cases])
    if seen is None:
        return None

    out = []
    for case, said in zip(cases, seen):
        person = _persona(case["persona"])
        if person is None:
            out.append([f"no persona named {case['persona']} in the library"])
        elif said is None:
            out.append(["the typed reader did not answer for this reaction"])
        else:
            facts = objections.persona_facts(person)
            out.append(_problems(case, said=said, read=_grounded(said, facts)))
    return out


def score(verbose=False):
    """(cases passed, cases total) for the word reader, LLM-free.

    tests/test_reaction_cases.py guards the number.
    """
    cases = load_cases()
    passed = 0
    for case in cases:
        problems = case_problems(case)
        passed += not problems
        if verbose:
            print(f"{'PASS' if not problems else 'FAIL'}  {case['id']}")
            for line in problems:
                print(f"        {line}")
    return passed, len(cases)


def compare():
    """Print both readers against the same sheet. Returns (word, typed, total),
    with `typed` None when the typed tier is unavailable."""
    cases = load_cases()
    word = [case_problems(c) for c in cases]
    typed = typed_problems(cases)

    if typed is None:
        print("Typed reader unavailable (no TYPESAFE_API_KEY, or the call failed).\n")

    def mark(problems):
        return "PASS" if not problems else "FAIL"

    width = max(len(c["id"]) for c in cases)
    header = f"{'case'.ljust(width)}  word  typed" if typed else f"{'case'.ljust(width)}  word"
    print(header)
    print("-" * len(header))
    for i, case in enumerate(cases):
        row = f"{case['id'].ljust(width)}  {mark(word[i])}"
        if typed:
            row += f"  {mark(typed[i])}"
        print(row)
        # Only explain a reader that got it wrong, and say which one.
        for line in word[i]:
            print(f"    word   {line}")
        for line in (typed[i] if typed else []):
            print(f"    typed  {line}")

    total = len(cases)
    good_word = sum(1 for p in word if not p)
    print(f"\nword  {good_word}/{total}")
    good_typed = None
    if typed:
        good_typed = sum(1 for p in typed if not p)
        print(f"typed {good_typed}/{total}")
        moved_up = [c["id"] for c, w, t in zip(cases, word, typed) if w and not t]
        moved_down = [c["id"] for c, w, t in zip(cases, word, typed) if not w and t]
        print(f"\ntyped fixes {len(moved_up)}, typed breaks {len(moved_down)}")
        for cid in moved_down:
            print(f"  broke: {cid}")
    return good_word, good_typed, total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--typed", action="store_true",
                    help="also score the typed reader (needs TYPESAFE_API_KEY, costs a few cents)")
    args = ap.parse_args()

    if args.typed:
        good, good_typed, total = compare()
        sys.exit(0 if good == total else 1)

    good, total = score(verbose=True)
    print(f"\n{good}/{total} cases pass")
    sys.exit(0 if good == total else 1)
