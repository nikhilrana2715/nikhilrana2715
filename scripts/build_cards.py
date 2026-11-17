"""Build editorial SVG cards for the GitHub profile README.

GitHub strips CSS/JS from READMEs, so all typography lives inside SVG images.
Fonts (Onest, IBM Plex Mono) are subset per card and embedded as base64, so
the cards render identically everywhere. Run locally or via the daily Action:

    python scripts/build_cards.py            # uses public API, no token needed
    GITHUB_TOKEN=... python scripts/build_cards.py

Tokens mirror the portfolio (nikhil-rana-portfolio.vercel.app/tokens.css).
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path

import logging

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ASSETS / "cards"
USER = "nikhilrana2715"
W = 840  # card width (GitHub README column ~ 830-880px)

# ---------------------------------------------------------------- tokens
THEMES = {
    "dark": dict(bg="#1B1817", surface="#211E1C", raised="#2A2624", text="#EDE7E1",
                 muted="#A39C97", accent="#D07A4C", border="#332E2B",
                 stripe="rgba(255,255,255,.025)", ok="#4FB286"),
    "light": dict(bg="#F5F1EC", surface="#EFE9E3", raised="#FFFFFF", text="#1A1818",
                  muted="#7D7773", accent="#A4552C", border="#DCD5D0",
                  stripe="rgba(26,24,24,.03)", ok="#1F7A5A"),
}

# ---------------------------------------------------------------- content
PROJECTS = [
    dict(slug="nova-hop", no="01", kind="GAME", title="Nova Hop",
         line="Sky-climbing arcade game. Combos, power-ups, 4 zones and skins. Plays offline on phone and desktop.",
         tags=["JavaScript", "Canvas", "PWA"], cta="Play now", url="https://nova-hop.vercel.app/"),
    dict(slug="funny-jump", no="02", kind="GAME", title="Funny Jump",
         line="Cartoon 3D runner and platformer with a live day-to-night cycle. Browser, Chrome toolbar and Android.",
         tags=["JavaScript", "3D", "Extension"], cta="Play now", url="https://running-game-91zr.vercel.app/"),
    dict(slug="mma", no="03", kind="WORK", title="Morning Meeting App",
         line="Upload the day's Excel production report, get a live dashboard. Used every morning at MRS Bearings.",
         tags=["TypeScript", "React", "Excel"], cta="View code", url="https://github.com/nikhilrana2715/MMA"),
    dict(slug="quick-lock", no="04", kind="DESKTOP", title="Quick Lock",
         line="App lock for Windows. Suspends a protected app until you type the master password.",
         tags=["Tauri 2", "Rust", "React"], cta="View code", url="https://github.com/nikhilrana2715/Locker"),
    dict(slug="applock", no="05", kind="ANDROID", title="AppLock",
         line="Android app protection with biometric unlock, PIN and pattern. Built with Material 3.",
         tags=["Kotlin", "Compose"], cta="View code", url="https://github.com/nikhilrana2715/App-Lock"),
    dict(slug="taskflow", no="06", kind="WEB", title="TaskFlow Pro",
         line="Full-stack productivity app for tasks, projects and goals, with offline support and reminders.",
         tags=["TypeScript", "Full-stack"], cta="Open live", url="https://taskflow-pro-xi-blush.vercel.app"),
]

TOOLKIT = [
    ("FRONTEND", ["React", "TypeScript", "JavaScript", "Next.js", "Tailwind", "HTML/CSS"]),
    ("BACKEND", ["Node.js", "Express", "Python", "Flask", "REST APIs"]),
    ("DATA", ["SQL", "MySQL", "MongoDB", "Power BI", "Excel"]),
    ("APPS & GAMES", ["Kotlin", "Compose", "Rust", "Tauri", "Canvas", "PWA"]),
    ("SHIP", ["Git", "GitHub Actions", "Vercel", "VS Code"]),
]

SECTIONS = {
    "about": ("01 — RIGHT NOW", "Two tracks, one goal."),
    "work": ("02 — SELECTED WORK", "Things I've shipped."),
    "toolkit": ("03 — TOOLKIT", "Tools I build with."),
    "field": ("04 — FROM THE FIELD", "Numbers, not adjectives."),
}

# ---------------------------------------------------------------- fonts
FONT_DIR = ASSETS / "fonts"
_static: dict[str, TTFont] = {}


def _font(key: str) -> TTFont:
    """key: 'onest-400' | 'onest-500' | 'onest-700' | 'mono'"""
    if key not in _static:
        if key == "mono":
            _static[key] = TTFont(FONT_DIR / "IBMPlexMono-Medium.ttf")
        else:
            wght = int(key.split("-")[1])
            _static[key] = instancer.instantiateVariableFont(
                TTFont(FONT_DIR / "Onest.ttf"), {"wght": wght})
    return _static[key]


def text_width(s: str, key: str, size: float, tracking: float = 0) -> float:
    f = _font(key)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    w = sum(hmtx[cmap.get(ord(c), cmap.get(ord("?")))][0] for c in s)
    return w * size / upm + tracking * size * max(len(s) - 1, 0)


def wrap(s: str, key: str, size: float, max_w: float) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if text_width(trial, key, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def font_face(family: str, key: str, chars: str) -> str:
    f = _font(key)
    buf = io.BytesIO()
    opts = subset.Options()
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = []
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(text=chars + " ")
    import copy
    ft = copy.deepcopy(f)
    sub.subset(ft)
    ft.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,{b64}) format('truetype');}}"


class Card:
    """Tiny SVG builder that tracks glyphs per font so it can subset."""

    FAM = {"onest-400": "O4", "onest-500": "O5", "onest-700": "O7", "mono": "PM"}

    def __init__(self, w: int, h: int, theme: str, title: str):
        self.w, self.h, self.t, self.title = w, h, THEMES[theme], title
        self.theme = theme
        self.body: list[str] = []
        self.used: dict[str, set[str]] = {k: set() for k in self.FAM}
        self.defs: list[str] = []
        self.css: list[str] = []

    def text(self, x, y, s, key="onest-400", size=16, fill=None, anchor="start",
             tracking=0.0, upper=False, extra=""):
        s = s.upper() if upper else s
        self.used[key].update(s)
        ls = f' letter-spacing="{tracking * size:.2f}"' if tracking else ""
        self.body.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{self.FAM[key]}" font-size="{size}"'
            f' fill="{fill or self.t["text"]}" text-anchor="{anchor}"{ls} {extra}>{html.escape(s)}</text>')

    def raw(self, s: str):
        self.body.append(s)

    def render(self) -> str:
        faces = "".join(font_face(self.FAM[k], k, "".join(sorted(v)))
                        for k, v in self.used.items() if v)
        css = faces + "".join(self.css) + (
            "@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" role="img" '
                f'aria-label="{html.escape(self.title)}"><title>{html.escape(self.title)}</title>'
                f'<defs><style>{css}</style>{"".join(self.defs)}</defs>'
                f'{"".join(self.body)}</svg>')


# ---------------------------------------------------------------- images
def data_uri(img: Image.Image, fmt="PNG", quality=82) -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        mime = "image/jpeg"
    else:
        img.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode()}"


def sticker(name: str, height: int) -> tuple[str, int, int]:
    """Transparent chibi with a white die-cut border, sized @2x for retina."""
    im = Image.open(ASSETS / "src" / f"sticker-{name}.png").convert("RGBA")
    pad = 10
    canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, (pad, pad), im)
    alpha = canvas.getchannel("A").point(lambda a: 255 if a > 60 else 0)
    border = alpha.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(0.8))
    shadow = border.filter(ImageFilter.GaussianBlur(4)).point(lambda a: int(a * 0.35))
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 255)); sh.putalpha(shadow)
    out.alpha_composite(sh, (0, 3))
    white = Image.new("RGBA", canvas.size, (255, 255, 255, 255)); white.putalpha(border)
    out.alpha_composite(white)
    out.alpha_composite(canvas)
    out = out.crop(out.getbbox())
    scale = (height * 2) / out.height
    out = out.resize((round(out.width * scale), height * 2), Image.LANCZOS)
    return data_uri(out), out.width // 2, height


def portrait(w: int, h: int) -> str:
    im = Image.open(ASSETS / "src" / "portrait-bw.jpg")
    # cover-crop to w:h
    tr = w / h
    sw, sh = im.size
    if sw / sh > tr:
        nw = int(sh * tr); im = im.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
    else:
        nh = int(sw / tr); im = im.crop((0, 0, sw, nh))
    im = im.resize((w * 2, h * 2), Image.LANCZOS)
    return data_uri(im, "JPEG", 80)


# ---------------------------------------------------------------- data
def gh(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-cards",
                                               "Accept": "application/vnd.github+json"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def fetch_stats() -> dict:
    cache = OUT / "stats.json"
    try:
        user = json.loads(gh(f"https://api.github.com/users/{USER}"))
        repos = json.loads(gh(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
        own = [r for r in repos if not r["fork"]]
        langs = Counter(r["language"] for r in own if r["language"])
        page = gh(f"https://github.com/users/{USER}/contributions")
        m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", page)
        stats = dict(
            repos=user["public_repos"], followers=user["followers"],
            stars=sum(r["stargazers_count"] for r in own),
            live=sum(1 for r in own if r.get("homepage")),
            contrib=int(m.group(1).replace(",", "")) if m else None,
            langs=langs.most_common(5),
        )
        cache.write_text(json.dumps(stats, indent=2))
        return stats
    except Exception as e:  # network hiccup: keep last good numbers
        print("stats fetch failed, using cache:", e)
        return json.loads(cache.read_text())


# ---------------------------------------------------------------- shared bits
def frame(c: Card, h: int | None = None, r: int = 20):
    t, h = c.t, h or c.h
    c.defs.append(f'<pattern id="st" width="8" height="8" patternUnits="userSpaceOnUse" '
                  f'patternTransform="rotate(45)"><rect width="1" height="8" fill="{t["stripe"]}"/></pattern>')
    c.raw(f'<rect x=".5" y=".5" width="{c.w - 1}" height="{h - 1}" rx="{r}" fill="{t["surface"]}" stroke="{t["border"]}"/>')
    c.raw(f'<rect x=".5" y=".5" width="{c.w - 1}" height="{h - 1}" rx="{r}" fill="url(#st)"/>')


def eyebrow(c: Card, x, y, s, anchor="start"):
    c.text(x, y, s, "mono", 12, c.t["accent"], anchor, tracking=0.14, upper=True)


def float_anim(c: Card, cls: str, amp=6, dur=4.0, rot=0):
    c.css.append(
        f"@keyframes {cls}{{0%,100%{{transform:translateY(0) rotate({rot}deg)}}"
        f"50%{{transform:translateY(-{amp}px) rotate({-rot}deg)}}}}"
        f".{cls}{{animation:{cls} {dur}s ease-in-out infinite;transform-box:fill-box;transform-origin:center}}")


# ---------------------------------------------------------------- cards
def card_hero(theme: str) -> str:
    c = Card(W, 400, theme, "Nikhil Rana — web, game and app developer from Ranchi, India")
    t = c.t
    frame(c, r=24)
    x = 48
    eyebrow(c, x, 72, "Developer · MCA student · Ranchi, IN")
    c.text(x, 140, "Hi, I'm Nikhil.", "onest-700", 60, tracking=-0.035)
    lines = wrap("I build web apps, games and Android apps — and ship them so people can actually use them.",
                 "onest-400", 20, 400)
    for i, ln in enumerate(lines):
        c.text(x, 188 + i * 30, ln, "onest-400", 20, t["muted"])
    # status pill
    py = 188 + len(lines) * 30 + 22
    label = "Developer @ MRS Bearings"
    pw = text_width(label, "onest-500", 14) + 44
    c.raw(f'<rect x="{x}" y="{py}" width="{pw:.0f}" height="34" rx="17" fill="{t["raised"]}" stroke="{t["border"]}"/>')
    c.raw(f'<circle cx="{x + 18}" cy="{py + 17}" r="4" fill="{t["ok"]}"><animate attributeName="opacity" '
          f'values="1;.35;1" dur="2.4s" repeatCount="indefinite"/></circle>')
    c.text(x + 30, py + 22, label, "onest-500", 14)
    c.text(x, 368, "Open to freelance, collabs & full-time roles", "mono", 12, t["muted"], tracking=0.04)
    # portrait as a taped print
    pw_, ph_ = 236, 300
    px, py2 = 548, 50
    c.raw(f'<g transform="rotate(2.5 {px + pw_ / 2} {py2 + ph_ / 2})">'
          f'<rect x="{px - 10}" y="{py2 - 10}" width="{pw_ + 20}" height="{ph_ + 20}" rx="4" fill="#F7F3EE"/>'
          f'<image x="{px}" y="{py2}" width="{pw_}" height="{ph_}" href="{portrait(pw_, ph_)}" preserveAspectRatio="xMidYMid slice"/>'
          f'<rect x="{px + pw_ / 2 - 40}" y="{py2 - 22}" width="80" height="24" fill="{t["accent"]}" opacity=".55" '
          f'transform="rotate(-4 {px + pw_ / 2} {py2 - 10})"/></g>')
    uri, sw, sh = sticker("jump", 150)
    float_anim(c, "fl", amp=7, dur=4.2, rot=2)
    c.raw(f'<image class="fl" x="{px - sw + 40}" y="{400 - sh - 18}" width="{sw}" height="{sh}" href="{uri}"/>')
    return c.render()


def card_section(theme: str, key: str) -> str:
    kicker, head = SECTIONS[key]
    c = Card(W, 96, theme, head)
    eyebrow(c, 4, 30, kicker)
    c.text(2, 80, head, "onest-700", 40, tracking=-0.03)
    return c.render()


def card_about(theme: str) -> str:
    c = Card(W, 270, theme, "Right now: full-time developer job and MCA")
    t = c.t
    frame(c)
    cols = [
        ("TRACK 01 — JOB", "Developer, MRS Bearings",
         ["Real-time projects for real users", "Requirement → research → ship"]),
        ("TRACK 02 — MCA", "MCA, 2026 – 2028",
         ["Studying alongside the job", "Java, Python, DSA + MCA project"]),
    ]
    for i, (k, h, pts) in enumerate(cols):
        x = 40 + i * 320
        eyebrow(c, x, 56, k)
        c.text(x, 92, h, "onest-700", 21, tracking=-0.01)
        for j, p in enumerate(pts):
            y = 132 + j * 34
            c.text(x, y, f"0{j + 1}", "mono", 12, t["accent"])
            c.text(x + 30, y, p, "onest-400", 15, t["muted"])
    c.raw(f'<line x1="40" y1="206" x2="{W - 220}" y2="206" stroke="{t["border"]}"/>')
    c.text(40, 238, "First Python script at 16. Haven't stopped building since.", "onest-500", 15)
    uri, sw, sh = sticker("drink", 190)
    float_anim(c, "fl", amp=5, dur=5)
    c.raw(f'<image class="fl" x="{W - sw - 36}" y="{270 - sh - 26}" width="{sw}" height="{sh}" href="{uri}"/>')
    return c.render()


def card_project(theme: str, p: dict) -> str:
    cw, ch = 412, 236
    c = Card(cw, ch, theme, f'{p["title"]} — {p["line"]}')
    t = c.t
    c.defs.append(f'<pattern id="st" width="8" height="8" patternUnits="userSpaceOnUse" '
                  f'patternTransform="rotate(45)"><rect width="1" height="8" fill="{t["stripe"]}"/></pattern>')
    c.raw(f'<rect x=".5" y=".5" width="{cw - 1}" height="{ch - 1}" rx="18" fill="{t["surface"]}" stroke="{t["border"]}"/>')
    c.text(28, 44, p["no"], "mono", 13, t["accent"])
    c.text(cw - 28, 44, p["kind"], "mono", 11, t["muted"], "end", tracking=0.14)
    c.text(28, 86, p["title"], "onest-700", 28, tracking=-0.025)
    for i, ln in enumerate(wrap(p["line"], "onest-400", 14.5, cw - 56)[:3]):
        c.text(28, 116 + i * 22, ln, "onest-400", 14.5, t["muted"])
    # tags
    tx = 28
    for tag in p["tags"]:
        tw = text_width(tag, "mono", 11) + 20
        c.raw(f'<rect x="{tx}" y="{ch - 58}" width="{tw:.0f}" height="24" rx="12" fill="none" stroke="{t["border"]}"/>')
        c.text(tx + 10, ch - 42, tag, "mono", 11, t["muted"])
        tx += tw + 6
    c.text(cw - 28, ch - 41, f'{p["cta"]} →', "onest-500", 14, t["accent"], "end")
    return c.render()


def card_toolkit(theme: str) -> str:
    c = Card(W, 330, theme, "Toolkit: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in TOOLKIT))
    t = c.t
    frame(c)
    y = 58
    for label, items in TOOLKIT:
        c.text(40, y + 5, label, "mono", 11, t["accent"], tracking=0.14)
        x = 168
        for it in items:
            w = text_width(it, "onest-500", 14) + 28
            c.raw(f'<rect x="{x:.0f}" y="{y - 16}" width="{w:.0f}" height="32" rx="16" fill="{t["raised"]}" stroke="{t["border"]}"/>')
            c.text(x + 14, y + 5, it, "onest-500", 14)
            x += w + 8
        y += 54
    uri, sw, sh = sticker("think", 150)
    float_anim(c, "fl", amp=4, dur=5.5)
    c.raw(f'<image class="fl" x="{W - sw - 26}" y="{330 - sh - 18}" width="{sw}" height="{sh}" href="{uri}"/>')
    return c.render()


def card_field(theme: str, s: dict) -> str:
    c = Card(W, 340, theme, "GitHub stats for nikhilrana2715")
    t = c.t
    frame(c)
    # --- ID badge (left)
    bx, by, bw, bh = 36, 36, 236, 268
    c.raw(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="16" fill="{t["raised"]}" stroke="{t["border"]}"/>')
    c.raw(f'<rect x="{bx + bw / 2 - 26}" y="{by + 14}" width="52" height="8" rx="4" fill="{t["border"]}"/>')
    c.raw(f'<rect x="{bx + 18}" y="{by + 36}" width="{bw - 36}" height="132" rx="10" fill="{t["accent"]}" opacity=".16"/>')
    uri, sw, sh = sticker("wink", 128)
    c.raw(f'<image x="{bx + (bw - sw) / 2}" y="{by + 38}" width="{sw}" height="{sh}" href="{uri}"/>')
    c.text(bx + 18, by + 200, "Nikhil Rana", "onest-700", 20, tracking=-0.02)
    c.text(bx + 18, by + 222, f"@{USER}", "mono", 12, t["muted"])
    c.text(bx + 18, by + 250, "DEV ID", "mono", 10, t["muted"], tracking=0.14)
    c.text(bx + bw - 18, by + 250, "#2715 · RANCHI", "mono", 10, t["accent"], "end", tracking=0.08)
    # --- numbers (right)
    nums = [("Contributions", s["contrib"] if s["contrib"] is not None else "—", "last 12 months"),
            ("Public repos", s["repos"], "and counting"),
            ("Live demos", s["live"], "click & play"),
            ("Stars earned", s["stars"], "thank you")]
    gx, gy = 304, 36
    cw_, chh = 242, 96
    for i, (lab, val, sub) in enumerate(nums):
        x = gx + (i % 2) * (cw_ + 14)
        y = gy + (i // 2) * (chh + 12)
        c.raw(f'<rect x="{x}" y="{y}" width="{cw_}" height="{chh}" rx="14" fill="{t["raised"]}" stroke="{t["border"]}"/>')
        c.text(x + 20, y + 30, lab, "mono", 11, t["muted"], tracking=0.1, upper=True)
        c.text(x + 18, y + 74, f"{val:,}" if isinstance(val, int) else str(val), "onest-700", 38, tracking=-0.03)
        c.text(x + cw_ - 18, y + 74, sub, "onest-400", 12, t["muted"], "end")
    # --- language bar
    ly = gy + 2 * (chh + 12) + 12
    total = sum(n for _, n in s["langs"]) or 1
    palette = [t["accent"], t["text"], t["muted"], t["ok"], "#C9A227"]
    c.text(gx, ly + 4, "Most used languages", "mono", 11, t["muted"], tracking=0.1, upper=True)
    x, barw = gx, 2 * cw_ + 14
    c.defs.append(f'<clipPath id="bar"><rect x="{gx}" y="{ly + 16}" width="{barw}" height="10" rx="5"/></clipPath>')
    segs = []
    for i, (lang, n) in enumerate(s["langs"]):
        w = barw * n / total
        segs.append(f'<rect x="{x:.1f}" y="{ly + 16}" width="{w:.1f}" height="10" fill="{palette[i % 5]}"/>')
        x += w
    c.raw(f'<g clip-path="url(#bar)">{"".join(segs)}</g>')
    x = gx
    for i, (lang, n) in enumerate(s["langs"][:4]):
        lab = f"{lang} {round(100 * n / total)}%"
        c.raw(f'<circle cx="{x + 4}" cy="{ly + 42}" r="4" fill="{palette[i % 5]}"/>')
        c.text(x + 14, ly + 46, lab, "onest-400", 12, t["muted"])
        x += text_width(lab, "onest-400", 12) + 34
    return c.render()


def card_contact(theme: str) -> str:
    c = Card(W, 230, theme, "Contact Nikhil Rana — portfolio and LinkedIn")
    t = c.t
    # always-dark CTA block, like the portfolio footer
    ink, paper = ("#0F0E0D", "#EDE7E1") if theme == "dark" else ("#1A1818", "#EDE7E1")
    c.raw(f'<rect x=".5" y=".5" width="{W - 1}" height="229" rx="24" fill="{ink}" stroke="{t["border"]}"/>')
    eyebrow(c, 44, 58, "05 — Contact")
    c.text(44, 112, "Got a project, a role", "onest-700", 40, paper, tracking=-0.03)
    c.text(44, 158, "or a game idea?", "onest-700", 40, t["accent"] if theme == "dark" else "#D07A4C", tracking=-0.03)
    c.text(44, 198, "nikhil-rana-portfolio.vercel.app  →", "mono", 13, "#A39C97", tracking=0.02)
    uri, sw, sh = sticker("peace", 176)
    float_anim(c, "fl", amp=6, dur=4.6, rot=-2)
    c.raw(f'<image class="fl" x="{W - sw - 56}" y="{230 - sh - 20}" width="{sw}" height="{sh}" href="{uri}"/>')
    return c.render()


# ---------------------------------------------------------------- main
def main():
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    OUT.mkdir(parents=True, exist_ok=True)
    stats = fetch_stats()
    for theme in THEMES:
        files = {
            "hero": card_hero(theme),
            "about": card_about(theme),
            "toolkit": card_toolkit(theme),
            "field": card_field(theme, stats),
            "contact": card_contact(theme),
            **{f"sec-{k}": card_section(theme, k) for k in SECTIONS},
            **{f"p-{p['slug']}": card_project(theme, p) for p in PROJECTS},
        }
        for name, svg in files.items():
            (OUT / f"{name}-{theme}.svg").write_text(svg, encoding="utf-8")
    print("stats:", stats)
    for f in sorted(OUT.glob("*.svg")):
        print(f"{f.stat().st_size / 1024:7.1f} KB  {f.name}")


if __name__ == "__main__":
    main()
