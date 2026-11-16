#!/usr/bin/env python3
"""
write_post.py - writes the next blog post and puts it on the site.

Robin, 16 November 2026: "we'd like to get the blog automation going for some
of the other properties".

HOW THIS DIFFERS FROM THE LISBON SINTRA TOURS ONE. That site's posts are
written in the CRM, which holds the queue and serves them at /api/blog-feed;
a GitHub Action only carries them the last step. These sites have no CRM, so
there is nothing to pull from - this script does the writing as well as the
publishing, and the queue is a text file in the repo.

That makes it self-contained: one script, one workflow, one API key, and a
topics file anybody can edit. Nothing here depends on another repository or
on a service staying up.

WHAT IT DOES, every Tuesday and Friday morning
  1. Reads topics.md and takes the first line not yet marked done.
  2. Asks Claude for the post - title, slug, meta description, body HTML.
  3. Builds the page from an existing post, so the head, nav and footer are
     whatever the site currently has rather than a copy going stale in here.
  4. Adds a card to the index, newest first.
  5. Ticks the topic off.

It never overwrites a post already on disk: a page edited by hand is the
better copy by definition, and a job running unattended twice a week must not
be able to undo an edit.

If anything is missing - no API key, no topics left, no skeleton - it says so
and exits 0. A blog that skips a Tuesday is fine; a workflow that fails loudly
every Tuesday gets muted, and then nobody notices the day it matters.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = "claude-opus-5-5"
API = "https://api.anthropic.com/v1/messages"


# ── SITE CONFIG ────────────────────────────────────────────────────────────
# One entry per site. `site.json` beside this file picks which one and may
# override any field, so the same script runs unchanged in every repo.
def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site.json")
    if not os.path.exists(path):
        die(f"no site.json beside {os.path.basename(__file__)}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def die(msg, code=0):
    """Say why nothing happened, and do not fail the run for it."""
    print(f"nothing published: {msg}", file=sys.stderr)
    sys.exit(code)


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ── THE QUEUE ──────────────────────────────────────────────────────────────
# topics.md is a plain list. A line starting "- [ ] " is waiting, "- [x] " is
# done. Anything else - headings, blank lines, notes to yourself - is ignored,
# so the file stays something a person wants to open.
TODO = re.compile(r"^-\s*\[\s*\]\s*(.+?)\s*$")


def next_topic(path):
    if not os.path.exists(path):
        return None, None
    lines = open(path, encoding="utf-8").read().split("\n")
    for i, line in enumerate(lines):
        m = TODO.match(line)
        if m:
            return m.group(1), (lines, i)
    return None, None


def tick_off(path, state, slug):
    lines, i = state
    done = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines[i] = lines[i].replace("- [ ]", "- [x]", 1) + f"  _({done} - /{slug}/)_"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── THE WRITING ────────────────────────────────────────────────────────────
def ask_claude(cfg, topic, existing):
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        die("ANTHROPIC_API_KEY is not set on this repository")

    prompt = f"""{cfg['brief']}

Write one post for the subject below. Return ONLY a JSON object, no commentary
and no code fence, with exactly these keys:

  "title"  - the headline. Plain text. No site name, no pipe, no colon-subtitle
             unless the subject genuinely needs one.
  "slug"   - lowercase, hyphens, no accents, no stop words you can lose. {cfg['slug_note']}
  "desc"   - one sentence of 140-160 characters for the meta description. It is
             a description, not a slogan.
  "body"   - the post as HTML. <p>, <h2>, <h3>, <ul>/<li>, <strong>, <a href>.
             No <h1> - the page supplies it. No <html>, <head>, <body>, no
             inline styles, no classes. 800-1200 words.

SUBJECT: {topic}

Posts already on the site, so you do not repeat one:
{existing}

{cfg['voice']}"""

    def call(extra):
        payload = {
            "model": MODEL,
            "max_tokens": 8000,
            "messages": [{"role": "user", "content": prompt}],
        }
        payload.update(extra)
        req = urllib.request.Request(API, data=json.dumps(payload).encode(), headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode())

    # effort is asked for, not insisted on. This job runs unattended at ten
    # past the hour on a Tuesday, and a parameter the account's API version
    # happens not to accept would mean no post and nobody finding out until
    # somebody looked at the blog. If it is refused, the post is still worth
    # having at the model's own default.
    try:
        data = call({"output_config": {"effort": "high"}})
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        if e.code == 400 and "output_config" in detail:
            print("  (effort not accepted here; writing at the default)", file=sys.stderr)
            try:
                data = call({})
            except urllib.error.HTTPError as e2:
                die(f"the API said {e2.code}: {e2.read().decode()[:300]}")
            except Exception as e2:
                die(f"could not reach the API: {e2}")
        else:
            die(f"the API said {e.code}: {detail}")
    except Exception as e:
        die(f"could not reach the API: {e}")

    if data.get("stop_reason") == "refusal":
        die("the model declined this subject")

    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        post = json.loads(text)
    except Exception:
        die(f"the reply was not JSON: {text[:300]}")

    for k in ("title", "slug", "desc", "body"):
        if not str(post.get(k, "")).strip():
            die(f"the reply had no {k}")
    post["slug"] = re.sub(r"[^a-z0-9-]", "", post["slug"].lower().replace(" ", "-")).strip("-")
    if not post["slug"]:
        die("the slug came back empty after cleaning")
    return post


# ── THE PAGE ───────────────────────────────────────────────────────────────
def build_page(cfg, skeleton, post):
    url = f"{cfg['domain']}{cfg['url_prefix']}{post['slug']}/"
    s = skeleton

    s = re.sub(r"<title>.*?</title>",
               lambda _: f"<title>{esc(post['title'])}{cfg['title_suffix']}</title>",
               s, count=1, flags=re.S)
    for pat in (r'(<meta name="description" content=")[^"]*(")',
                r'(<meta property="og:description" content=")[^"]*(")',
                r'(<meta name="twitter:description" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + esc(post["desc"]) + m.group(2), s, count=1)
    for pat in (r'(<meta property="og:title" content=")[^"]*(")',
                r'(<meta name="twitter:title" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + esc(post["title"]) + m.group(2), s, count=1)
    for pat in (r'(<link rel="canonical" href=")[^"]*(")',
                r'(<meta property="og:url" content=")[^"]*(")'):
        s = re.sub(pat, lambda m: m.group(1) + url + m.group(2), s, count=1)

    # A new post exists in this language only. Claiming a translation that is
    # not there sends a search engine to a 404.
    s = re.sub(r'\s*<link rel="alternate" hreflang="(?!' + cfg["lang"] + r'|x-default)[^"]*"[^>]*/?>', "", s)
    s = re.sub(r'(<link rel="alternate" hreflang="(?:' + cfg["lang"] + r'|x-default)" href=")[^"]*(")',
               lambda m: m.group(1) + url + m.group(2), s)

    def fix_ld(m):
        try:
            data = json.loads(m.group(1))
        except Exception:
            return m.group(0)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def walk(n):
            if isinstance(n, dict):
                if "headline" in n:
                    n["headline"] = post["title"]
                if "description" in n:
                    n["description"] = post["desc"]
                for k in ("datePublished", "dateModified"):
                    if k in n:
                        n[k] = today
                if n.get("@type") in ("BlogPosting", "Article", "WebPage"):
                    n["url"] = url
                    if "mainEntityOfPage" in n:
                        n["mainEntityOfPage"] = url
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)

        walk(data)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"

    s = re.sub(r'<script type="application/ld\+json">(.*?)</script>', fix_ld, s,
               count=1, flags=re.S)

    s = re.sub(r"(<h1[^>]*>).*?(</h1>)",
               lambda m: m.group(1) + esc(post["title"]) + m.group(2), s, count=1, flags=re.S)

    start, end = cfg["body_start"], cfg["body_end"]
    a, b = s.find(start), s.find(end)
    if a < 0 or b < 0 or b <= a:
        die("could not find where the words go in the skeleton")
    a += len(start)
    s = (s[:a] + cfg.get("body_prefix", "") + post["body"]
         + cfg.get("body_suffix", "") + s[b:])

    # The date on the page, where the skeleton shows one.
    if cfg.get("date_pattern"):
        when = datetime.now(timezone.utc).strftime(cfg.get("date_format", "%d %b %Y"))
        s = re.sub(cfg["date_pattern"], lambda m: m.group(1) + when + m.group(2), s, count=1)
    return s


def add_to_index(cfg, index_html, post):
    if f'href="{cfg["url_prefix"]}{post["slug"]}/"' in index_html:
        return index_html
    # Cards on two of these sites carry a photograph, and a card without one
    # has a hole in it where every other card has a picture. There is no new
    # photograph for a post nobody has been out to shoot, so it takes the
    # closest thing already on the site.
    img = cfg.get("card_image_default", "")
    low = (post["title"] + " " + post["desc"]).lower()
    for word, path in cfg.get("card_images", []):
        if word in low:
            img = path
            break
    when = datetime.now(timezone.utc).strftime(cfg.get("card_when", "%B %Y"))
    card = cfg["card"].replace("@@URL@@", f'{cfg["url_prefix"]}{post["slug"]}/') \
                      .replace("@@TITLE@@", esc(post["title"])) \
                      .replace("@@DESC@@", esc(post["desc"])) \
                      .replace("@@IMG@@", img) \
                      .replace("@@WHEN@@", when)
    m = re.search(cfg["card_anchor"], index_html)
    if not m:
        print("  ! could not find where the cards go; index left alone", file=sys.stderr)
        return index_html
    return index_html[:m.start()] + card + index_html[m.start():]


def main():
    cfg = load_config()
    topics_path = os.path.join(ROOT, cfg.get("topics", "topics.md"))
    topic, state = next_topic(topics_path)
    if not topic:
        die(f"nothing left in {cfg.get('topics', 'topics.md')} - add some lines to it")

    posts_dir = os.path.join(ROOT, cfg["posts_dir"])
    skeleton_path = os.path.join(ROOT, cfg["skeleton"])
    index_path = os.path.join(ROOT, cfg["index"])
    for p in (skeleton_path, index_path):
        if not os.path.exists(p):
            die(f"{p} is missing")

    existing = "\n".join(
        f"- {d}" for d in sorted(os.listdir(posts_dir))
        if os.path.isdir(os.path.join(posts_dir, d))) or "- (none yet)"

    print(f"writing: {topic}")
    post = ask_claude(cfg, topic, existing)
    print(f"  title: {post['title']}")
    print(f"  slug:  {post['slug']}")

    folder = os.path.join(posts_dir, post["slug"])
    page = os.path.join(folder, "index.html")
    if os.path.exists(page):
        die(f"{cfg['url_prefix']}{post['slug']}/ already exists, and what is on disk wins")

    skeleton = open(skeleton_path, encoding="utf-8").read()
    html = build_page(cfg, skeleton, post)
    os.makedirs(folder, exist_ok=True)
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)

    index_html = open(index_path, encoding="utf-8").read()
    updated = add_to_index(cfg, index_html, post)
    if updated != index_html:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(updated)

    tick_off(topics_path, state, post["slug"])
    print(f"published {cfg['url_prefix']}{post['slug']}/ ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
