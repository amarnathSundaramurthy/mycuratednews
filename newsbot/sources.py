"""Collectors: each one returns a list of plain dict items.

Every collector is wrapped so that one broken source never stops the others.
"""
import html
import re
import time
import urllib.parse

import feedparser
import requests

UA = "SouthIndiaNewsBot/1.0 (personal news reader)"
TIMEOUT = 20

AI_WORDS = re.compile(
    r"\b(ai|a\.i\.|llm|llms|gpt|chatgpt|openai|anthropic|claude|gemini|llama|mistral|"
    r"deepseek|copilot|agent|agents|agentic|machine learning|neural|transformer|"
    r"diffusion|hugging ?face|prompt|rag|fine-?tun\w*|inference)\b",
    re.I,
)

GN_EDITIONS = {
    "en": ("en-IN", "IN", "IN:en"),
    "kn": ("kn", "IN", "IN:kn"),
    "ta": ("ta", "IN", "IN:ta"),
    "te": ("te", "IN", "IN:te"),
    "ml": ("ml", "IN", "IN:ml"),
}


def clean(text, limit=320):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _item(src, title, link, summary="", ts=None, score=0, lang="en", source_name=None):
    return {
        "title": clean(title, 300),
        "link": link,
        "summary": clean(summary),
        "ts": int(ts or time.time()),
        "score": score,
        "lang": lang,
        "source": source_name or src["name"],
        "feed": src["name"],
        "section": src.get("section", "news"),
        "state": src.get("state"),
    }


def _entry_ts(e):
    for key in ("published_parsed", "updated_parsed"):
        if e.get(key):
            return int(time.mktime(e[key]))
    return None


def _get(url, **kw):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- RSS
def fetch_rss(src, url=None, lang=None):
    feed = feedparser.parse(_get(url or src["url"]).content)
    out = []
    for e in feed.entries[:60]:
        if not e.get("title") or not e.get("link"):
            continue
        out.append(_item(src, e.title, e.link, e.get("summary", ""), _entry_ts(e),
                         lang=lang or src.get("lang", "en")))
    return out


# -------------------------------------------------------- Google News
def google_news_url(lang, query=None):
    hl, gl, ceid = GN_EDITIONS.get(lang, GN_EDITIONS["en"])
    params = f"hl={hl}&gl={gl}&ceid={urllib.parse.quote(ceid)}"
    if query:
        return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&{params}"
    return f"https://news.google.com/rss?{params}"


def fetch_google_news(src):
    lang = src.get("lang", "en")
    items = fetch_rss(src, google_news_url(lang, src.get("query")), lang)
    for it in items:
        # Google adds " - Publisher" to the end of titles; use it as the source name.
        m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", it["title"])
        if m:
            it["title"], it["source"] = m.group(1).strip(), m.group(2).strip()
        it["summary"] = ""  # Google's summary is just the title again
    return items


# ----------------------------------------------------------- Inshorts
def fetch_inshorts(src):
    """Unofficial. Tries two known Inshorts addresses; returns [] if both fail."""
    attempts = [_inshorts_read_api, _inshorts_web_api]
    last_err = None
    for fn in attempts:
        try:
            items = fn(src)
            if items:
                return items
        except Exception as e:  # noqa: BLE001
            last_err = e
    if last_err:
        raise last_err
    return []


def _inshorts_obj_to_item(src, o):
    ts = o.get("created_at")
    if ts and ts > 10_000_000_000:  # milliseconds
        ts = ts / 1000
    link = o.get("source_url") or o.get("shortened_url") or ""
    if not link:
        return None
    return _item(src, o.get("title", ""), link, o.get("content", ""), ts,
                 source_name=f"Inshorts / {o.get('source_name') or 'Inshorts'}")


def _inshorts_read_api(src):
    base = "https://read-api.newsinshorts.com"
    meta = _get(f"{base}/en/v4/news/top_refresh").json()
    ids = [n["hash_id"] for n in meta.get("news_list", []) if n.get("type") == "NEWS"][:60]
    if not ids:
        return []
    r = requests.post(f"{base}/en/v2/hash_id/search", json={"news_hash_ids": ids},
                      headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    objs = r.json().get("news_objs", [])
    return [i for i in (_inshorts_obj_to_item(src, o) for o in objs) if i]


def _inshorts_web_api(src):
    url = "https://inshorts.com/api/en/news?category=all_news&max_limit=60&include_card_data=true"
    data = _get(url).json().get("data", {})
    objs = [n.get("news_obj", n) for n in data.get("news_list", [])]
    return [i for i in (_inshorts_obj_to_item(src, o) for o in objs) if i]


# ------------------------------------------------------------- Reddit
def fetch_reddit(src):
    sort = src.get("sort", "hot")
    url = f"https://www.reddit.com/r/{src['subreddit']}/{sort}/.rss"
    if sort == "top":
        url += "?t=day"
    items = fetch_rss(src, url)
    for it in items:
        it["source"] = src["name"]
    return items


# -------------------------------------------------------- Hacker News
def fetch_hackernews(src):
    data = _get("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=60").json()
    out = []
    for h in data.get("hits", []):
        title = h.get("title") or ""
        if not AI_WORDS.search(title):
            continue
        link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append(_item(src, title, link, "", h.get("created_at_i"), score=h.get("points") or 0))
    return out


COLLECTORS = {
    "rss": fetch_rss,
    "google_news": fetch_google_news,
    "inshorts": fetch_inshorts,
    "reddit": fetch_reddit,
    "hackernews": fetch_hackernews,
}


def collect_all(sources, log):
    items, report = [], {}
    for src in sources:
        fn = COLLECTORS.get(src.get("type"))
        if not fn:
            log(f"  ! {src.get('name')}: unknown type {src.get('type')}")
            continue
        try:
            got = fn(src)
            items.extend(got)
            report[src["name"]] = len(got)
            log(f"  ok {src['name']}: {len(got)}")
        except Exception as e:  # noqa: BLE001
            report[src["name"]] = f"error: {type(e).__name__}"
            log(f"  ! {src['name']}: {type(e).__name__}: {str(e)[:120]}")
        time.sleep(0.5)  # be polite
    return items, report
