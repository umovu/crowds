# From paper to persona reasoning — the qualitative pipeline

This explains how a research paper ends up shaping what a persona says when a
user asks a question.

There are two halves.

- **Offline half.** Slow. A human is involved. A paper becomes a "mechanism
  card". This happens once, long before anyone runs anything.
- **Runtime half.** Fast. No AI involved until the very last step. A question
  comes in, people are picked, cards are handed out, an answer comes back.

The two halves meet at one small step: we check whether a card's tags match a
persona's tags. That's the whole join. No search, no AI matching.

```
PAPER ──offline extraction (7 stages)──▶ MECHANISM CARD ──┐
                                                          │  tag match
USER QUERY ──▶ MODE ──▶ CAST ──▶ PERSONA PROFILE ─────────┴──▶ PROMPT ──▶ ANSWER
                                  (survey-born identity)      (5 layers)
```

---

## Part A — Offline: turning a paper into a card

A research paper is about 8,000 words wrapped around maybe five useful
sentences. The job is to find those sentences and write them in a form a
persona can actually use later.

Full detail lives in `docs/EXTRACTION_PROTOCOL.md`. One worksheet per card.
About one day per paper.

### The seven stages, in plain terms

**Stage 0 — Screen it.** Does the paper explain *why* people act the way they
do? We need quotes or the author explaining reasons. If the paper only reports
numbers ("62% of households own livestock"), we reject it here. Those numbers
go somewhere else, into the stats file.

**Stage 1 — Harvest.** Read the findings and discussion sections. Copy out
every bit where the paper explains a reason. Number each one: P1, P2, P3. Write
down the page. Note whether it was a real participant talking, or the author
interpreting. Author-only reasoning gets a lower confidence score later.

**Stage 2 — Chain.** Take related bits and force them into one chain:

> their situation → so they judge things this way → so they behave this way →
> so a new product or policy reads like this to them

Every link in the chain must point back to the passage numbers it came from.
A link with no passage behind it gets flagged and usually deleted. Limit of
five chains per paper. If you have more, you're pulling out findings, not
reasoning, so merge or cut.

**Stage 3 — Scope it.** Say exactly who this applies to, by filling in one
sentence:

> For [this segment], in [this context], [this chain] happens, producing
> [this pattern].

Three rules here:

- The tags come from a fixed list. No making up new words.
- You also write down who this does **not** apply to. So cattle-as-savings
  applies to a communal farmer, but not to an emerging commercial farmer. This
  keeps us honest at writing time, not later.
- You record the money situation of the people the paper studied, using only
  three buckets: tight, moderate, loose. Township, communal, grant-dependent
  and no-fee-school samples map to tight/moderate. Middle-class or private
  school samples map to moderate/loose. If the paper never says, you leave the
  field out. An honest blank beats a guess.

**Stage 4 — Write the card.** Squash each chain into one sentence that keeps
the word "because". Then apply the hard test:

> Could a persona use this rule on a situation the paper never talked about?

"Cattle are important" fails and dies here. It's a description. "Cattle work
as savings and insurance, so selling is a last resort rather than routine
income" passes. It's a rule you can carry to a new situation.

You also add the words people actually used, the questions they actually ask,
and the rules they use to judge things. Then you check whether the card covers
can-they, will-circumstances-let-them, and do-they-want-to. If one is missing
you write down that it's missing. You never fill the gap by inventing.

**Stage 5 — Gate.** A human runs a checklist. All boxes must pass:

- No number carried out of the paper.
- No claims about who a persona *is*.
- All tags from the fixed list.
- Money tags match the paper's actual sample, or are left out.
- Every word in the vocabulary list actually appears in the paper.
- Every mechanism traces back to passage numbers.

Confidence is graded per sentence, not per paper. Only then does the card ship.

**Stage 6 — Prove it works.** Run matching personas three ways: with no card,
with the card, with card plus stats. Use a situation the paper never discussed.
Repeat it, because one run is just noise. Four levels of proof:

| Test | What you look for | What it means |
|---|---|---|
| Straw-in-the-wind | The card's words show up | Weak. Flavour only. |
| Hoop | The reasoning shows up with the card, and rarely without it | The card changed behaviour |
| Smoking gun | The reasoning gets applied to the new situation | The card caused it |
| Doubly decisive | Both of the above, repeatedly | Ship it |

A card that only passes the first test still ships, but flagged as
"citations only, no behaviour claim". A card that fails the hoop test goes back
to Stage 4, because the sentence was almost certainly written as a finding.

### Two rules that do most of the work

**1. Keep the "because."** A finding tells you what is true. A mechanism tells
you why, so it can travel to a new situation. Only the second kind is useful.

**2. Feelings only as "if this, then that."** A paper might document shame
around debt, or nihilism among unemployed youth. You may write "losing work
repeatedly erodes belief that effort pays". You may not write "these people are
hopeless". The first describes a response to circumstances. The second invents
a personality, and papers are never allowed to do that.

If a paper reveals an *attitude* rather than a reason, it does not go in the
card at all. It becomes a candidate new question in the survey vocabulary, so
the actual value comes from real survey respondents, person by person.

### What a card looks like

Three separate parts: the words, the tags, and the paper trail.

```json
{
  "id": "stokvels-calibration",
  "citation": ["Matuku & Kaseke (2014), Social Work/Maatskaplike Werk"],
  "segment_tags": ["grant_dependent_survivor", "guardian_parent", "..."],
  "economic_tags": ["tight", "moderate"],
  "mechanisms": ["A stokvel works because it separates grocery money from other claims on irregular income..."],
  "mechanism_provenance": [{"mechanism_index": 0, "chain_id": "C1", "passages": ["P1","P2"]}],
  "vocabulary": ["..."],
  "objection_patterns": ["..."],
  "claim_type": "qualitative",
  "confidence": "..."
}
```

- `mechanisms` is the payload. Plain sentences. Never scored, never counted.
- `segment_tags` and `economic_tags` are the index. This is the only part the
  running system looks at.
- `mechanism_provenance` is the paper trail back to numbered passages.

Cards live in [backend/app/data/mechanism_cards/](../backend/app/data/mechanism_cards/).
Fifteen so far. One card per idea, not per paper. Three stock-theft studies
become one card with three citations.

---

## Part B — Runtime: from a question to an answer

### Step 1 — The question arrives

The user writes a scenario or a pitch. The system works out the mode from the
text itself: policy or product. Product mode turns on the money lens. Policy
mode ignores money tags.

### Step 2 — Pick the room

`persona_retrieval.select_for_query` decides who is in the room. No AI here.

- Seats are handed out in proportion to the real population mix.
- Relevant people get more seats, but capped at about 3x their normal share.
- At least four different kinds of people must appear.

That cap and that floor exist to stop the echo chamber. A taxi question should
not produce a room of only taxi operators. You need the sceptic and the
uninterested person too.

In product mode the pool is narrowed by money bucket *before* picking, using
the exact same calculation that later gets stamped on the profile. So the
filter and the stamp can never disagree.

People come from the curated library first, custom agents second. Never written
by an AI. There is a guard that fails loudly if that is ever broken.

### Step 3 — Hand out the cards

This is the join. Still no AI. It runs from
[simulation_manager.py:496](../backend/app/services/simulation_manager.py#L496)
and [panel_service.py:573](../backend/app/services/panel_service.py#L573).

Four filters, in order:

1. **Does the tag match?** The card must name this persona's archetype. No
   match means no card. We never hand over the closest-ish card instead.
2. **Does the money bucket match?** In product mode, the persona's computed
   bucket must be in the card's list. A card with no money tags goes to
   everyone. Policy runs skip this step.
3. **Does the setting match?** A farming card only reaches someone who farms or
   lives rurally. This exists because a broad tag like "grant dependent" covers
   both a township grant recipient and a rural subsistence grower. Before this
   guard we measured 57 wrong matches, including a KwaMashu grant recipient
   being handed "price taker, market surplus" reasoning.
4. **Rank and cap.** Cards naming fewer groups sort first, because a paper that
   named one group knew it better. Ties break on the card's name so the result
   is always identical. Maximum two cards per persona. Broad groups could
   otherwise pull five cards, about 25 sentences, into thousands of calls.

Result: two fields get attached to the persona. The rendered text block, and
the citation list for the UI. **If nothing matches, no fields are added at
all.** The missing field is the honest answer.

Off switch: `RESEARCH_CONTEXT_ENABLED=0`.

### Step 4 — Build the prompt

The text block opens by saying "reason through this, do not quote it". Then the
sentences, grouped by paper. Then the vocabulary. Then two guardrails:

- **Your own outlook wins.** Where the card disagrees with what this person
  actually told a survey, the person's own view prevails. Real data about *this*
  person beats documented patterns about people *like* this person.
- **Do not invent features.** If a card mentions something the scenario never
  described, like public rankings, the persona must raise it as a question or a
  condition, never assume it's there.

The block sits at layer 3c of five:

| Layer | What it is | Where it comes from |
|---|---|---|
| 1–2 | Who they are, what they said before | Survey microdata |
| 3 | What's at stake for them | The scenario |
| 3b | Money reality (product runs) | Computed from real income. Fixed. |
| **3c** | **Research context** | **Mechanism cards. Words only.** |
| 4 | The question, reframed | Scenario and mode |
| 5 | Output rules | Fixed |

3b and 3c sit next to each other on purpose, and stay separate on purpose. The
numbers say where the person stands financially. The research says how people
standing there tend to decide. Wanting and affording never merge into one
number.

### Step 5 — The persona answers

The model writes in the persona's voice, reasoning through the sentences it was
given. It never writes a new one. It never sets a money bucket. It never
decides who the person is. What comes back is words: objections, conditions,
what they'd need before saying yes.

The citation list travels with the run, so the UI can show which papers stood
behind which person.

---

## Who wins when sources disagree

Inside one persona, this is the order:

1. **Numbers computed from real data.** Income, fees, money bucket. Never
   overridable. Never written by a model.
2. **This person's own measured attitudes**, matched from real survey
   respondents. Beats group patterns.
3. **Mechanism cards.** How people in this situation tend to reason.
4. **The model.** Voice and phrasing only.

---

## The rules that never bend

- Papers give reasoning and words. Never numbers. Never identity.
- Handing out cards is a plain tag lookup, provable with the model switched off
  (`backend/tests/test_mechanism_cards.py`, `test_card_binding_geotype.py`).
- Extraction happens offline, with a human gate. We chose this over searching
  papers live, because live search means paying every run, no review step, and
  bad extractions quietly poisoning results. Thirty checked cards beat three
  hundred scraped papers.
- Coverage is never faked. A group with no card gets nothing.
- Words stay words. You can count the tags. You never turn the sentence into a
  score.

## Known gaps

- No card yet for `institutional_loyalist` or `community_leader`.
- No coverage for the top-end professional segment. Those personas don't exist
  yet.
- Live paper search is designed but not built. When it lands it will propose
  new cards into a review queue, never straight into a running sim. Stages 1 to
  4 become the AI's instructions word for word. Stage 5 stays human. Stage 6
  stays scripted.
