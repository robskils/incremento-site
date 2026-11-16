#!/usr/bin/env python3
"""
pull_posts.py - the bridge between the Incremento admin's blog queue and this
site, in all five languages.

Robin: "incremento writes in english but translates into all the languages of
the blog - several." Five: en, pt, es, fr, de. Each gets its own page at its
own localised slug - /pt/blog/seo-lisboa/ beside /blog/seo-lisbon/ - a card on
its own index, and an hreflang set pointing at the other four. That is how the
sixteen posts already here are built, and this writes new ones the same way.

The writing and the translating happen in the admin worker, which holds the
queue and calls Claude. This runs in GitHub Actions - the thing allowed to
push - and does only what the worker cannot: commit the pages.

It never overwrites a page already on disk. A page edited here by hand is the
better copy by definition, and a job that runs unattended twice a week must
not be able to undo an edit.

A post whose translations have not arrived yet gets the languages it has.
The rest appear on a later run, because the worker keeps trying - so a German
failure on Tuesday costs a German page until Wednesday, not an English one.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

FEED = os.environ.get("BLOG_FEED", "https://enquiries.incremento.eu/api/blog-feed")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://incremento.eu"

# Language -> where its posts live, which index lists them, and an existing
# post to use as the skeleton so head, nav and footer are never stale here.
LANGS = {
    "en": {"dir": "blog",    "prefix": "/blog/",    "skeleton": "blog/seo-lisbon/index.html",
           "html_lang": "en", "read": "min read"},
    "pt": {"dir": "pt/blog", "prefix": "/pt/blog/", "skeleton": "pt/blog/seo-lisboa/index.html",
           "html_lang": "pt", "read": "min de leitura"},
    "es": {"dir": "es/blog", "prefix": "/es/blog/", "skeleton": "es/blog/seo-lisboa/index.html",
           "html_lang": "es", "read": "min de lectura"},
    "fr": {"dir": "fr/blog", "prefix": "/fr/blog/", "skeleton": "fr/blog/seo-lisbonne/index.html",
           "html_lang": "fr", "read": "min de lecture"},
    "de": {"dir": "de/blog", "prefix": "/de/blog/", "skeleton": "de/blog/seo-lissabon/index.html",
           "html_lang": "de", "read": "Min. Lesezeit"},
}

BODY_START = '<div class="blog-post-body">'
BODY_END = "<!-- CTA -->"


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fetch():
    req = urllib.request.Request(FEED, headers={"User-Agent": "incremento-site-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")).get("posts", [])


def read_minutes(html):
    return max(3, round(len(re.sub(r"<[^>]+>", " ", html or "").split()) / 220))


def versions(post):
    """Every language this post exists in, as {code: {title, slug, meta, body}}.

    The English is the post itself; the rest come from the worker's
    translations. A language missing simply is not built this time."""
    out = {"en": {"title": post["title"], "slug": post["slug"],
                  "meta": post.get("meta_desc") or "", "body": post.get("body") or ""}}
    for code, v in (post.get("langs") or {}).items():
        if code in LANGS and v and v.get("body") and v.get("slug"):
            out[code] = {"title": v.get("title") or post["title"], "slug": v["slug"],
                         "meta": v.get("meta") or "", "body": v["body"]}
    return out


def alternates(vers):
    """The hreflang block: every language that exists, plus x-default on the
    English, which is the source. Claiming one that is not there would send a
    search engine to a 404."""
    rows = [f'<link rel="alternate" hreflang="{c}" href="{SITE}{LANGS[c]["prefix"]}{v["slug"]}/">'
            for c, v in vers.items()]
    if "en" in vers:
        rows.append(f'<link rel="alternate" hreflang="x-default" '
                    f'href="{SITE}/blog/{vers["en"]["slug"]}/">')
    return "\n".join(rows)


def build_page(skeleton, code, vers, when):
    cfg = LANGS[code]
    v = vers[code]
    url = f'{SITE}{cfg["prefix"]}{v["slug"]}/'
    s = skeleton

    s = re.sub(r"<title>.*?</title>",
               lambda _: f'<title>{esc(v["title"])} | Incremento</title>',
               s, count=1, flags=re.S)
    for pat in (r'(<meta name="description" content=")[^"]*(")',
                r'(<meta property="og:description" content=")[^"]*(")',
                r'(<meta name="twitter:description" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + esc(v["meta"]) + m.group(2), s, count=1)
    for pat in (r'(<meta property="og:title" content=")[^"]*(")',
                r'(<meta name="twitter:title" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + esc(v["title"]) + m.group(2), s, count=1)
    for pat in (r'(<link rel="canonical" href=")[^"]*(")',
                r'(<meta property="og:url" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + url + m.group(2), s, count=1)

    # Replace the whole alternates block rather than editing each line, since
    # which languages exist differs per post.
    block = alternates(vers)
    s = re.sub(r'(?:\s*<link rel="alternate" hreflang="[^"]*"[^>]*>)+',
               lambda _: "\n" + block, s, count=1)

    def fix_ld(m):
        try:
            data = json.loads(m.group(1))
        except Exception:
            return m.group(0)

        def walk(n):
            if isinstance(n, dict):
                if "headline" in n:
                    n["headline"] = v["title"]
                if "description" in n:
                    n["description"] = v["meta"]
                for k in ("datePublished", "dateModified"):
                    if k in n:
                        n[k] = when
                if n.get("@type") in ("BlogPosting", "Article", "WebPage"):
                    n["url"] = url
                    if "mainEntityOfPage" in n:
                        n["mainEntityOfPage"] = url
                if "inLanguage" in n:
                    n["inLanguage"] = code
                for x in n.values():
                    walk(x)
            elif isinstance(n, list):
                for x in n:
                    walk(x)

        walk(data)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"

    s = re.sub(r'<script type="application/ld\+json">(.*?)</script>', fix_ld, s,
               count=1, flags=re.S)

    s = re.sub(r"(<h1[^>]*>).*?(</h1>)",
               lambda m: m.group(1) + esc(v["title"]) + m.group(2), s, count=1, flags=re.S)

    # Date and reading time in the post header, in that language's words.
    nice = datetime.strptime(when, "%Y-%m-%d").strftime("%d %b %Y")
    s = re.sub(r'(<span class="blog-meta-date">[\s\S]*?</svg>\s*)[^<]*(\s*</span>)',
               lambda m: m.group(1) + nice + m.group(2), s, count=1)
    s = re.sub(r'(<span class="blog-meta-read">[\s\S]*?</svg>\s*)[^<]*(\s*</span>)',
               lambda m: m.group(1) + f'{read_minutes(v["body"])} {cfg["read"]}' + m.group(2),
               s, count=1)

    a, b = s.find(BODY_START), s.find(BODY_END)
    if a < 0 or b < 0:
        raise RuntimeError(f"could not find where the words go in the {code} skeleton")
    a += len(BODY_START)
    return s[:a] + "\n" + v["body"] + "\n\n    </div>\n\n    " + s[b:]


def add_to_index(index_html, code, v, when):
    cfg = LANGS[code]
    href = f'{cfg["prefix"]}{v["slug"]}/'
    if f'href="{href}"' in index_html:
        return index_html
    nice = datetime.strptime(when, "%Y-%m-%d").strftime("%d %b %Y")
    card = (
        '<article class="blog-card">\n'
        '        <span class="blog-tag">Incremento</span>\n'
        f'        <h3 class="mt-3"><a href="{href}">{esc(v["title"])}</a></h3>\n'
        f'        <p class="mt-3 text-muted">{esc(v["meta"])}</p>\n'
        '        <div class="blog-meta mt-4">\n'
        f'          <span class="blog-meta-date">{nice}</span>\n'
        f'          <span class="blog-meta-read">{read_minutes(v["body"])} {cfg["read"]}</span>\n'
        '        </div>\n'
        '      </article>\n\n      '
    )
    m = re.search(r'<article class="blog-card"', index_html)
    if not m:
        print(f"  ! {code}: could not find where the cards go; index left alone",
              file=sys.stderr)
        return index_html
    return index_html[:m.start()] + card + index_html[m.start():]


def main():
    try:
        posts = fetch()
    except Exception as e:
        print(f"could not read the feed: {e}", file=sys.stderr)
        return 1
    if not posts:
        print("nothing written yet; nothing to publish")
        return 0

    skeletons, indexes = {}, {}
    for code, cfg in LANGS.items():
        sk = os.path.join(ROOT, cfg["skeleton"])
        ix = os.path.join(ROOT, cfg["dir"], "index.html")
        if not os.path.exists(sk) or not os.path.exists(ix):
            print(f"  ! {code}: no skeleton or index; that language is skipped",
                  file=sys.stderr)
            continue
        skeletons[code] = open(sk, encoding="utf-8").read()
        indexes[code] = open(ix, encoding="utf-8").read()
    before = dict(indexes)
    added = []

    # Oldest first, so the newest ends up at the top of each index.
    for post in sorted(posts, key=lambda p: p.get("published_at") or p.get("written_at") or ""):
        if not (post.get("slug") and post.get("body")):
            continue
        vers = versions(post)
        when = (post.get("published_at") or post.get("written_at")
                or datetime.now(timezone.utc).isoformat())[:10]

        for code, v in vers.items():
            if code not in skeletons:
                continue
            folder = os.path.join(ROOT, LANGS[code]["dir"], v["slug"])
            page = os.path.join(folder, "index.html")
            if os.path.exists(page):
                continue                  # already here, and the copy on disk wins
            os.makedirs(folder, exist_ok=True)
            with open(page, "w", encoding="utf-8") as f:
                f.write(build_page(skeletons[code], code, vers, when))
            indexes[code] = add_to_index(indexes[code], code, v, when)
            added.append(f'{LANGS[code]["prefix"]}{v["slug"]}/')
            print(f'  + {LANGS[code]["prefix"]}{v["slug"]}/')

    for code, html in indexes.items():
        if html != before.get(code):
            with open(os.path.join(ROOT, LANGS[code]["dir"], "index.html"), "w",
                      encoding="utf-8") as f:
                f.write(html)

    print(f"{len(added)} new page{'' if len(added) == 1 else 's'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
