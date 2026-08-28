"""Where the real data lives.

The learning worktree is a clean checkout, so it does NOT contain the survey
microdata or the persona library — both are gitignored (licensed data, and
generated personas). Rather than copy them, we read them from the main working
copy, READ-ONLY.

Nothing in learn/ ever writes to MAIN. If a notebook needs to save something,
it saves under learn/output/.
"""

from pathlib import Path

# The main working copy — the one you actually develop and run the app in.
MAIN = Path("D:/Fub-agentsociety")

# This worktree.
LEARN = Path(__file__).resolve().parent
OUTPUT = LEARN / "output"
OUTPUT.mkdir(exist_ok=True)

# ── Survey microdata (licensed, read-only) ────────────────────────────────
MICRODATA = MAIN / "backend" / "data" / "microdata"

AFROBAROMETER = MICRODATA / "attitudes" / "afrobarometer_r9_sa.sav"
GHS_PERSON    = MICRODATA / "ghs-2025-v1" / "ghs-2025-person-v1.dta"
GHS_HOUSEHOLD = MICRODATA / "ghs-2025-v1" / "ghs-2025-household-v1.dta"
QLFS          = MICRODATA / "qlfs-2026-q1-v1" / "qlfs-2026-q1-v1.dta"
QLFS_CSV      = MICRODATA / "qlfs-2026-q1-v1" / "qlfs-2026-q1-v1.csv"

# ── Generated artefacts from the live system (read-only) ──────────────────
PERSONAS      = MAIN / "backend" / "app" / "data" / "persona_library" / "personas.json"
SCRIPTS       = MAIN / "backend" / "scripts"          # backtest_responses_*.jsonl live here

# ── The production code, importable so you can compare against it ─────────
# e.g.  import sys; sys.path.insert(0, str(SCRIPTS)); import attitude_donor_adapter
BACKEND       = MAIN / "backend"


def check():
    """Print what exists. Run this first in any notebook."""
    items = {
        "Afrobarometer R9 (.sav)": AFROBAROMETER,
        "GHS person (.dta)":       GHS_PERSON,
        "GHS household (.dta)":    GHS_HOUSEHOLD,
        "QLFS (.dta)":             QLFS,
        "persona library (.json)": PERSONAS,
        "scripts dir":             SCRIPTS,
    }
    for label, p in items.items():
        mark = "ok " if p.exists() else "MISSING"
        size = f"{p.stat().st_size / 1e6:.1f} MB" if p.exists() and p.is_file() else ""
        print(f"{mark:8} {label:26} {size:>10}  {p}")


if __name__ == "__main__":
    check()
