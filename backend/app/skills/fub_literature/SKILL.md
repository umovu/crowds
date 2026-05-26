---
name: fub_literature
description: Search academic literature across ArXiv, OpenAlex, and CrossRef
user_invocable: true
---

# Fub Literature Search

Search academic databases for research papers to ground policy simulations in real-world evidence.

## When to Use

- Before creating a simulation, to understand the research landscape
- Finding papers on specific policy topics
- Discovering key authors, findings, and citations

## How to Use

1. Provide a search query (e.g., "minimum wage informal economy South Africa")
2. Optionally specify sources: arxiv, openalex, crossref
3. Review returned papers with titles, authors, abstracts, and citation counts
4. Save relevant papers to your research context

## Sources

| Source | Coverage | Access |
|--------|----------|--------|
| ArXiv | Preprints (CS, Econ, Physics) | Free, no API key |
| OpenAlex | Published academic works | Free, no API key |
| CrossRef | DOI-based metadata | Free, no API key |

## Output

Returns a list of papers with:
- Title, authors, publication year
- Abstract
- Source badge
- Citation count (OpenAlex only)
- Link to full text

## Integration

This skill calls Fub's backend API which handles the actual HTTP requests to academic APIs.
Results are returned in a standardized format compatible with the agent workspace.