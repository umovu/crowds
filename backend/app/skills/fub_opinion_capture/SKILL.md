---
name: fub_opinion_capture
description: Captures agent opinions on policy topics during simulation
user_invocable: false
---

# Fub Opinion Capture Skill

Collects and records how simulated agents (archetypes) respond to policy questions during a simulation run.

## When to Use

- During simulation execution to capture agent stances
- Post-simulation to interview agents about hypothetical scenarios
- Tracking opinion shifts across simulation rounds

## How It Works

1. Each simulation round, agents are prompted with policy-relevant questions
2. Agents respond based on their archetype, persona, and SA-context
3. Responses are recorded in the opinion database (SQLite)
4. Results feed into post-simulation analytics

## Archetype Anchoring

Each agent responds from the perspective of their archetype:
- Stance (support/oppose/neutral)
- Radicalism level (intensity of opinion)
- Group affiliation (which community they represent)
- Behavioral tendencies (how they typically act)

## Opinion Environment

Agents interact through a shared feed where they can:
- Post opinions
- Read others' posts
- Shift opinions based on social influence
- Express support or opposition to policy proposals