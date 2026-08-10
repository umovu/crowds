"""Preset depth packs for /api/simulation/start (quick / balanced / deep).

Single source of truth for the parameter packs applied when a user picks a
simulation depth. Pure dict logic — no LLM, no I/O — so the behaviour is
unit-testable with the LLM switched off. The standalone CLI path keeps its own
copy in scripts/run_simulation_as.py (slightly different numbers, same shape).

`apply_preset` mutates a loaded simulation config dict exactly like the old
inline block in the /start route did:
  * overwrites the convergence/max-min agents params
  * merges the time_config (total_simulation_hours / minutes_per_round)
  * returns the matching max_rounds so the caller can pin the round count
"""

SIM_PRESETS = {
    "quick": {
        "convergence_threshold": 0.08,
        "convergence_window": 3,
        "max_agents_per_round": 10,
        "min_agents_per_round": 2,
        "time_config": {"total_simulation_hours": 6, "minutes_per_round": 60},
        "max_rounds": 6,
    },
    "balanced": {
        "convergence_threshold": 0.05,
        "convergence_window": 3,
        "max_agents_per_round": 15,
        "min_agents_per_round": 3,
        "time_config": {"total_simulation_hours": 12, "minutes_per_round": 60},
        "max_rounds": 12,
    },
    "deep": {
        "convergence_threshold": 0.03,
        "convergence_window": 5,
        "max_agents_per_round": 30,
        "min_agents_per_round": 5,
        "time_config": {"total_simulation_hours": 24, "minutes_per_round": 60},
        "max_rounds": 24,
    },
}


def apply_preset(config, preset):
    """Apply a preset pack to an in-memory config dict.

    Args:
        config: the loaded simulation_config.json dict (mutated in place).
        preset: 'quick' | 'balanced' | 'deep'.

    Returns:
        (max_rounds_from_preset, time_overrides) — (None, {}) if the preset is
        unknown, so callers can treat it as a no-op.
    """
    pack = SIM_PRESETS.get(preset)
    if not pack:
        return None, {}
    config.update({k: v for k, v in pack.items() if k not in ("time_config", "max_rounds")})
    if "time_config" not in config:
        config["time_config"] = {}
    config["time_config"].update(pack["time_config"])
    return pack["max_rounds"], pack["time_config"]
