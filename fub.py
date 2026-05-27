"""
Fub Simulation — root CLI entry point.
Usage:
  python fub.py           Start the backend server
  python fub.py -v        Print version and exit
  python fub.py --version Print version and exit
"""

import argparse
import os
import sys


def _get_version() -> str:
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
    try:
        with open(version_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0.0"


def main():
    parser = argparse.ArgumentParser(description="Fub Simulation — multi-agent policy simulation engine")
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"fub-simulation v{_get_version()}",
    )
    args, remaining = parser.parse_known_args()

    # Forward to backend/run.py
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
    sys.path.insert(0, os.getcwd())

    from run import main as backend_main
    backend_main()


if __name__ == "__main__":
    main()
