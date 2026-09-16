"""Interviewing a simulation's agents.

Asking a finished or running simulation's agents a question. Four shapes of the same
job: one agent, a batch of different questions, the same question to everyone, and the
post-simulation path that works from saved profiles when the environment has closed.

Three rules carry the weight here:

  * **The prompt prefix.** Agents are told to answer in plain text and not call tools,
    and to stay on the question. Without it they reply with tool calls or drift onto
    unrelated topics, which reads as a broken interview.
  * **The fallback.** A live interview needs the simulation environment running. Once
    it has closed, the only honest option is to answer from the saved profiles, which
    `fallback_interview` does explicitly rather than pretending the environment is up.
  * **Query context.** The question is matched against the run's knowledge graph first,
    so answers are grounded in what the graph actually holds.

No Flask. `storage` is passed in, because only a request can reach `current_app`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..repositories import simulation_repository as repo
from ..utils.logger import get_logger
from .simulation_manager import SimulationManager
from .simulation_runner import SimulationRunner

logger = get_logger("fub.simulation_interview")

#: Prefixed to every interview question. Stops the agent calling tools and keeps it on
#: the topic, answering as a person with lived experience rather than as an analyst.
INTERVIEW_PROMPT_PREFIX = """You are being interviewed about a specific South African policy. Follow these rules STRICTLY:

SPEAKING STYLE:
- Speak as a real South African with lived experience in your community
- Use natural language - you may include SA slang, vernacular, or code-switching where appropriate
- Express yourself as a person with authentic perspective, not as a policy analyst

VOICE:
- If your persona represents a community or collective, use 'we' and 'our community' to express shared views
- If your persona is an individual, use 'I' and 'my' perspective
- Ground your response in how this policy or question affects YOUR LIVELIHOOD, FAMILY, or COMMUNITY

TOPIC FOCUS:
- Stay STRICTLY on the policy or question being asked
- Keep responses concrete and specific about the policy's direct impacts
- Do not volunteer information about sports, entertainment, unrelated political issues, or personal matters unconnected to the topic

RESPONSE FORMAT:
- Reply directly with text only - do not call any tools
- Be concise but substantive - 2-4 sentences minimum for structured questions"""

#: The fallback answers at most this many agents, so a closed-environment interview
#: cannot turn into a very long serial run of model calls.
FALLBACK_AGENT_CAP = 10


class EnvironmentNotRunning(RuntimeError):
    """The simulation environment is not up, so a live interview cannot happen."""


class ProfilesUnavailable(RuntimeError):
    """The saved profiles could not be read."""


class NoAgents(LookupError):
    """The run has no agents to interview."""


class AgentNotFound(LookupError):
    """The named agent is not in this run."""


def optimize_prompt(prompt: str) -> str:
    """Add the interview prefix, once. An already-prefixed prompt is left alone."""
    if not prompt:
        return prompt
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def _require_env(simulation_id: str) -> None:
    """Refuse a live interview when the environment is not running."""
    if not SimulationRunner.check_env_alive(simulation_id):
        raise EnvironmentNotRunning(
            "Simulation environment not running or closed. Please ensure simulation "
            "is started and wait for it to progress.")


def query_context(prompt: str, storage: Any, graph_id: Optional[str]) -> Optional[Any]:
    """What the run's graph holds about this question, or None.

    Best effort: a failure here costs grounding, not the interview, so it is logged
    and swallowed. Runs its own event loop because the extractor is async and this is
    called from a synchronous request.
    """
    if not storage or not graph_id:
        return None
    from .topic_extractor import TopicExtractor
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                TopicExtractor().extract_query_context(prompt, storage, graph_id))
        finally:
            loop.close()
    except Exception as e:  # noqa: BLE001 - grounding is optional
        logger.warning(f"Failed to extract query context: {e}")
        return None


def interview_one(simulation_id: str, agent_id: int, prompt: str,
                  platform: Optional[str] = None, timeout: int = 60,
                  storage: Any = None) -> Dict[str, Any]:
    """Interview a single agent in a running simulation."""
    _require_env(simulation_id)
    state = SimulationManager().get_simulation(simulation_id)
    return SimulationRunner.interview_agent(
        simulation_id=simulation_id,
        agent_id=agent_id,
        prompt=optimize_prompt(prompt),
        platform=platform,
        timeout=timeout,
        query_context=query_context(
            prompt, storage, state.graph_id if state else None),
    )


def interview_batch(simulation_id: str, interviews: List[Dict[str, Any]],
                    platform: Optional[str] = None,
                    timeout: int = 120) -> Dict[str, Any]:
    """Interview several agents, each with their own question.

    Falls back to answering from saved profiles when the live call comes back with no
    results at all — otherwise the caller gets a success with an empty room in it.
    """
    try:
        env_alive = SimulationRunner.check_env_alive(simulation_id)
        logger.info(f"Interview check: simulation={simulation_id}, env_alive={env_alive}")
    except Exception as e:  # noqa: BLE001 - treated as "not running"
        logger.error(f"check_env_alive failed: {e}")
        env_alive = False
    if not env_alive:
        raise EnvironmentNotRunning(
            "Simulation environment not running or closed. Please ensure simulation "
            "is started and wait for it to progress.")

    optimized = []
    for interview in interviews:
        item = dict(interview)
        item['prompt'] = optimize_prompt(interview.get('prompt', ''))
        optimized.append(item)

    result = SimulationRunner.interview_agents_batch(
        simulation_id=simulation_id, interviews=optimized,
        platform=platform, timeout=timeout)

    if not result.get("result", {}).get("results"):
        logger.warning("Interview returned no results, falling back to "
                       "post-simulation interview")
        result = fallback_interview(
            simulation_id=simulation_id,
            profiles=SimulationManager().get_profiles(simulation_id, 'opinion_space') or [],
            prompt=", ".join(iv.get("prompt", "") for iv in optimized),
            platform=platform or 'opinion_space')
    return result


def interview_all(simulation_id: str, prompt: str, platform: Optional[str] = None,
                  timeout: int = 180) -> Dict[str, Any]:
    """Ask every agent in a running simulation the same question."""
    _require_env(simulation_id)
    return SimulationRunner.interview_all_agents(
        simulation_id=simulation_id, prompt=optimize_prompt(prompt),
        platform=platform, timeout=timeout)


def post_simulation(simulation_id: str, prompt: str, agent_id: Optional[int] = None,
                    platform: str = "opinion_space",
                    timeout: float = 180) -> Dict[str, Any]:
    """Interview agents after the run has finished.

    Reads the saved profiles rather than going through the manager, so ANY agent can
    be interviewed — including the ones that never spoke during the run. Uses the live
    API while the environment is still up, and the fallback once it has closed.

    Raises ProfilesUnavailable when the profiles cannot be read, NoAgents when the run
    has none, and AgentNotFound when a named agent is not in it.
    """
    snap = repo.snapshot(simulation_id, repo.PROFILES_FILE)
    if not snap.present:
        raise ProfilesUnavailable(
            f"Profiles file not found: {repo.path(simulation_id, repo.PROFILES_FILE)}")
    profiles = snap.data if isinstance(snap.data, list) else None
    if profiles is None:
        raise ProfilesUnavailable(f"Could not read profiles for {simulation_id}")
    if not profiles:
        raise NoAgents(f"No agents found for simulation {simulation_id}")

    if agent_id is not None:
        targets = [p for p in profiles if p.get('id') == agent_id]
        if not targets:
            raise AgentNotFound(f"Agent {agent_id} not found in simulation")
    else:
        targets = profiles

    optimized = optimize_prompt(prompt)
    interviews = []
    for agent in targets:
        idx = agent.get('id', agent.get('agent_id'))
        if idx is not None:
            interviews.append({"agent_id": idx, "prompt": optimized})

    if SimulationRunner.check_env_alive(simulation_id):
        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id, interviews=interviews,
            platform=platform, timeout=float(timeout))
    else:
        # The run has finished, so there is no environment to ask. Answer from the
        # saved profiles instead, and say so by using this path explicitly.
        result = fallback_interview(simulation_id=simulation_id, profiles=targets,
                                    prompt=optimized, platform=platform)
    return {"interviews_count": len(interviews), "result": result}


def fallback_interview(simulation_id: str, profiles: List[Dict[str, Any]], prompt: str,
                       platform: str = "opinion_space") -> Dict[str, Any]:
    """Answer from saved profiles when the simulation environment is not running.

    One model call per agent, capped at FALLBACK_AGENT_CAP. A failure for one agent is
    recorded in that agent's own answer rather than failing the whole round.
    """
    from ..utils.llm_client import LLMClient

    llm = LLMClient()
    results: Dict[str, Any] = {}

    for agent in profiles[:min(FALLBACK_AGENT_CAP, len(profiles))]:
        agent_id = agent.get('id', agent.get('agent_id'))
        if agent_id is None:
            continue

        name = agent.get('username') or agent.get('name') or f"Agent {agent_id}"
        bio = (agent.get('bio', '') or agent.get('persona', '')
               or agent.get('background_story', ''))
        role = agent.get('profession') or agent.get('occupation', 'Citizen')

        context_prompt = f"""You are {name}, a {role} in South Africa.

Your background: {bio[:500]}

Please answer the following question in YOUR OWN VOICE, as yourself:

{prompt}

Remember:
1. Answer directly as your character
2. Do not call any tools
3. Do not use JSON or markdown formatting
4. Provide a genuine, personal response"""

        try:
            response = llm.chat(messages=[{"role": "user", "content": context_prompt}],
                                temperature=0.7)
        except Exception as e:  # noqa: BLE001 - one agent failing is not the round
            response = f"Sorry, I couldn't process this interview: {str(e)}"

        results[f"{platform}_{agent_id}"] = {
            "agent_id": agent_id, "response": response, "platform": platform,
        }

    return {
        "success": True,
        "interviews_count": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }
