"""
Read a poster image into text with the vision tier.

One call per image. The personas never see the image — they see this text.

Usage:
    python backend/scripts/read_poster.py path/to/poster.png
"""

import mimetypes
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.llm_client import LLMClient  # noqa: E402


PROMPT = """You are looking at a poster or advertisement, most likely from South Africa.

Describe it so that someone who cannot see it understands exactly what is on it.
Cover, in this order:

1. EVERY word of text, transcribed exactly, including small print, and noting
   how prominent each piece is (headline / body / footnote).
2. Who or what is pictured — people, their apparent age and dress, objects,
   setting, logos, branding.
3. The layout: what the eye hits first, second, third.
4. The claim being made, and any claim only implied.
5. What it asks the reader to do, and how to do it.

Report only what is actually on the poster. Do not judge whether it is good.
Do not say who it is aimed at, do not describe an audience or a market, and do
not guess who would respond to it. Choosing who sees this is not your job.
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"No such file: {path}")
        return 2

    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as fh:
        image_bytes = fh.read()

    client = LLMClient.for_vision()
    print(f"model={client.model}  base_url={client.base_url}")
    print(f"image={path}  {len(image_bytes) / 1024:.0f} KB  {mime}\n")

    started = time.time()
    # Low temperature: the same poster should read the same way twice.
    # Large max_tokens: thinking tokens count against output, and a truncated
    # answer is spend with nothing to show for it.
    text = client.chat(
        messages=[LLMClient.image_message(PROMPT, image_bytes, mime)],
        temperature=0.2,
        max_tokens=8000,
    )
    elapsed = time.time() - started

    print(text or "(empty response — raise max_tokens)")
    stats = client.get_stats()
    print(
        f"\n{elapsed:.1f}s  prompt={stats['prompt_tokens']}  "
        f"completion={stats['completion_tokens']}  "
        f"cost=${stats['estimated_cost_usd']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
