# Shipping the poster-vision feature to main

Upload a social poster, read it once into a text brief, put the brief in front of
a persona panel. The personas only ever see text.

Branch: `worktree-poster-vision-test`.

---

## 1. What a reviewer needs to know first

**One vision call per poster, never per persona.** A panel of 40 costs one image
read, not forty. The brief is cached on disk, so re-reading the same poster is
free.

**The vision model describes the poster and nothing else.** It does not name an
audience, invent a segment, or write persona text. Cast selection stays with the
curated library. The read prompt says this explicitly, and the same rule that
bans a "% who would buy" bans a "% who would click" — there is no score anywhere
in this feature.

**A third model tier.** The repo already split `LLM_*` (research, Plus tier) from
`SIM_LLM_*` (simulation runtime, cheap tier). Posters are neither, so they get
`VISION_*`. Without this split, pointing at a vision model would silently swap
the research model too.

**Everything is testable with the model switched off.** `StubPosterReader` needs
no key and no network. `POST /api/panel/posters?read=0` stores the image without
calling anything.

---

## 2. Environment variables

Add to `.env` in production. All three fall back to the `LLM_*` tier when blank,
so a deploy without them keeps working — the poster read just goes to whatever
`LLM_MODEL_NAME` is.

```
VISION_MODEL=qwen3-vl-235b-a22b-thinking
VISION_API_KEY=
VISION_BASE_URL=
VISION_PRICE_PROMPT_PER_1M=
VISION_PRICE_COMPLETION_PER_1M=
```

- `VISION_MODEL` — must be a model that accepts images. Verified on
  `qwen3-vl-235b-a22b-thinking` via DashScope. Takes 30 to 60 seconds per poster.
- `VISION_API_KEY` / `VISION_BASE_URL` — leave blank to reuse the research key and
  base URL. Set them only if the vision model lives at a different provider.
- `VISION_PRICE_*` — **set these or poster reads report $0.** There is no pricing
  entry for this model in `token_counter._DEFAULT_PRICING`, so cost reporting
  falls back to zero with a warning in the log.

`.env.example` already documents all five.

### Thinking must stay ON for this tier

`Config.llm_extra_body()` used to disable thinking for any model with "qwen" in
the name, which is right for persona texture and wrong for a reasoning vision
model. It now takes the model name and returns `{}` for any `-thinking` variant.
Sending `enable_thinking: false` to one of those either 400s or is ignored.

The signature gained an optional argument, so the four existing callers
(`agentsociety_opinion_block`, `deep_research_service`, `sa_context`) are
unchanged and still read `LLM_MODEL_NAME` from the environment.

---

## 3. Files changed

### Backend

| File | Change |
|---|---|
| `app/services/poster_service.py` | **New.** Save, read, cache. `PosterReader` protocol, `VisionPosterReader`, `StubPosterReader`, `POSTER_QUESTIONS`. |
| `app/api/panel.py` | **New routes** `POST /api/panel/posters`, `GET /api/panel/posters/<id>`. |
| `app/config.py` | `VISION_*` settings, `POSTER_DATA_DIR`, `llm_extra_body(model)`. |
| `app/utils/llm_client.py` | `LLMClient.for_vision()`, `LLMClient.image_message()`, `price_prefix`, empty-content guard. |
| `app/utils/token_counter.py` | Counts multimodal message lists, `price_prefix`, `IMAGE_TOKEN_ESTIMATE`. |
| `scripts/read_poster.py` | **New.** Command-line poster read, for checking the model without the app. |

### Frontend

| File | Change |
|---|---|
| `src/components/flow/FlowHome.vue` | Upload button in the prompt bar, loading card, attached-poster card, `composedPitch()`. |
| `src/api/panel.js` | `uploadPoster()`, `getPoster()`. |
| `src/views/PosterTestView.vue` | **New.** Standalone `/poster` page: image beside brief. |
| `src/router/index.js` | `/poster` route. |

### Two notable details

**`chat()` message typing loosened.** `List[Dict[str, str]]` became
`List[Dict[str, Any]]` because a multimodal message's `content` is a list of
parts, not a string.

**Token counting had to learn about images.** Encoding a 400 KB base64 data URL
through tiktoken counted it as ~400,000 tokens and was slow. Image parts now
count as a flat `IMAGE_TOKEN_ESTIMATE` (1024). Text parts count normally.
Measured: a real poster message counts 1033 tokens instead of 400,000.

---

## 4. Before merging

- [ ] **Delete the `## THIS WORKTREE` section from `CLAUDE.md`.** It documents the
      scratch branch and must not reach main. (Already done on this branch.)
- [ ] **Decide on `/poster`.** `PosterTestView.vue` shows the image beside the
      brief, which is useful for judging the read itself but duplicates what the
      home screen now does. Keep it as a debug page, or delete the view and its
      router entry. It is referenced, so it is not an orphan either way.
- [ ] **Do not ship `.env` or `frontend/.env.local`.** Both are gitignored. The
      `.env.local` file only exists to bypass local auth.
- [ ] Check `package-lock.json` — it was already modified before this work
      started, so confirm that change is wanted before it rides along.

---

## 5. Testing after deploy

### With the model off — no key needed

```python
from app.services import poster_service as ps

record = ps.save_poster(open("poster.png", "rb").read(), "image/png", "poster.png")
record = ps.read_poster(record["poster_id"], reader=ps.StubPosterReader())
assert record["brief"]
assert ps.read_poster(record["poster_id"])["brief"] == record["brief"]   # cached
```

Rejections to expect: `image/gif` raises `ValueError`, so does an empty upload,
so does anything over 8 MB.

### Store without calling the model

```
curl -X POST -F "image=@poster.png" "$HOST/api/panel/posters?read=0"
```

Returns `brief: null` plus the four poster questions.

### The real path

```
curl -X POST -F "image=@poster.png" "$HOST/api/panel/posters"
```

Expect a brief under six headings: `TEXT ON THE POSTER`, `WHAT IS PICTURED`,
`LAYOUT`, `CLAIMS`, `THE ASK`, `PRICE SHOWN`. Check two things:

1. The small print is transcribed. That is the hardest part of a poster and the
   main reason to use a reasoning vision model.
2. The brief does **not** name an audience. If it does, the read prompt has
   regressed and the no-LLM-personas rule is being broken.

### End to end

Upload on the home screen, confirm the prompt box stays **empty** (the brief goes
to the card below, not into the box), type a question, then "Assemble panel".
The pitch sent is the brief under `THE POSTER`, then the question under
`WHAT THE FOUNDER WANTS TO KNOW`.

---

## 6. Two things that will bite you locally, unrelated to this code

**The persona library is gitignored.** A fresh checkout or worktree has no
`backend/app/data/persona_library/personas.json`, so `POST /api/panel/sessions`
returns "Persona library is empty" and no personas appear. Rebuilding costs
Plus-tier LLM money (`backend/scripts/build_library.py`). Copy the built file
from a machine that has it instead.

**Model quota failures look like empty personas.** When the simulation tier runs
out of quota, a panel assembles fine and then every reaction comes back blank.
The real reason is in the response body under `failure_reason` — read it before
suspecting the code. The `all_failed: true` flag is the tell.

**The backend does not auto-reload.** `use_reloader=False` keeps LadybugDB's
single-process file lock intact. Restart it after any backend change, or you will
be testing old code.

---

## 7. Rolling back

The feature is additive. To disable it without reverting code, unset
`VISION_MODEL` so poster reads fall back to the research model, or hide the
upload button in `FlowHome.vue`. The routes are new, so nothing existing breaks
if they are never called. `POSTER_DATA_DIR` is a new directory under `DATA_ROOT`
and can be deleted safely.
