"""A/B rerun of the Thuto panel (original: panel_39692ef06a7c, seed 39133)
under the fixed code: annual fee units, real-numbers anchor in the panel
prompt, tier-aware card binding. Creates a NEW session with identical
parameters and runs one pitch round. ~12 sim-tier LLM calls.
"""
import asyncio
import json
import os
import sys

BACKEND = r"D:\Fub-agentsociety\backend"
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(r"D:\Fub-agentsociety\.env")
load_dotenv(os.path.join(BACKEND, ".env"))

# Same SIM_* -> AGENTSOCIETY_* mapping run.py does.
os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY",
                      os.environ.get("SIM_LLM_API_KEY", os.environ.get("LLM_API_KEY", "")))
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE",
                      os.environ.get("SIM_LLM_BASE_URL", os.environ.get("LLM_BASE_URL", "")))
os.environ.setdefault("AGENTSOCIETY_LLM_MODEL",
                      os.environ.get("SIM_LLM_MODEL", os.environ.get("LLM_MODEL_NAME", "")))

from app.services import panel_service
from app.services.interview_service import InterviewService

OLD_META = json.load(open(
    os.path.join(BACKEND, "uploads", "panel_sessions", "panel_39692ef06a7c", "panel_session.json"),
    encoding="utf-8"))

meta = panel_service.create_session(
    pitch=OLD_META["pitch"],
    mode=OLD_META["mode"],
    n=OLD_META["requested_size"],
    seed=OLD_META["seed"],
    segments=OLD_META["segments"],
    user_id=OLD_META.get("user_id"),
)
sid = meta["session_id"]
print("new session:", sid)
print("tiers:", meta.get("budget_tier_distribution"))

framed = panel_service.frame_pitch(OLD_META["pitch"], OLD_META["mode"])
svc = InterviewService(sid, base_dir=os.path.join(BACKEND, "uploads", "panel_sessions"))

result = asyncio.new_event_loop().run_until_complete(
    svc.batch_impact_interview(question=framed, concurrency=6))

panel_service.save_round(sid, {
    "pitch": OLD_META["pitch"],
    "framed_pitch": framed,
    "agent_ids": None,
    "result": result,
})
print("round saved; successful:", result["successful"], "/", result["total_interviewed"])
print("stances:", result["impact_dashboard"].get("stance_distribution")
      if isinstance(result.get("impact_dashboard"), dict) else "")
print("report:", os.path.join(BACKEND, "uploads", "panel_sessions", sid, "REPORT.md"))
