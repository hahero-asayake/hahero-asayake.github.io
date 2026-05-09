#!/usr/bin/env python3
"""Generate OGP images for daily posts.

Routes by front matter layout:
  daily_v2 → notebook card (1200×630, drawn from scratch)
  daily / unset → base image overlay (original behavior)
"""
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

# ── Original (daily) constants ────────────────────────────────────────────────
SNIPPET_LEN = 30
FONT_SCALE = 1.2

# ── daily_v2 notebook card constants ─────────────────────────────────────────
V2_W, V2_H = 1200, 630
MG   = 28;  PAD  = 24;  CR   = 10
SR_H = 175; STSZ = 80

CREAM      = (250, 246, 233)
CREAM_DARK = (237, 231, 208)
INK        = (45,  36,  22)
GREEN      = (74, 124,  89)
BORDER     = (200, 184, 154)
RULE_C     = (215, 198, 170)
ORANGE     = (176,  96,  64)
RAINY_C    = (68, 102, 170)
SUNNY_C    = (204, 136,   0)
WHITE      = (255, 255, 255)
CHIP_BDR   = (232, 192, 144)
V2_BG      = (20,  21,  31)

WEATHER_MAP = {
    'sunny':  ('晴', SUNNY_C,  'はれ（好調）'),
    'cloudy': ('曇', GREEN,    'くもり（ふつう）'),
    'rainy':  ('雨', RAINY_C,  'あめ（不調）'),
}

# ── Font helpers ─────────────────────────────────────────────────────────────

def find_font() -> str:
    """Return path to a Japanese-capable font (for original daily layout)."""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf",
        "/mnt/c/Windows/Fonts/YuGothB.ttc",
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


def find_noto_pair() -> tuple[str, str]:
    """Return (bold_path, regular_path) for NotoSansCJK (daily_v2 only)."""
    bold_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]
    reg_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    bold = next((p for p in bold_candidates if Path(p).exists()), None)
    reg  = next((p for p in reg_candidates  if Path(p).exists()), None)
    if not bold or not reg:
        raise FileNotFoundError("NotoSansCJK bold/regular not found. Install fonts-noto-cjk.")
    return bold, reg


def load_v2_fonts(bold: str, reg: str) -> dict:
    def f(path, sz): return ImageFont.truetype(path, sz)
    return {
        'st': f(bold, 52),  # stamp kanji
        'ml': f(bold, 22),  # meta label
        'mv': f(reg,  30),  # meta value
        'ti': f(bold, 44),  # title
        'tg': f(reg,  24),  # tag
        'bd': f(reg,  28),  # body
    }

# ── Front matter parser ───────────────────────────────────────────────────────

def parse_front_matter(text: str) -> dict:
    """Parse simple YAML front matter (strings and string lists, no nesting)."""
    if not text.startswith('---'):
        return {}
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}
    fm: dict = {}
    cur_key: str | None = None
    cur_list: list | None = None
    for line in parts[1].splitlines():
        if line.startswith('  - ') and cur_list is not None:
            cur_list.append(line[4:].strip())
        elif ':' in line:
            if cur_list is not None:
                fm[cur_key] = cur_list
                cur_list = None
            key, _, val = line.partition(':')
            key = key.strip(); val = val.strip()
            if val:
                fm[key] = val
                cur_key = None
            else:
                cur_key = key
                cur_list = []
    if cur_list is not None and cur_key:
        fm[cur_key] = cur_list
    return fm

# ── Shared text utilities ─────────────────────────────────────────────────────

def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines

# ── Original daily functions ──────────────────────────────────────────────────

def strip_front_matter(text: str) -> str:
    m = re.match(r"^---\r?\n[\s\S]*?\r?\n---\r?\n", text)
    if m:
        return text[m.end():]
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


def get_text_area(width: int, height: int) -> tuple[int, int, int, int]:
    left = int(width * 0.11)
    top = int(height * 0.40)
    right = int(width * 0.89)
    bottom = int(height * 0.59)
    return left, top, right, bottom


def make_background_template(base_image: Image.Image) -> Image.Image:
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


def fit_text(draw, text, font_path, max_width, max_height, max_lines=2):
    max_size = int(88 * FONT_SCALE)
    min_size = int(28 * FONT_SCALE)
    for size in range(max_size, min_size, -2):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text(draw, text, font, max_width)
        if len(lines) > max_lines:
            continue
        line_h = int(size * 1.25)
        if line_h * len(lines) > max_height:
            continue
        widest = max(
            draw.textbbox((0, 0), l, font=font)[2] - draw.textbbox((0, 0), l, font=font)[0]
            for l in lines
        )
        if widest <= max_width:
            return font, lines, line_h
    font = ImageFont.truetype(font_path, min_size)
    lines = wrap_text(draw, text, font, max_width)[:max_lines]
    if lines and len(lines) == max_lines and not lines[-1].endswith("…"):
        lines[-1] = lines[-1][:-1] + "…"
    return font, lines, int(min_size * 1.25)


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

# ── daily_v2 notebook card ────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    r'[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F‍]+',
)


def _remove_emoji(s: str) -> str:
    return _EMOJI_RE.sub('', s)


def _strip_leading_emoji(s: str) -> str:
    return re.sub(r'^' + _EMOJI_RE.pattern + r'\s*', '', s).strip()


def _date_from_stem(stem: str) -> str:
    try:
        y, m, d = stem.split('-')
        return f'{y}ねん {int(m)}がつ {int(d)}にち'
    except Exception:
        return stem


def generate_v2(src: Path, out: Path, fonts: dict, base: Image.Image) -> None:
    raw = src.read_text(encoding='utf-8')
    fm = parse_front_matter(raw)
    body_raw = raw.split('---', 2)[2].strip() if raw.count('---') >= 2 else raw

    title         = fm.get('title') or src.stem
    date_label    = fm.get('date_label') or _date_from_stem(src.stem)
    weather       = fm.get('weather', 'cloudy')
    weather_label = fm.get('weather_label', '')
    observer      = fm.get('observer', 'そねっと4')
    tags = [_strip_leading_emoji(str(t)) for t in (fm.get('tags') or [])]
    tags = [t for t in tags if t]

    body_text = ' '.join(l.strip() for l in body_raw.splitlines() if l.strip())
    body_text = _remove_emoji(body_text).strip()

    stamp_ch, stamp_c, weather_label_auto = WEATHER_MAP.get(weather, ('曇', GREEN, 'くもり（ふつう）'))
    if not weather_label:
        weather_label = weather_label_auto

    bg_rgba = base.convert('RGBA')
    white   = Image.new('RGBA', bg_rgba.size, (255, 255, 255, 255))
    bg_on_white = Image.alpha_composite(white, bg_rgba)
    bg   = bg_on_white.convert('RGB').resize((V2_W, V2_H), Image.LANCZOS)
    bg   = bg.filter(ImageFilter.GaussianBlur(radius=4))
    img  = bg.copy()
    draw = ImageDraw.Draw(img)

    # Card
    card = [MG, MG, V2_W-MG, V2_H-MG]
    draw.rounded_rectangle(card, radius=CR, fill=CREAM)
    draw.rectangle([MG+2, MG+2, V2_W-MG-2, MG+2+SR_H], fill=CREAM_DARK)
    draw.rounded_rectangle(card, radius=CR, outline=BORDER, width=2)
    draw.line([(MG+2, MG+2+SR_H), (V2_W-MG-2, MG+2+SR_H)], fill=BORDER, width=1)

    # Stamp circle
    sx0 = MG + PAD
    sy0 = MG + 2 + (SR_H - STSZ) // 2
    sx1, sy1 = sx0 + STSZ, sy0 + STSZ
    draw.ellipse([sx0, sy0, sx1, sy1], outline=stamp_c, width=3)
    f_st = fonts['st']
    bb = draw.textbbox((0, 0), stamp_ch, font=f_st)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    draw.text(
        (sx0 + (STSZ-tw)//2 - bb[0], sy0 + (STSZ-th)//2 - bb[1]),
        stamp_ch, font=f_st, fill=stamp_c,
    )

    # Meta rows (3 sections, evenly divided in stamp row)
    mx0 = sx1 + PAD
    mx1 = V2_W - MG - PAD
    meta = [
        ('ひづけ',     date_label),
        ('ようす',     weather_label or stamp_ch),
        ('かいたひと', observer),
    ]
    sec_h = SR_H // 3
    f_ml, f_mv = fonts['ml'], fonts['mv']
    for i, (lbl, val) in enumerate(meta):
        sec_top = MG + 2 + i * sec_h
        lh = draw.textbbox((0, 0), lbl, font=f_ml)[3]
        vh = draw.textbbox((0, 0), val, font=f_mv)[3]
        mh = max(lh, vh)
        ry = sec_top + (sec_h - mh) // 2
        lw = draw.textlength(lbl, font=f_ml)
        draw.text((mx0, ry + (mh-lh)//2), lbl, font=f_ml, fill=GREEN)
        draw.text((mx0 + lw + 12, ry + (mh-vh)//2), val, font=f_mv, fill=INK)
        if i < 2:
            draw.line([(mx0, sec_top+sec_h-1), (mx1, sec_top+sec_h-1)], fill=BORDER, width=1)

    # Content area
    cx0 = MG + PAD
    cx1 = V2_W - MG - PAD
    cw  = cx1 - cx0
    cy  = MG + 2 + SR_H + 1 + PAD

    # Title (single line, truncate if needed)
    f_ti = fonts['ti']
    t = title
    if draw.textlength(t, font=f_ti) > cw:
        while len(t) > 1 and draw.textlength(t + '…', font=f_ti) > cw:
            t = t[:-1]
        t += '…'
    draw.text((cx0, cy), t, font=f_ti, fill=INK)
    ti_bb = draw.textbbox((0, 0), t, font=f_ti)
    cy += (ti_bb[3] - ti_bb[1]) + 14

    # Tags
    f_tg = fonts['tg']
    if tags:
        chip_h = draw.textbbox((0, 0), 'あ', font=f_tg)[3] + 8
        tx = cx0
        for tag in tags[:3]:
            chip_w = int(draw.textlength(tag, font=f_tg)) + 16
            if tx + chip_w > cx1:
                break
            draw.rounded_rectangle(
                [tx, cy, tx+chip_w, cy+chip_h],
                radius=3, fill=WHITE, outline=CHIP_BDR, width=2,
            )
            draw.text((tx+8, cy+4), tag, font=f_tg, fill=ORANGE)
            tx += chip_w + 8
        cy += chip_h + 12

    # Body with ruled lines — fill available space, no fixed line limit
    f_bd    = fonts['bd']
    RULE_SP = int(f_bd.size * 1.65)
    bot     = V2_H - MG - PAD

    ry = cy + RULE_SP - 1
    while ry < bot:
        draw.line([(cx0, ry), (cx1, ry)], fill=RULE_C, width=1)
        ry += RULE_SP

    lines = wrap_text(draw, body_text, f_bd, cw)
    ty = cy
    for ln in lines:
        if ty + RULE_SP > bot:
            break
        draw.text((cx0, ty), ln, font=f_bd, fill=INK)
        ty += RULE_SP

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), 'PNG', optimize=True)
    print(f'  {out.name}')

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    if not BASE_IMAGE.exists():
        print(f"Base image not found: {BASE_IMAGE}", file=sys.stderr)
        return 1

    font_path = find_font()
    base: Image.Image = Image.open(BASE_IMAGE)
    template: Image.Image | None = None   # lazy; expensive blur skipped if nothing to do
    v2_fonts: dict | None = None          # lazy

    posts = sorted(p for p in POSTS_DIR.glob("*.md") if p.name != "index.md")
    if not posts:
        print("No daily markdown posts found.")
        return 0

    generated: list[Path] = []
    skipped = 0

    for post in posts:
        out_path = OUT_DIR / f"{post.stem}.png"
        fm = parse_front_matter(post.read_text(encoding='utf-8'))
        layout = fm.get('layout', '')

        if layout == 'daily_v2':
            if out_path.exists():
                skipped += 1
                continue
            if v2_fonts is None:
                bold, reg = find_noto_pair()
                v2_fonts = load_v2_fonts(bold, reg)
            print(f'Generating (v2): {post.name}')
            generate_v2(post, out_path, v2_fonts, base)
            generated.append(out_path)
        else:
            if out_path.exists():
                skipped += 1
                continue
            if template is None:
                template = make_background_template(base)
            generated.append(generate_for_post(post, template, font_path))

    print(f"Generated {len(generated)} OGP images, skipped {skipped} (up-to-date) in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
