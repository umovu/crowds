<div align="center">

# Fub Sandbox

**Test your policies, announcements, and events on digital agents before they reach real people.**

*A multi-agent simulation engine that generates AI agents with unique personalities to simulate public reaction to your content — before it goes live.*

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)

</div>

## What is this?

Fub Sandbox lets you **stress-test ideas on virtual populations** before they reach real audiences.

Upload a policy draft, press release, or event brief — and watch how hundreds of AI agents with distinct personalities, opinions, and biases react. See how ideas spread, where resistance builds, and what the public mood looks like *before* you commit.

**Powered by the AgentSociety simulation engine with live web-research grounding.**

## Use Cases

- **Policy testing** — See how communities respond to regulations before drafting legislation
- **Crisis simulation** — Predict public reaction to announcements and communications
- **Event planning** — Test how audiences will receive conferences, launches, or campaigns
- **Stakeholder analysis** — Understand how different groups will interpret your message

## How It Works

1. **Build Graph** — Extract entities, relationships, and context from your document into a knowledge graph
2. **Create Agents** — Generate a population with diverse personalities, biases, and viewpoints
3. **Run Simulation** — Watch agents react, discuss, argue, and shift opinions on your topic
4. **Analyze Results** — Get structured insights on sentiment, influence patterns, and key viewpoints

## Quick Start

### Prerequisites

- Docker & Docker Compose, **or**
- Python 3.11+, Node.js 18+, Neo4j 5.15+, Ollama

### Option A: Docker

```bash
git clone https://github.com/umovu/fub-sandbox.git
cd fub-sandbox
cp .env.example .env

docker compose up -d

# Pull required models
docker exec fub-ollama ollama pull qwen2.5:32b
docker exec fub-ollama ollama pull nomic-embed-text
```

Open `http://localhost:3000`

### Option B: Manual

```bash
# Start Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/fubsimulation \
  neo4j:5.15-community

# Start Ollama & pull models
ollama serve &
ollama pull qwen2.5:32b
ollama pull nomic-embed-text

# Run backend
cd backend
pip install -r requirements.txt
python run.py

# Run frontend
cd frontend
npm install
npm run dev
```

## Architecture

Powered by **AgentSociety** simulation engine with live web-research grounding.

- **Neo4j** — Knowledge graph and memory storage
- **Ollama** — Local LLM inference (qwen2.5, llama3, etc.)
- **AgentSociety** — Agent-Block-Action simulation model
- **Web research** — Optional deep web research for persona enrichment

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 16 GB | 32 GB |
| VRAM (GPU) | 10 GB | 24 GB |
| Disk | 20 GB | 50 GB |

## License

AGPL-3.0 — see [LICENSE](./LICENSE).

## Credits

Powered by the AgentSociety simulation engine.

Forked from Mirofish Offline.
