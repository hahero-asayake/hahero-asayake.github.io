#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
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


def get_text_area(width: int, height: int) -> tuple[int, int, int, int]:
    # Area where "Asayake Hahero" exists in the original base image.
    left = int(width * 0.11)
    top = int(height * 0.40)
    right = int(width * 0.89)
    bottom = int(height * 0.59)
    return left, top, right, bottom


def make_background_template(base_image: Image.Image) -> Image.Image:
    # Remove original title by blending a locally blurred version.
    img = base_image.convert("RGB")
    width, height = img.size
    blurred = img.filter(ImageFilter.GaussianBlur(radius=max(18, int(min(width, height) * 0.035))))

    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    area = get_text_area(width, height)
    corner_r = int(min(width, height) * 0.05)
    mask_draw.rounded_rectangle(area, radius=corner_r, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(10, int(min(width, height) * 0.02))))
    return Image.composite(blurred, img, mask)


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    max_width: int,
    max_height: int,
    max_lines: int = 2,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(88, 28, -2):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) > max_lines:
            continue
        line_h = int(size * 1.25)
        total_h = line_h * len(lines)
        widest = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            widest = max(widest, bbox[2] - bbox[0])
        if widest <= max_width and total_h <= max_height:
            return font, lines, line_h

    # Fallback: smallest size and force 2 lines at most.
    font = ImageFont.truetype(font_path, 28)
    lines = wrap_text(draw, text, font, max_width)[:max_lines]
    if lines and len(lines) == max_lines and not lines[-1].endswith("…"):
        lines[-1] = lines[-1][:-1] + "…"
    return font, lines, int(28 * 1.25)


def generate_for_post(post_path: Path, base_template: Image.Image, font_path: str) -> Path:
    raw = post_path.read_text(encoding="utf-8")
    plain = markdown_to_text(raw)
    snippet = first_snippet(plain)

    img = base_template.copy().convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size
    left, top, right, bottom = get_text_area(width, height)
    area_w = right - left
    area_h = bottom - top

    font, lines, line_h = fit_text(
        draw=draw,
        text=snippet,
        font_path=font_path,
        max_width=int(area_w * 0.92),
        max_height=int(area_h * 0.82),
    )
    total_h = line_h * len(lines)
    y = top + (area_h - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = left + (area_w - line_w) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 110))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 245))
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
    template = make_background_template(base)

    posts = sorted(p for p in POSTS_DIR.glob("*.md") if p.name != "index.md")
    if not posts:
        print("No daily markdown posts found.")
        return 0

    generated = [generate_for_post(post, template, font_path) for post in posts]
    print(f"Generated {len(generated)} OGP images in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
