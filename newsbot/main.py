"""Runs one full cycle: collect -> keep only new -> group -> score -> save -> alert.

Run it with:  python -m newsbot.main
"""
import json
import os
import pathlib
import sys
import time

import yaml

from . import sources as src_mod
from . import stories as st
from . import telegram
from .llm import LLM

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "state.json"
SITE_FILE = ROOT / "docs" / "data.json"


def log(msg):
    print(msg, flush=True)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def site_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def run(config_path=ROOT / "config.yaml", collected=None):
    cfg = yaml.safe_load(pathlib.Path(config_path).read_text(encoding="utf-8"))
    settings = cfg.get("settings", {})
    keep = settings.get("keep_hours", 72)

    state = load_json(STATE_FILE, {})
    seen = state.setdefault("seen", {})
    stories = state.setdefault("stories", {})

    log("1) Collecting")
    if collected is None:
        items, report = src_mod.collect_all(cfg.get("sources", []), log)
    else:
        items, report = collected, {"test": len(collected)}

    log("2) Keeping only new articles")
    new = st.pick_new(items, seen, keep, settings.get("max_new_items_per_run", 150))
    log(f"   {len(items)} collected, {len(new)} new")

    log("3) Grouping into stories")
    llm = LLM(settings.get("llm"), log)
    size = settings.get("llm_batch_size", 40)
    for i in range(0, len(new), size):
        batch = new[i:i + size]
        result = None
        if llm.available:
            result = st.group_with_llm(llm, batch, stories, log)
        if result:
            grouped, missing = result
            st.merge(grouped, stories, True)
            if missing:
                st.merge(st.group_simple(missing, stories), stories, False)
        else:
            st.merge(st.group_simple(batch, stories), stories, False)

    log("4) Scoring and cleaning up")
    st.prune(stories, seen, keep)
    for s in stories.values():
        st.score(s)

    log("5) Telegram")
    telegram.run_alerts(stories, state, settings.get("telegram", {}), site_url(), log)

    log("6) Saving")
    now = int(time.time())
    if llm.calls:
        ai_note = "AI on" if llm.used else "AI limit reached - showing simple summaries"
    else:
        ai_note = "AI on" if llm.chain else "AI key not set - showing simple summaries"
    state.update({"last_run": now, "sources_report": report})
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")),
                          encoding="utf-8")

    trending_min = settings.get("trending_min_sources", 3)
    public = []
    for s in sorted(stories.values(), key=lambda s: (-s["score"], -s["updated"])):
        items_sorted = sorted(s["items"], key=lambda x: -x["ts"])
        public.append({
            "id": s["id"], "title": s["title"], "summary": s["summary"], "tip": s.get("tip", ""),
            "tab": s["section"] if s["section"] != "news" else (s.get("state") or "IN"),
            "created": s["created"], "updated": s["updated"], "score": s["score"],
            "n_sources": s["n_sources"], "trending": s["n_sources"] >= trending_min,
            "ai": s.get("ai", False),
            "items": [{k: x[k] for k in ("title", "link", "source", "ts", "lang")}
                      for x in items_sorted[:12]],
        })
    SITE_FILE.parent.mkdir(exist_ok=True)
    SITE_FILE.write_text(json.dumps(
        {"generated": now, "ai_note": ai_note, "llm_used": llm.used,
         "sources": report, "stories": public}, ensure_ascii=False), encoding="utf-8")
    log(f"   {len(public)} stories on the page. AI calls this run: {llm.calls} {llm.used}")
    return public


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else ROOT / "config.yaml")
