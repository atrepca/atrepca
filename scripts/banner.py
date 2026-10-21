#!/usr/bin/env python3
"""Render the README greeting banner (docs/banner.svg): a terminal prompt that
types out the greeting, then leaves a blinking cursor.

The text is pinned to a fixed width with textLength so the cursor lands right
after it whatever monospace font the viewer's system picks.
"""
from pathlib import Path

GREETING = "Hi, I'm Alex!"
PROMPT = "$"
SIZE = 36            # font size
CHAR_W = SIZE * 0.6  # typical monospace advance
TEXT_X = 2 * CHAR_W + 2
DELAY, TYPE = 0.4, 1.3  # seconds before typing starts, seconds to type
STOPS = ["#2f81f7", "#6e7ff3", "#a371f7"]
MUTED = "#8b949e"
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,Liberation Mono,monospace"


def main():
    n = len(GREETING)
    text_w = n * CHAR_W
    cursor_x = TEXT_X + text_w + 4
    width, height = round(cursor_x + CHAR_W + 8), 56
    stops = "".join(f'<stop offset="{i / (len(STOPS) - 1):.2f}" stop-color="{c}"/>' for i, c in enumerate(STOPS))
    # One discrete step per character: the clip widens and the cursor advances together.
    widths = ";".join(f"{i * CHAR_W:.1f}" for i in range(n + 1))
    xs = ";".join(f"{TEXT_X + i * CHAR_W + (4 if i == n else 0):.1f}" for i in range(n + 1))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{PROMPT} {GREETING}">
<defs>
  <linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{TEXT_X:.1f}" y1="0" x2="{TEXT_X + text_w:.1f}" y2="0">{stops}</linearGradient>
  <clipPath id="typed"><rect x="{TEXT_X:.1f}" y="0" width="{text_w:.1f}" height="{height}">
    <set attributeName="width" to="0" begin="0s" end="{DELAY}s"/>
    <animate attributeName="width" values="{widths}" calcMode="discrete" begin="{DELAY}s" dur="{TYPE}s" fill="freeze"/>
  </rect></clipPath>
</defs>
<g font-family="{FONT}" font-size="{SIZE}" font-weight="700">
  <text x="0" y="40" fill="{MUTED}">{PROMPT}</text>
  <text x="{TEXT_X:.1f}" y="40" textLength="{text_w:.1f}" lengthAdjust="spacingAndGlyphs" fill="url(#g)" clip-path="url(#typed)">{GREETING.replace("'", "&#39;")}</text>
</g>
<rect x="{cursor_x:.1f}" y="12" width="{CHAR_W * 0.85:.1f}" height="34" fill="{STOPS[-1]}">
  <set attributeName="x" to="{TEXT_X:.1f}" begin="0s" end="{DELAY}s"/>
  <animate attributeName="x" values="{xs}" calcMode="discrete" begin="{DELAY}s" dur="{TYPE}s" fill="freeze"/>
  <animate attributeName="opacity" values="1;0" calcMode="discrete" begin="{DELAY + TYPE}s" dur="1s" repeatCount="indefinite"/>
</rect>
</svg>
'''
    out = Path(__file__).resolve().parent.parent / "docs" / "banner.svg"
    out.write_text(svg)
    print(f"wrote {out} ({width}x{height})")


if __name__ == "__main__":
    main()
