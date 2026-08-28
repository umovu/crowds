# learn/ — the learning worktree

A separate checkout of this repo, on branch `learning`, for working through the
data science curriculum against the real data. Nothing here ships.

## Where you are

| | |
|---|---|
| This worktree | `D:/Fub-learn` (branch `learning`) |
| Main working copy | `D:/Fub-agentsociety` (branch `operator-context`) |
| Python | `D:/Fub-learn/.venv/Scripts/python.exe` |

Two separate virtual environments on purpose. Installing a package here can
never break the backend that runs the product.

## The rule

**This worktree reads from main. It never writes to main.**

The survey microdata and the persona library are gitignored, so they don't exist
in this checkout. `learn/paths.py` points at the copies in `D:/Fub-agentsociety`
and opens them read-only. Anything you produce goes in `learn/output/`.

## Start a session

```
D:/Fub-learn/.venv/Scripts/python.exe -m jupyter lab
```

Then open `learn/notebooks/`. In any notebook, first cell:

```python
import sys; sys.path.insert(0, "D:/Fub-learn/learn")
import paths; paths.check()
```

## Importing the production code

You can import the real scripts and compare your work against them:

```python
import sys, paths
sys.path.insert(0, str(paths.SCRIPTS))
import attitude_donor_adapter as ada   # the real one, from main
```

This is the whole point of the worktree: your experiments sit next to the
production implementation, not in place of it.

## Read these two first

- `GUIDE.md` — how to run a study session, and what to optimise for.
- `PROGRESS.md` — your log and scoreboard. The real output of all this.

## The curriculum

`D:/Fub-agentsociety/local-plans/learn/curriculum.html` — seven topics, each
tied to a claim the codebase makes. One notebook per topic:

| # | Notebook | Topic |
|---|---|---|
| 01 | `01_raw_data.ipynb` | Reading the microdata, finding sentinel values |
| 02 | `02_uncertainty.ipynb` | Confidence intervals on a 30-person panel |
| 03 | `03_weighting.ipynb` | Is the panel the right mix of South Africans? |
| 04 | `04_baseline_model.ipynb` | How predictable is an attitude, really? |
| 05 | `05_neighbours.ipynb` | Your donor ladder vs. a real KNN |
| 06 | `06_clustering.ipynb` | Are your segments real groups? |
| 07 | `07_text.ipynb` | Scoring the objection classifier |

## Committing

Work on `learning` freely. Commit whatever you want here — it is a scratch
branch and is never merged into `main`. Nothing in `learn/` is imported by the
product.

## Cleaning up

```
git worktree remove D:/Fub-learn
git branch -D learning
```
