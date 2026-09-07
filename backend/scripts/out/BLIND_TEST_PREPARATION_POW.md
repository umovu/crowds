# Free preparation after the education repair

## Outcome

Synchronized deterministic survey belief sentences for 86 of 375 local personas with their current measured attitudes. There are no remaining mismatches among those recognized template sentences. All other fields are identical, including identities, income, background prose, attitudes and source records. A byte-for-byte private backup was saved beside the library as `personas.backup-pre-belief-sync.json`. No private persona records belong in the commit.

The repair preserves custom beliefs and does not claim to validate free-form narrative prose. No new identity or model-written text was generated. Live services and deployed copies have not been refreshed or verified.

## Code and checks

- `backend/scripts/sync_measured_beliefs.py`: explicitly applied maintenance operation; preserves custom text, validates duplicate topics, refuses backup/report overwrite, checks all other fields, and is idempotent.
- `backend/scripts/backtest_panel.py`: parses complete final answer labels, including spaces and apostrophes. Rejects prefixes, multiple answer lines and trailing explanations. Adds `--phase prepare --n 40`, which checks the frozen truth-free question file and counts local records without creating a client or reading R10 outcomes.
- `backend/tests/test_blind_preparation.py`: full labels, invalid replies, belief preservation, neutral beliefs, repeated repair, changed question rejection, preparation without a truth file or client.
- Existing crosswalk, frozen questions, education repair and realism tests pass alongside the new tests: **48 passed**.

## Evidence

- [Actual terminal output](blind_preparation_terminal.txt)
- [Belief repair hashes and counts](belief_sync_results.json)
- [Free readiness inventory](r10_preparation_inventory.json)

All pre-existing evidence files, the locked method and frozen question files retain their previous byte hashes. Model calls: **0**. Provider charges from this work: **0**.

## What paid means

The model provider charges for text sent to and returned by its API. Local data repair, report generation and offline tests do not send requests to that provider. The planned trial asks 40 personas all 15 frozen questions: 12 held-out questions plus 3 controls, or 600 planned requests. The whole 375-person library would require 5,625 planned requests. Retries could increase those counts. A currency estimate requires the selected SIM model, its current prices and measured input/output token use; no cost figure is invented here.

## Remaining work before paid testing

This is a completed free repair and readiness inventory, not completion of Item 5. The runner still needs separate blind ask/reveal phases, national weighting, subgroup gap reporting and provider token accounting. Narrative text needs a consistency review, and the running service must be shown to load the repaired data. Obtain an approved spending limit before any real model calls. Preserve the frozen questions and report unsuccessful or missing answers honestly.
