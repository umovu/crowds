---
name: fub_web_research
description: Multi-step web research using deep-research (Firecrawl + Jina + LLM)
user_invocable: true
---

# Fub Web Research Skill

Perform deep, multi-step web research using deep-research (Firecrawl + Jina + LLM).
Searches Google, reads webpages, and synthesizes findings — useful for grounding
simulations in current events and real-world context.

## When to Use

- Researching current news and events relevant to a simulation topic
- Finding stakeholder positions and recent policy developments
- Enriching agent personas with real-world context
- Complementing academic literature with web sources

## How to Use

1. Provide a research query (e.g., "current minimum wage debate South Africa 2026")
2. Deep research autonomously:
   - Searches Google for relevant results
   - Reads and extracts content from top articles
   - Searches for additional context as needed
   - Synthesizes findings into a structured summary
3. Review the research summary with sources
4. Optionally, use findings to enrich simulation agents

## Requirements

- API keys configured: Firecrawl, Jina, Serper, LLM
- Set `FIRECRAWL_API_KEY` and `JINA_API_KEY` in configuration

## Output

Returns structured research findings with:
- Key findings summary
- Sources (URLs)
- Stakeholder positions
- Timeline of events
- Relevance to simulation topic