# How to actually learn in here

The curriculum says *what* to study. This says *how*, and what to optimise for.

---

## What is in this worktree

```
D:/Fub-learn/                 branch: learning
├── .venv/                    your own Python. Separate from the backend on purpose.
├── learn/
│   ├── README.md             setup, the read-only rule, how to start a session
│   ├── GUIDE.md              this file — how to study
│   ├── PROGRESS.md           your log. You write this one.
│   ├── paths.py              pointers to the real data over in main
│   ├── notebooks/            one per curriculum topic
│   │   └── 01_raw_data.ipynb
│   └── output/               anything you save. Gitignored.
└── (a full checkout of the app, so you can read and import the real code)
```

The last line is the point. This is not a sandbox with fake data. The production
`ghs_adapter.py`, `attitude_fuser.py`, and `eval_attitude_match.py` are sitting right
there, importable, next to your experiments.

---

## The one thing to optimise for

**Being able to say a number out loud without opening a file.**

Not finishing notebooks. Not understanding an explanation. Numbers you own.

A concrete example from notebook 01: *"1% of GHS households report an unspecified
income, and if that code leaked through it would inflate mean household income from
R11,700 to R113,000."* That sentence is worth more than a week of reading about data
cleaning, because you can defend it, and because you found it.

Everything below serves that.

---

## The session shape

Ninety minutes, one question, in this order. Do not reorder it.

1. **Guess (2 min).** Write the number you expect in `PROGRESS.md`. Before any code.
2. **Compute (40 min).** Get the real number out of the real data.
3. **Compare (5 min).** How wrong were you, and in which direction?
4. **Write (10 min).** One paragraph in `PROGRESS.md`, in plain words, as if telling a
   customer.
5. **Stop.**

Step 1 is the one people skip and it is the one that does the work. A number you
predicted wrong sticks; a number you merely read does not.

---

## Five rules

**One question per notebook, never one topic.** "How wide is the error bar on 30
personas" is a question. "Statistics" is not. If you cannot phrase it as a question
with a numeric answer, you are not ready to open the notebook.

**Always beat a dumb baseline.** Before any clever method, compute what "guess the
most common answer" scores. If clever does not beat dumb, clever is not earning its
place. Your own `eval_attitude_match.py` already enforces this — copy the discipline.

**Read the production code before writing your own.** Every topic in the curriculum
exists because your codebase already does a version of it. Read theirs, then write
yours, then diff. Disagreement is the lesson.

**Never fix main from here.** If you find a real bug, write it down in `PROGRESS.md`
and fix it in the main worktree in a normal branch. Mixing learning with shipping ruins
both.

**Ship one sentence per session.** Not code. A sentence you could say to a buyer. That
is the deliverable.

---

## How to tell it is working

| Real learning | Looks like learning |
|---|---|
| You predicted 5% and it was 40% | You read that missing data matters |
| You can state your panel's margin of error | You know confidence intervals exist |
| You found a column nobody validated | You ran every cell without errors |
| You changed a product decision | You finished the notebook |
| You explained it to someone non-technical | You understood the explanation |

The right-hand column is the trap, and it feels identical from the inside. The test
is whether you can produce the number cold, a week later.

---

## What to skip, deliberately

You are not becoming a research scientist. Skip these until something forces you back:

- Deep learning and neural network internals. Nothing in your product needs them.
- Big data tooling (Spark, warehouses). Your data fits in memory. All of it.
- Kaggle-style model competitions. Your problem is measurement, not prediction accuracy.
- MLOps and deployment pipelines. You already deploy fine.

Spend the saved time on survey methodology and uncertainty instead. That is where your
product's credibility actually lives, and it is the part almost no AI-startup founder
has.

---

## When you get stuck

Stuck for more than twenty minutes means the question was too big. Cut it in half.

"Is my panel representative" is too big. "Does my panel have the right share of
Gauteng residents" is one query and one comparison, and answering it teaches you most
of the big question anyway.
