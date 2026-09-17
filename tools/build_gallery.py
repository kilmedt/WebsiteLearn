#!/usr/bin/env python
"""Build the "Imgs" gallery section of Kilmedt's Website.

Source of truth is the folder tree under images/:

    images/AIworks/   -> AI generated works   (rendered with an "AI" badge)
    images/HMworks/   -> hand-made works      (no badge)

There is a single flat gallery — the folders decide the ordering and whether
the AI badge is shown, but they are never rendered as visible categories.

For every source image the script writes size-optimised derivatives into
img/gallery/ and then regenerates gallery/gallery.html from them.

Run it again after dropping new images into either folder:

    python tools/build_gallery.py

Requires Pillow (`pip install Pillow`). Re-encoding is skipped when a
derivative is already newer than its source, so repeat runs are cheap.
Pass --force to rebuild every derivative regardless.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from html import escape

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: pip install Pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (folder under images/, carries the "AI" badge). Images are listed in this
# order, then by file name — reorder the list to change the gallery order.
SOURCES = [
    ("AIworks", True),
    ("HMworks", False),
]

SOURCE_ROOT = os.path.join(ROOT, "images")
DERIVED_DIR = os.path.join(ROOT, "img", "gallery")
PAGE_DIR = os.path.join(ROOT, "gallery")
PAGE_PATH = os.path.join(PAGE_DIR, "gallery.html")

THUMB_W = 640
FULL_W = 1600
WEBP_Q = 82
JPEG_Q = 85
EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Where the lightbox scrim / close button returns to.
CLOSE_ANCHOR = "gallery"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return s.strip("-") or "image"


def derivatives(src: str, slug: str, force: bool) -> dict:
    """Write <slug>-thumb/-full in webp+jpg and return their metadata."""
    meta = {"slug": slug}
    for label, width in (("thumb", THUMB_W), ("full", FULL_W)):
        paths = {
            "webp": os.path.join(DERIVED_DIR, f"{slug}-{label}.webp"),
            "jpg": os.path.join(DERIVED_DIR, f"{slug}-{label}.jpg"),
        }
        if not force and all(
            os.path.exists(p) and os.path.getmtime(p) >= os.path.getmtime(src)
            for p in paths.values()
        ):
            with Image.open(paths["jpg"]) as im:
                meta[label] = {"w": im.width, "h": im.height}
            continue

        # convert("RGB") drops any embedded PNG text chunks, which for AI
        # exports often carry the full generation prompt and seed.
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > width:
                height = max(1, round(im.height * width / im.width))
                out = im.resize((width, height), Image.LANCZOS)
            else:
                out = im
            meta[label] = {"w": out.width, "h": out.height}
            out.save(paths["webp"], "WEBP", quality=WEBP_Q, method=6)
            out.save(paths["jpg"], "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
    return meta


def collect(force: bool) -> list[dict]:
    items: list[dict] = []
    for folder, is_ai in SOURCES:
        src_dir = os.path.join(SOURCE_ROOT, folder)
        if not os.path.isdir(src_dir):
            continue
        for name in sorted(os.listdir(src_dir), key=str.lower):
            ext = os.path.splitext(name)[1].lower()
            path = os.path.join(src_dir, name)
            if not os.path.isfile(path) or ext not in EXTS:
                continue
            stem = os.path.splitext(name)[0]
            # Folder-prefixed so the two folders can hold same-named files
            # without their derivatives colliding.
            slug = f"{slugify(folder)}-{slugify(stem)}"
            meta = derivatives(path, slug, force)
            meta.update(
                {
                    "name": stem,
                    "anchor": f"shot-{slug}",
                    "alt": f"{'AI 作品' if is_ai else '手工作品'}：{stem}",
                    "is_ai": is_ai,
                    "folder": folder,
                    "kb": round(os.path.getsize(path) / 1024),
                }
            )
            items.append(meta)
    return items


SHOT = """\
                    <li class="shot">
                        <a class="shot__link" href="#{anchor}">
                            <span class="shot__frame">
                                <picture>
                                    <source srcset="../img/gallery/{slug}-thumb.webp" type="image/webp">
                                    <img src="../img/gallery/{slug}-thumb.jpg" alt="{alt}"
                                        width="{tw}" height="{th}" loading="lazy" decoding="async">
                                </picture>
{badge}                            </span>
                            <span class="shot__meta">
                                <span class="shot__name">{name}</span>
                                <span class="shot__zoom" aria-hidden="true">放大</span>
                            </span>
                        </a>
                    </li>
"""

BADGE = '                                <span class="badge badge--ai">AI</span>\n'
BADGE_CAPTION = '                    <span class="badge badge--ai">AI</span>\n'

LIGHTBOX = """\
        <div class="lightbox" id="{anchor}">
            <a class="lightbox__scrim" href="#{close}" aria-label="关闭"></a>
            <figure class="lightbox__figure">
                <picture>
                    <source srcset="../img/gallery/{slug}-full.webp" type="image/webp">
                    <img src="../img/gallery/{slug}-full.jpg" alt="{alt}"
                        width="{fw}" height="{fh}" decoding="async">
                </picture>
                <figcaption class="lightbox__caption">
{badge}                    <span class="lightbox__name">{name}</span>
                    <a class="lightbox__action" href="../img/gallery/{slug}-full.jpg"
                        target="_blank" rel="noopener noreferrer">在新标签打开</a>
                    <a class="lightbox__close" href="#{close}" aria-label="关闭大图">&times;</a>
                </figcaption>
            </figure>
        </div>
"""

GRID_OPEN = '            <ul class="gallery__grid">\n'
GRID_CLOSE = "            </ul>\n"

EMPTY = """\
            <p class="gallery__empty">
                还没有图片。把图片放进 <code>images/AIworks/</code> 或
                <code>images/HMworks/</code>，重新生成后就会出现在这里。
            </p>
"""

GENERATED_BY = "<!-- 本文件由 tools/build_gallery.py 生成，请勿手工修改。 -->"

PAGE = """\
<!DOCTYPE html>
<html lang="zh-CN">

<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#cef5ff">
    <meta name="description" content="Kilmedt 的图片作品集。">
    <title>Imgs · Kilmedt's Website</title>

    <link rel="icon" href="../favicons/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" sizes="16x16" href="../favicons/favicon-16x16.png">
    <link rel="icon" type="image/png" sizes="32x32" href="../favicons/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="192x192" href="../favicons/android-chrome-192x192.png">
    <link rel="apple-touch-icon" sizes="180x180" href="../favicons/apple-touch-icon.png">

    <link rel="stylesheet" href="../css/styles.css">
</head>

<body class="page-gallery">
    <header class="app-header">
        <a class="brand" href="../index.html">
            <span class="brand__mark" aria-hidden="true"></span>
            <span>Kilmedt<span class="brand__suffix">'s Website</span></span>
        </a>
        <nav class="app-nav" aria-label="主导航">
            <a href="../index.html">首页</a>
            <a href="../projects/projects.html">Projects</a>
            <a href="gallery.html" aria-current="page">Imgs</a>
        </nav>
    </header>

    <div class="app-body">
        <aside class="profile">
            <picture class="profile__avatar">
                <source srcset="../img/avatar-256.webp" type="image/webp">
                <img src="../img/avatar-256.png" alt="Kilmedt 的头像" width="256" height="256" decoding="async">
            </picture>

            <div class="profile__intro">
                <p class="profile__name">Kilmedt</p>
                <p class="profile__tagline">"kilmedt的website"</p>
                <p class="profile__email"><a href="mailto:kilmedt@163.com">kilmedt@163.com</a></p>
            </div>

            <nav class="profile__links" aria-label="社交链接">
                <a href="https://space.bilibili.com/87122588" target="_blank" rel="noopener noreferrer">
                    <img src="../img/bilibili_icon.png" alt="Bilibili" width="200" height="200">
                </a>
                <a href="https://github.com/Kilmedt" target="_blank" rel="noopener noreferrer">
                    <img src="../img/github_icon.png" alt="GitHub" width="200" height="200">
                </a>
            </nav>
        </aside>

        <main class="panel gallery" id="{close}">
            <h1 class="panel__title">Imgs</h1>
            <p class="panel__lead">{lead}</p>

{grid}
            <a class="back-link" href="../index.html">&larr; 返回首页</a>
        </main>
    </div>

    <footer class="app-footer">
        <p>&copy; {year} Kilmedt</p>
    </footer>

{lightboxes}</body>

</html>
"""

LEAD = (
    '共 {n} 张。带 <span class="badge badge--ai">AI</span> 标记的是 AI 生成的作品。'
)


def render(items: list[dict]) -> str:
    if items:
        grid = GRID_OPEN + "".join(
            SHOT.format(
                anchor=it["anchor"], slug=it["slug"], alt=escape(it["alt"]),
                name=escape(it["name"]),
                tw=it["thumb"]["w"], th=it["thumb"]["h"],
                badge=BADGE if it["is_ai"] else "",
            )
            for it in items
        ) + GRID_CLOSE
        lead = LEAD.format(n=len(items))
    else:
        grid = EMPTY
        lead = "还没有图片。"

    lightboxes = "".join(
        LIGHTBOX.format(
            anchor=it["anchor"], close=CLOSE_ANCHOR, slug=it["slug"],
            alt=escape(it["alt"]), name=escape(it["name"]),
            fw=it["full"]["w"], fh=it["full"]["h"],
            badge=BADGE_CAPTION if it["is_ai"] else "",
        )
        for it in items
    )

    html = PAGE.format(
        close=CLOSE_ANCHOR, lead=lead, grid=grid,
        lightboxes=lightboxes, year=date.today().year,
    )
    # The "generated" banner goes just after the doctype, never before it.
    return html.replace(
        "<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + GENERATED_BY + "\n", 1
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="rebuild every derivative")
    args = ap.parse_args()

    os.makedirs(DERIVED_DIR, exist_ok=True)
    os.makedirs(PAGE_DIR, exist_ok=True)

    items = collect(args.force)
    ai = sum(1 for it in items if it["is_ai"])
    print(f"{len(items)} image(s) total, {ai} with the AI badge")
    for it in items:
        thumb = os.path.join(DERIVED_DIR, f"{it['slug']}-thumb.webp")
        full = os.path.join(DERIVED_DIR, f"{it['slug']}-full.webp")
        tag = "AI  " if it["is_ai"] else "    "
        print(
            f"   {tag}{it['folder']}/{it['name']:<20} source {it['kb']:>6} KB -> "
            f"thumb {os.path.getsize(thumb)/1024:6.1f} KB, "
            f"full {os.path.getsize(full)/1024:6.1f} KB"
        )

    html = render(items)
    with open(PAGE_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print(f"\n-> {os.path.relpath(PAGE_PATH, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
