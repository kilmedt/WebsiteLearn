#!/usr/bin/env python
"""Build the "Imgs" gallery section of Kilmedt's Website.

Source of truth is the folder tree under images/:

    images/AIworks/   -> AI generated works   (rendered with an "AI" badge)
    images/HMworks/   -> hand-made works      (no badge)

There is a single flat gallery — the folders decide the ordering and whether
the AI badge is shown, but they are never rendered as visible categories.

For every source image the script writes a grid thumbnail into img/gallery/
and then regenerates gallery/gallery.html from them. The enlarged lightbox view
shows the original image file itself, so no large derivative is produced. The
newest image's thumbnail is also published as img/gallery/cover-thumb.*, which
is what the homepage Imgs tile shows — so the cover tracks your latest work
with no manual step.

Because the lightbox points at the originals, images/ must be deployed with the
site. See .gitignore for the size trade-off and the lighter alternative.

Run it again after dropping new images into either folder:

    python tools/build_gallery.py

Requires Pillow (`pip install Pillow`). Re-encoding is skipped when a
derivative is already newer than its source, so repeat runs are cheap.
Pass --force to rebuild every derivative regardless.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from html import escape
from urllib.parse import quote

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
CSS_PATH = os.path.join(PAGE_DIR, "gallery.css")

# Records when each image was first seen here, so "upload time" is a real
# fact rather than a guess from file timestamps. See load_history().
HISTORY_PATH = os.path.join(HERE, "gallery-history.json")

THUMB_W = 640
WEBP_Q = 82
JPEG_Q = 85
EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

# Where the lightbox scrim / close button returns to.
CLOSE_ANCHOR = "gallery"

# The homepage Imgs tile cover mirrors the most recently uploaded image, so
# dropping in a new work updates the cover with no manual step. Upload order is
# tracked in tools/gallery-history.json; see load_history(). Point this at a
# file name to pin one image instead, e.g. COVER_OVERRIDE = "Anima_00182_.png".
COVER_OVERRIDE = None

# Stable file name the cover is published under, so index.html never has to
# reference a specific work (a hard-coded path is what broke img/0.jpg before).
COVER_STEM = "cover"


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return s.strip("-") or "image"


def derivatives(src: str, slug: str, force: bool) -> dict:
    """Write the grid thumbnail and return thumbnail + source metadata.

    The enlarged view shows the original file itself, so no larger derivative
    is produced — only the small grid thumbnail the page loads up front.
    """
    meta = {"slug": slug}
    path = os.path.join(DERIVED_DIR, f"{slug}-thumb.webp")
    path_jpg = os.path.join(DERIVED_DIR, f"{slug}-thumb.jpg")

    # convert("RGB") drops any embedded PNG text chunks, which for AI exports
    # often carry the full generation prompt and seed. The original keeps them,
    # so those stay out of the page unless the visitor opens the file directly.
    with Image.open(src) as im:
        meta["src"] = {"w": im.width, "h": im.height}
        im = im.convert("RGB")
        if im.width > THUMB_W:
            thumb = im.resize(
                (THUMB_W, max(1, round(im.height * THUMB_W / im.width))), Image.LANCZOS
            )
        else:
            thumb = im
        meta["thumb"] = {"w": thumb.width, "h": thumb.height}
        if force or not (
            os.path.exists(path)
            and os.path.exists(path_jpg)
            and os.path.getmtime(path) >= os.path.getmtime(src)
        ):
            thumb.save(path, "WEBP", quality=WEBP_Q, method=6)
            thumb.save(path_jpg, "JPEG", quality=JPEG_Q, optimize=True, progressive=True)
    return meta


def collect(force: bool, history: dict[str, float]) -> list[dict]:
    """Scan the source folders and record first-seen times into `history`.

    On the very first run (empty history) existing images are seeded from their
    file creation times, so a gallery that predates the history file keeps a
    sensible order instead of every image looking like it arrived just now.
    """
    seeding = not history
    now = datetime.now().timestamp()
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

            key = f"{folder}/{name}"
            if key in history:
                added, origin = history[key], "recorded"
            elif seeding:
                added, origin = added_time(path), "seeded"
            else:
                added, origin = now, "new"
            history[key] = added

            meta.update(
                {
                    "name": stem,
                    "file": name,
                    "added": added,
                    "origin": origin,
                    "mtime": os.path.getmtime(path),
                    "anchor": f"shot-{slug}",
                    "alt": f"{'AI 作品' if is_ai else '手工作品'}：{stem}",
                    # Source names may hold spaces or CJK; percent-encode before
                    # putting them in a CSS url() or an href.
                    "url": quote(f"../images/{folder}/{name}", safe="/"),
                    "is_ai": is_ai,
                    "folder": folder,
                    "kb": round(os.path.getsize(path) / 1024),
                }
            )
            items.append(meta)
    return items


def added_time(path: str) -> float:
    """Fallback "when did this land here", used only to seed the history.

    A file's mtime is when its *content* was made, which for a downloaded or
    exported image can be months earlier than the day you put it here — the
    tool's timestamp travels with the file. The creation time is what a *copy*
    records, so it is the closest thing to an upload time available from the
    filesystem alone. It is only a fallback: moving a file preserves its
    original creation time, which is why tools/gallery-history.json is the
    real record once the script has seen an image at least once.
    """
    st = os.stat(path)
    return getattr(st, "st_birthtime", st.st_ctime)


def load_history() -> dict[str, float]:
    """Map "folder/file" -> epoch seconds when the script first saw it.

    Written as readable ISO timestamps, so the file doubles as a record of the
    upload order. Missing or unreadable history is not fatal: the next run
    re-seeds from file creation times.
    """
    if not os.path.exists(HISTORY_PATH):
        return {}
    try:
        with open(HISTORY_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {k: datetime.fromisoformat(v).timestamp() for k, v in raw.items()}
    except (ValueError, TypeError, OSError) as exc:
        print(
            f"!! 无法读取 {os.path.relpath(HISTORY_PATH, ROOT)}（{exc}）；"
            "本次改用文件创建时间重新播种",
            file=sys.stderr,
        )
        return {}


def save_history(history: dict[str, float]) -> None:
    payload = {
        key: datetime.fromtimestamp(ts).isoformat(timespec="seconds")
        for key, ts in sorted(history.items(), key=lambda kv: kv[1])
    }
    with open(HISTORY_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def pick_cover(items: list[dict]) -> dict | None:
    """The most recently uploaded work.

    Ties — several images added in the same run — fall back to the file's own
    timestamp and then to gallery order, so the result is always stable.
    """
    if not items:
        return None
    if COVER_OVERRIDE:
        for it in items:
            if COVER_OVERRIDE in (it["file"], it["name"]):
                return it
        print(
            f"!! COVER_OVERRIDE={COVER_OVERRIDE!r} matched no image; "
            "falling back to the newest one",
            file=sys.stderr,
        )
    return max(
        enumerate(items),
        key=lambda pair: (pair[1]["added"], pair[1]["mtime"], pair[0]),
    )[1]


def write_cover(item: dict) -> list[str]:
    """Publish the chosen work's thumbnail under a stable cover file name."""
    written = []
    for fmt in ("webp", "jpg"):
        src = os.path.join(DERIVED_DIR, f"{item['slug']}-thumb.{fmt}")
        dst = os.path.join(DERIVED_DIR, f"{COVER_STEM}-thumb.{fmt}")
        shutil.copyfile(src, dst)
        written.append(dst)
    return written


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
                <div class="lightbox__img" role="img" aria-label="{alt}"></div>
                <figcaption class="lightbox__caption">
{badge}                    <span class="lightbox__name">{name}</span>
                    <a class="lightbox__action" href="{url}"
                        target="_blank" rel="noopener noreferrer">打开原图</a>
                    <a class="lightbox__close" href="#{close}" aria-label="关闭大图">&times;</a>
                </figcaption>
            </figure>
        </div>
"""

# Per-image rules. The background-image only matches while the lightbox is
# :target, so an original is fetched when — and only when — it is opened.
# An <img src> would pull every original on page load.
LIGHTBOX_CSS = """\
#{anchor} {{
    --ar: {ar};
}}

#{anchor}:target .lightbox__img {{
    background-image: url("{url}");
}}
"""

CSS_HEADER = """\
/* 本文件由 tools/build_gallery.py 生成，请勿手工修改。
   每个大图的原图地址都写在 :target 规则里，因此只有真正打开某一张时
   浏览器才会去下载那张原图。 */
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
    <link rel="stylesheet" href="gallery.css">
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
            anchor=it["anchor"], close=CLOSE_ANCHOR, url=it["url"],
            alt=escape(it["alt"]), name=escape(it["name"]),
            badge=BADGE_CAPTION if it["is_ai"] else "",
        )
        for it in items
    )

    rules = "".join(
        LIGHTBOX_CSS.format(
            anchor=it["anchor"],
            ar=round(it["src"]["w"] / it["src"]["h"], 7),
            url=it["url"],
        )
        for it in items
    )
    with open(CSS_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(CSS_HEADER + (rules or "/* 暂无图片 */\n"))

    html = PAGE.format(
        close=CLOSE_ANCHOR, lead=lead, grid=grid,
        lightboxes=lightboxes, year=date.today().year,
    )
    # The "generated" banner goes just after the doctype, never before it.
    return html.replace(
        "<!DOCTYPE html>\n", "<!DOCTYPE html>\n" + GENERATED_BY + "\n", 1
    )


def sweep_orphans(items: list[dict]) -> list[str]:
    """Delete derivatives left behind by removed images or older layouts."""
    keep = {f"{COVER_STEM}-thumb.webp", f"{COVER_STEM}-thumb.jpg"}
    for it in items:
        keep |= {f"{it['slug']}-thumb.webp", f"{it['slug']}-thumb.jpg"}
    removed = []
    for name in sorted(os.listdir(DERIVED_DIR)):
        path = os.path.join(DERIVED_DIR, name)
        if os.path.isfile(path) and name not in keep:
            os.remove(path)
            removed.append(name)
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="rebuild every derivative")
    args = ap.parse_args()

    os.makedirs(DERIVED_DIR, exist_ok=True)
    os.makedirs(PAGE_DIR, exist_ok=True)

    history = load_history()
    items = collect(args.force, history)
    ai = sum(1 for it in items if it["is_ai"])
    print(f"{len(items)} image(s) total, {ai} with the AI badge")
    for it in items:
        thumb = os.path.join(DERIVED_DIR, f"{it['slug']}-thumb.webp")
        tag = "AI  " if it["is_ai"] else "    "
        origin = {"new": "新的", "seeded": "补录", "recorded": "已记录"}[it["origin"]]
        print(
            f"   {tag}{it['folder']}/{it['name']:<20} "
            f"{it['src']['w']}x{it['src']['h']} {it['kb']:>6} KB original -> "
            f"grid thumb {os.path.getsize(thumb)/1024:6.1f} KB  "
            f"[上传时间 {datetime.fromtimestamp(it['added']):%Y-%m-%d %H:%M} {origin}]"
        )

    # Drop history entries for images that no longer exist.
    for gone in sorted(set(history) - {f"{it['folder']}/{it['file']}" for it in items}):
        del history[gone]
        print(f"   forgot removed image: {gone}")
    if items:
        save_history(history)

    for name in sweep_orphans(items):
        print(f"   removed stale derivative: {name}")

    html = render(items)
    with open(PAGE_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print(f"\n-> {os.path.relpath(PAGE_PATH, ROOT)}")

    cover = pick_cover(items)
    if cover is None:
        print(
            "!! no images found, so img/gallery/cover-thumb.* was not written.\n"
            "   index.html points at that file, so the Imgs tile will show a\n"
            "   broken cover until at least one image exists.",
            file=sys.stderr,
        )
    else:
        write_cover(cover)
        print(
            f"-> homepage cover = {cover['folder']}/{cover['file']}\n"
            f"   上传时间 {datetime.fromtimestamp(cover['added']):%Y-%m-%d %H:%M}"
            f"（{cover['origin']}），文件自身时间 "
            f"{datetime.fromtimestamp(cover['mtime']):%Y-%m-%d %H:%M}\n"
            f"   published as img/gallery/{COVER_STEM}-thumb.webp|.jpg"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
