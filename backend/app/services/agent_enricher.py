"""
Agent Enricher — Uses research findings to enhance agent persona context.

Takes structured research (from literature search or deep web research)
and transforms it into prompt context injected into agent profiles during
simulation setup.
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.logger import get_logger

logger = get_logger("fub.agent_enricher")


class AgentContextEnricher:
    """
    Transforms research findings into agent persona context.

    Research results (literature papers, web research) are processed into
    structured context blocks that get injected into agent profile prompts
    during simulation setup.
    """

    @staticmethod
    def enrich_from_literature(
        papers: List[Dict[str, Any]],
        archetypes: List[str]
    ) -> Dict[str, str]:
        """
        Create enriched context for archetypes based on literature.

        Args:
            papers: List of paper dicts from LiteratureSearchService
            archetypes: List of archetype names to target

        Returns:
            Dict mapping archetype name → enriched context string
        """
        if not papers:
            return {}

        # Generate research summary from papers
        summary_parts = []
        for paper in papers:
            title = paper.get("title", "")
            authors = ", ".join(paper.get("authors", [])[:3])
            year = paper.get("year", "")
            source = paper.get("source", "")
            summary_parts.append(
                f"- {title} ({year}, {source}) — {authors}"
            )

        research_context = (
            "Research context for this simulation:\n"
            + "\n".join(summary_parts[:10])
        )

        context = {}
        for archetype in archetypes:
            context[archetype] = research_context

        return context

    @staticmethod
    def enrich_from_web_research(
        research_result: Dict[str, Any],
        archetypes: List[str]
    ) -> Dict[str, str]:
        """
        Create enriched context for archetypes based on web research.

        Args:
            research_result: Result from deep research service
            archetypes: List of archetype names to target

        Returns:
            Dict mapping archetype name → enriched context string
        """
        if not research_result.get("success"):
            return {}

        content = research_result.get("content", "")
        if not content:
            return {}

        context = {}
        for archetype in archetypes:
            context[archetype] = (
                "Recent research and news context:\n"
                + content[:2000]
            )

        return context

    @staticmethod
    def enrich_from_web_research(
        research_results: Dict[str, str],
        archetypes: List[str]
    ) -> Dict[str, str]:
        """
        Create enriched context from deep web research.

        Args:
            research_results: Dict mapping archetype → research text from web research
            archetypes: List of archetype names to target

        Returns:
            Dict mapping archetype name → enriched context string
        """
        context = {}
        for archetype in archetypes:
            if archetype in research_results:
                content = research_results[archetype]
                if content and len(content.strip()) >= 50:
                    context[archetype] = (
                        "CURRENT REALITY RESEARCH (from web research):\n"
                        + content[:3000]
                    )
        return context

    @staticmethod
    def build_enriched_prompt(
        base_prompt: str,
        archetype: str,
        enriched_context: Optional[str]
    ) -> str:
        """
        Combine base agent prompt with enriched research context.

        Args:
            base_prompt: Original agent prompt
            archetype: Agent archetype name
            enriched_context: Context from enrich_from_* methods

        Returns:
            Combined prompt string
        """
        if not enriched_context:
            return base_prompt

        return (
            base_prompt.rstrip()
            + "\n\n"
            + "## Research Context\n"
            + enriched_context
        )