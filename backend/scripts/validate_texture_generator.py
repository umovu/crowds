"""
validate_texture_generator — prove texture is English-only and never overwrites bones.

Texture is the first LLM layer, so validation splits:

  * LLM-OFF (always runs): inject a fake client returning known texture (incl. a
    non-Latin word and an attempt to change the age). Assert the merge preserves
    every frozen demographic field verbatim and that non-Latin drift is stripped.
    This is the load-bearing guarantee — that the LLM cannot undo representativeness
    — and it is proven WITHOUT a model.

  * LLM-ON (only if --live and creds present): generate a few real personas, assert
    structure (all texture fields present, English-only, skeleton preserved), and
    print them to eyeball.

Run:  python backend/scripts/validate_texture_generator.py          # offline checks
      python backend/scripts/validate_texture_generator.py --live   # + real LLM batch
"""

from __future__ import annotations

import re
import sys

from persona_sampler import sample_skeletons
from archetype_mapper import map_skeletons
import texture_generator as tg

_NON_LATIN = re.compile(r"[^\x00-\x7f]")


class _FakeClient:
    """Stand-in LLMClient: returns fixed texture, including drift + a frozen-field
    overwrite attempt, so we can prove the merge defends the skeleton with no model."""
    def chat_json(self, messages, **kwargs):
        return {
            "name": "Lerato Mokoena",
            "persona": "A welder in Tembisa running a one-man workshop.",
            "background_story": "Worked formally until 2019, now self-employed. 中文漂移 leaked in.",
            "voice_guide": "Speaks plainly, talks money in rands, distrusts big retailers.",
            "behavioral_tendencies": "Speaks up about electricity costs and red tape.",
            "group_affiliation": "",
            "interested_topics": ["load-shedding", "small business costs", "crime"],
            # Hostile extras: try to overwrite frozen demographic facts.
            "age": 999,
            "province": "SHOULD-NOT-WIN",
            "actor_archetype": "violent_agitator",
        }


def offline_checks() -> bool:
    print("=== LLM-OFF checks (grounding preservation) ===")
    ok = True
    mapped = map_skeletons(sample_skeletons(50, seed=3), seed=3)
    fake = _FakeClient()

    for sk in mapped:
        persona = tg.generate_texture(sk, client=fake)

        # Frozen fields preserved verbatim — texture cannot overwrite the skeleton.
        for f in tg.FROZEN_FIELDS:
            if f in sk and persona.get(f) != sk.get(f):
                print(f"FAIL: frozen field '{f}' was overwritten "
                      f"({sk.get(f)!r} -> {persona.get(f)!r})")
                ok = False
                break

        # The hostile overwrite attempts must not have landed.
        if persona.get("age") == 999 or persona.get("province") == "SHOULD-NOT-WIN":
            print("FAIL: texture overwrote a demographic fact")
            ok = False
        if persona.get("actor_archetype") == "violent_agitator":
            print("FAIL: texture overwrote actor_archetype with an edge archetype")
            ok = False

        # Non-Latin drift stripped from the background_story.
        if _NON_LATIN.search(persona.get("background_story", "")):
            print(f"FAIL: non-Latin drift survived: {persona['background_story']!r}")
            ok = False

        # All texture fields present.
        missing = [f for f in tg.TEXTURE_FIELDS if f not in persona]
        if missing:
            print(f"FAIL: missing texture fields: {missing}")
            ok = False

    print("LLM-OFF:", "PASS" if ok else "FAIL")
    return ok


def live_checks() -> bool:
    print("\n=== LLM-ON checks (real generation) ===")
    try:
        client = tg.LLMClient()
    except Exception as e:
        print(f"SKIP live: no LLM client ({e})")
        return True

    mapped = map_skeletons(sample_skeletons(3, seed=11), seed=11)
    ok = True
    for sk in mapped:
        try:
            persona = tg.generate_texture(sk, client=client)
        except Exception as e:
            print(f"FAIL: live generation error: {e}")
            return False

        for f in tg.FROZEN_FIELDS:
            if f in sk and persona.get(f) != sk.get(f):
                print(f"FAIL: live run changed frozen field '{f}'")
                ok = False
        for field in ("name", "persona", "background_story", "voice_guide"):
            text = str(persona.get(field, ""))
            if _NON_LATIN.search(text):
                print(f"FAIL: non-English text in '{field}': {text!r}")
                ok = False
            if not text.strip():
                print(f"FAIL: empty '{field}'")
                ok = False

        import json
        print(json.dumps({k: persona.get(k) for k in
                          ["name", "age", "province", "occupation", "actor_archetype",
                           "persona", "voice_guide", "interested_topics"]},
                         ensure_ascii=False, indent=2))
        print("-" * 60)

    print("LLM-ON:", "PASS" if ok else "FAIL")
    return ok


def main() -> int:
    ok = offline_checks()
    if "--live" in sys.argv:
        ok = live_checks() and ok
    print("\n" + ("PASS — texture is English-only and preserves the skeleton."
                  if ok else "FAIL — see above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
