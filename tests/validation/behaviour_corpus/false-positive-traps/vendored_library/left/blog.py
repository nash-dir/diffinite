"""Static blog generator: turns markdown-ish posts into HTML pages."""
import os
import sys
from datetime import date
from html import escape

from vendor.textkit import slugify, truncate_words, reading_time_minutes

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body><article><h1>{title}</h1><p class="meta">{date} &middot; {minutes} min read</p>
{body}
</article></body></html>
"""


class Post:
    def __init__(self, title, published, body):
        self.title = title
        self.published = published
        self.body = body

    @property
    def slug(self):
        return slugify(self.title, max_length=60)

    @property
    def summary(self):
        return truncate_words(self.body.replace("\n", " "), 30)


def parse_post(path):
    with open(path, encoding="utf-8") as fh:
        header, _, body = fh.read().partition("\n---\n")
    meta = {}
    for line in header.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    published = date.fromisoformat(meta.get("date", "1970-01-01"))
    return Post(meta.get("title", os.path.basename(path)), published, body.strip())


def render_body(text):
    out = []
    for para in text.split("\n\n"):
        para = para.strip()
        if para.startswith("# "):
            out.append("<h2>%s</h2>" % escape(para[2:]))
        elif para:
            out.append("<p>%s</p>" % escape(para))
    return "\n".join(out)


def build(src_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    posts = [parse_post(os.path.join(src_dir, f))
             for f in sorted(os.listdir(src_dir)) if f.endswith(".md")]
    posts.sort(key=lambda p: p.published, reverse=True)
    for post in posts:
        html = TEMPLATE.format(
            title=escape(post.title),
            date=post.published.isoformat(),
            minutes=reading_time_minutes(post.body),
            body=render_body(post.body),
        )
        with open(os.path.join(out_dir, post.slug + ".html"), "w", encoding="utf-8") as fh:
            fh.write(html)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<ul>\n")
        for post in posts:
            fh.write('<li><a href="%s.html">%s</a> - %s</li>\n'
                     % (post.slug, escape(post.title), escape(post.summary)))
        fh.write("</ul>\n")
    return len(posts)


if __name__ == "__main__":
    n = build(sys.argv[1], sys.argv[2])
    print("built %d posts" % n)
