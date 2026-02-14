#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow is required. Install with: python3 -m pip install pillow", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "blog" / "daily"
BASE_IMAGE = ROOT / "assets" / "ogp.png"
OUT_DIR = ROOT / "assets" / "ogp" / "daily"
SNIPPET_LEN = 30


def find_font() -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
        "/mnt/c/Windows/Fonts/YuGothR.ttc",
        "/mnt/c/Windows/Fonts/msgothic.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError("No Japanese-capable font found. Install Noto CJK fonts.")


def strip_front_matter(text: str) -> str:
    # Support both LF and CRLF front matter blocks.
    m = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n", text)
    if m:
        return text[m.end() :]
    return text


def markdown_to_text(markdown: str) -> str:
    text = strip_front_matter(markdown)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[#>*\-+\d.\s]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def first_snippet(text: str, length: int = SNIPPET_LEN) -> str:
    if len(text) <= length:
        return text
    return text[:length] + "…"


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = list(text)
    lines: list[str] = []
    current = ""
    for ch in words:
        candidate = current + ch
        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = ch
    if current:
        lines.append(current)
    return lines


def generate_for_post(post_path: Path, base_image: Image.Image, font_path: str) -> Path:
    raw = post_path.read_text(encoding="utf-8")
    plain = markdown_to_text(raw)
    snippet = first_snippet(plain)

    img = base_image.copy().convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    width, height = img.size
    pad_x = int(width * 0.07)
    box_h = int(height * 0.22)
    top = height - box_h

    # Keep most of the original image and only add a subtle readable band.
    draw.rectangle([(0, top), (width, height)], fill=(0, 0, 0, 150))

    font_size = max(28, int(height * 0.045))
    font = ImageFont.truetype(font_path, font_size)

    max_text_width = width - pad_x * 2
    lines = wrap_text(draw, snippet, font, max_text_width)
    if len(lines) > 2:
        lines = lines[:2]
        if not lines[-1].endswith("…"):
            lines[-1] = lines[-1][:-1] + "…"

    line_h = int(font_size * 1.35)
    total_h = line_h * len(lines)
    y = top + max(10, (box_h - total_h) // 2)

    for line in lines:
        draw.text((pad_x, y), line, font=font, fill=(255, 255, 255, 245))
        y += line_h

    out_path = OUT_DIR / f"{post_path.stem}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> int:
    if not BASE_IMAGE.exists():
        print(f"Base image not found: {BASE_IMAGE}", file=sys.stderr)
        return 1

    font_path = find_font()
    base = Image.open(BASE_IMAGE)

    posts = sorted(p for p in POSTS_DIR.glob("*.md") if p.name != "index.md")
    if not posts:
        print("No daily markdown posts found.")
        return 0

    generated = [generate_for_post(post, base, font_path) for post in posts]
    print(f"Generated {len(generated)} OGP images in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
