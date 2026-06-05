<div align="center">

# Fub Sandbox

**Pressure-test your policies, announcements, product ideas, and events against a synthetic public — before they meet the real one.**

*Describe a scenario, generate a population of AI agents with distinct personalities, and run your content past them to map the range of plausible reactions.*

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)

</div>

## What is this?

Fub Sandbox generates a population of AI personas — each with its own background, biases, and viewpoint — then plays your policy draft, press release, product pitch, or event brief past them. You see **the range of reactions your content might provoke**: where resistance builds, how an idea gets read or misread, and which objections you hadn't considered.

It's built for **coverage, not prediction.** The agents are LLM-driven personas, not a statistically representative sample. Treat the output as a fast, broad rehearsal of the *kinds* of responses your content might draw — directional signal to prepare against, not a forecast of what real people will do. Used that way, it's genuinely useful. Read as a poll, it will mislead you.

What makes it a *sandbox* rather than a passive demo: you can **intervene** — pause a running simulation, pose a follow-up ("we'll add a subsidy"), and watch stances shift — and you can **bring your own people** by injecting custom agents that model the specific stakeholders or groups you care about.

## What you can do with it

- **Red-team a policy** — surface likely objections, blind spots, and ways a rule gets gamed, before you commit
- **Test framing** — see how different groups might read or misread your wording
- **Rehearse crisis comms** — pressure-test an announcement and the reactions you'd need to handle
- **Stress-test product ideas** — see how a South African market might react to your product pitch, including objections, confusion, and qualitative willingness (not purchase predictions)
- **Intervene mid-run** — pause a live simulation, pose a follow-up, and watch how opinions move
- **Probe after the fact** — read each agent's expressed opinion post-run, then pose interventions and see how they respond
- **Bring your own people** — inject custom agents (named stakeholders, specific groups), merged into the population or run on their own

## How It Works

1. **Seed** — give it a document or a described scenario; it extracts entities, relationships, and context into a knowledge graph
2. **Populate** — it generates a population of agents (configurable in size) with diverse personalities, biases, and viewpoints, grounded in real socio-economic context
3. **Run** — agents post, argue, respond, and shift opinion across rounds; pause and intervene at any point. Choose between policy mode (citizens reacting to announcements) or product mode (market reacting to product ideas).
4. **Analyse** — the Analytics dashboard breaks down sentiment over time, who participated (and who stayed silent), what topics spread, each agent's opinions, and side-by-side scenario comparisons

## Scope & Limitations

Read this before you rely on the output.

- **Personas, not people.** Grounding makes agents plausible, not accurate. There is no claim of statistical representativeness.
- **Coverage, not prediction.** A broad survey of *possible* reactions — not a forecast or a poll.
- **Quality depends on your seed.** Vague input produces generic agents. The richer and more specific the scenario, the more useful the run.
- **Population size is configurable** and trades off against cost and runtime — larger runs mean more LLM calls. Smaller populations show limited opinion propagation, so don't over-read network effects at low agent counts.
- **Regional grounding is configurable.** It ships with a default context that you can change to fit your setting.
- **Web grounding is optional** and off by default — it makes personas more current but needs third-party API keys (see below).

## Quick Start

You can run the full stack with Docker (provisions Neo4j + Ollama for a self-contained local deployment), or run it lighter against a hosted LLM with the embedded graph database.

### Prerequisites

- Docker & Docker Compose, **or**
- Python 3.11+ and Node.js 18+ (plus an LLM endpoint — hosted or local)

### Option A: Docker (self-contained, local models)

```bash
git clone https://github.com/umovu/fub-sandbox.git
cd fub-sandbox
cp .env.example .env

docker compose up -d

# Pull the local models used by the Docker stack
docker exec fub-ollama ollama pull qwen2.5:32b
docker exec fub-ollama ollama pull nomic-embed-text
```

Open `http://localhost:3000`

### Option B: Manual (embedded graph + your own LLM)

The lightest path: the embedded **LadybugDB** graph backend (no Docker, no Neo4j) and any OpenAI-compatible LLM endpoint — hosted (e.g. Qwen/DashScope, Groq) or local (Ollama).

```bash
git clone https://github.com/umovu/fub-sandbox.git
cd fub-sandbox
cp .env.example .env
# Edit .env: set GRAPH_BACKEND=ladybug and your LLM_* endpoint/key

# Run backend
cd backend
pip install -r requirements.txt
python run.py

# Run frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

### LLM configuration

The pipeline splits LLM usage into two tiers, configured independently in `.env`:

- `LLM_*` — research, persona generation, and document parsing (lower volume, benefits from a stronger model)
- `SIM_LLM_*` — the simulation runtime (high volume; a cheaper/faster model is the right tool). Leave these blank to reuse the research key.

Any OpenAI-compatible endpoint works. **Optional web grounding** (richer, more current personas) is enabled per-run and uses `JINA_API_KEY` / `SERPER_API_KEY` / `FIRECRAWL_API_KEY` if set.

## Architecture

- **Simulation engine** — AgentSociety (Agent–Block–Action model)
- **Graph / memory** — LadybugDB by default (embedded, no Docker); Neo4j and an in-memory backend are also supported
- **LLM** — any OpenAI-compatible endpoint; split into research and simulation tiers
- **Web research (optional)** — Jina / Serper / Firecrawl for grounding personas in live sources

## Hardware Requirements

Applies to the **Docker** option (local Neo4j + Ollama inference). Running against a hosted LLM with the embedded graph needs far less.

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 16 GB | 32 GB |
| VRAM (GPU) | 10 GB | 24 GB |
| Disk | 20 GB | 50 GB |

## License

AGPL-3.0 — see [LICENSE](./LICENSE).

## Credits

Built on the AgentSociety simulation engine. Forked from MiroFish-Offline.
