"""belief_relevance: the beliefs a persona brings must follow the QUESTION, not the
order they happen to sit in.

Loaded by path, not as `app.services.belief_relevance`: importing the package runs
app/services/__init__.py, which pulls AgentSociety2 and dies without an API key. These
assertions are the point of the module being deterministic, so they must run with no
model and no key.
"""

import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "belief_relevance_test_target",
    os.path.join(_HERE, "..", "app", "services", "belief_relevance.py"))
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)


# The real sentences the phrasing table writes, in the order a fused persona stores them
# (ATTITUDE_VOCAB order). The grievance dimensions genuinely come first — that ordering is
# what made a positional cap a valence filter.
GOV = "Government and officials mostly don't act in people like me's interest."
ECON = "The economy is bad and my own prospects are poor right now."
SERVICE = "Basic services in my area are failing and complaints go nowhere."
CLINIC = "Public health services fail people like me — you can't count on a clinic."
PAYS = "I'll pay more if the service is genuinely better."
TRUSTS = "I generally give people the benefit of the doubt."

STORED = [GOV, ECON, SERVICE, CLINIC, PAYS, TRUSTS]

CLINIC_Q = "Would you use a small paid clinic near your home instead of the free hospital?"


def test_the_phrasing_table_is_reachable():
    """Without it every belief is unmapped and selection degrades to plain order."""
    assert br.dimension_of(PAYS) == ("pays_for_quality", "yes")
    assert br.dimension_of(GOV) == ("gov_trust", "low")


def test_question_subject_matter_drives_selection():
    dims = br.relevant_dimensions(CLINIC_Q)
    assert "health_service_satisfaction" in dims
    assert "pays_for_quality" in dims          # "paid" / "free" are price words
    assert "economic_optimism" not in dims


def test_relevant_beliefs_beat_earlier_irrelevant_ones():
    """The regression this module exists for: `beliefs[:3]` returned gov/econ/service for
    every persona and every question, so the belief most load-bearing in a product
    panel — willingness to pay — reached the prompt for none of them."""
    chosen = br.select(STORED, CLINIC_Q, 3)
    assert PAYS in chosen
    assert CLINIC in chosen
    assert ECON not in chosen                  # earlier in the list, unrelated to the ask
    assert chosen != STORED[:3]


def test_a_different_question_moves_a_different_belief_forward():
    chosen = br.select(STORED, "Would your neighbours recommend this to each other?", 2)
    assert TRUSTS in chosen


def test_unmapped_prose_is_never_dropped():
    """Hand-written beliefs on a custom agent aren't in the phrasing table. Nothing here
    may silently discard a sentence a human wrote."""
    custom = "I have run this spaza shop for eleven years."
    chosen = br.select([GOV, ECON, SERVICE, custom], CLINIC_Q, 2)
    assert custom in chosen


def test_unmatched_fill_is_not_all_grievance():
    """A question matching nothing must not hand back the three grievance dimensions by
    position — that is the old bug wearing a different hat."""
    chosen = br.select(STORED, "What is your favourite colour?", 3)
    assert any(b in chosen for b in (PAYS, TRUSTS))


def test_under_the_cap_everything_is_kept():
    assert br.select(STORED[:2], CLINIC_Q, 8) == STORED[:2]


def test_selection_is_deterministic():
    assert br.select(STORED, CLINIC_Q, 3) == br.select(STORED, CLINIC_Q, 3)


def test_empty_inputs_are_safe():
    assert br.select([], CLINIC_Q, 3) == []
    assert br.select(STORED, "", 0) == []
