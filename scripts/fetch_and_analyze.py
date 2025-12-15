#!/usr/bin/env python3
"""
Fetch latest Reddit posts and generate:
- data/posts.json  (latest posts with sentiment 1-5 + extracted "requested items")
- data/wordfreq.json (top items/phrases for word cloud)
- data/summary.json (aggregate stats)

Designed to run in GitHub Actions (scheduled) OR locally.

Reddit source: public JSON endpoint for 'new' listing.
OpenAI: Responses API via openai-python.
"""
from __future__ import annotations

import os
import json
import time
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# OpenAI SDK
from openai import OpenAI

UA = "codm-sentiment-tracker/1.0 (github-pages; contact: you@example.com)"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(x: Any, default: int) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _clean_text(s: str) -> str:
    s = s or ""
    # Remove URLs and excessive whitespace
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_reddit_new(subreddit: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch posts from /new.json, paginating until 'limit' posts are collected.
    """
    posts: List[Dict[str, Any]] = []
    after = None
    base = f"https://www.reddit.com/r/{subreddit}/new.json"
    headers = {"User-Agent": UA}

    while len(posts) < limit:
        remaining = limit - len(posts)
        # Reddit listing limit max is typically 100
        page_limit = min(100, remaining)
        params = {"limit": str(page_limit)}
        if after:
            params["after"] = after

        resp = requests.get(base, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        for c in children:
            d = c.get("data", {})
            if d:
                posts.append(d)

        after = data.get("data", {}).get("after", None)
        if not after:
            break

        # be gentle
        time.sleep(1.0)

    return posts[:limit]


def filter_by_age(posts: List[Dict[str, Any]], max_age_hours: Optional[int]) -> List[Dict[str, Any]]:
    if not max_age_hours:
        return posts
    cutoff = _now_utc() - timedelta(hours=max_age_hours)
    out = []
    for p in posts:
        created_utc = p.get("created_utc")
        if created_utc is None:
            continue
        dt = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
        if dt >= cutoff:
            out.append(p)
    return out


@dataclass
class ScoredPost:
    id: str
    title: str
    selftext: str
    url: str
    permalink: str
    author: str
    created_utc: float
    num_comments: int
    score: int
    sentiment_1_5: int
    sentiment_reason: str
    requested_items: List[str]


def openai_score_posts(client: OpenAI, subreddit: str, posts: List[Dict[str, Any]]) -> List[ScoredPost]:
    """
    Uses OpenAI to produce:
      - sentiment_1_5 (1..5)
      - short reason (<= 20 words)
      - requested_items (0..5 short noun phrases)
    """
    # Keep costs sane: we only send title + first N chars of body
    MAX_BODY_CHARS = 1200

    scored: List[ScoredPost] = []

    system = (
        "You are an analyst for a mobile game community. "
        "Given a Reddit post, output STRICT JSON with keys: "
        "sentiment_1_5 (integer 1..5), sentiment_reason (<=20 words), "
        "requested_items (array of 0..5 short phrases). "
        "Requested items = content the author is asking for (buff/nerf/add/remove/fix), "
        "or the main items being discussed (maps, guns, operators, perks, modes, bugs). "
        "If unclear, return an empty array for requested_items."
    )

    for p in posts:
        title = _clean_text(p.get("title", ""))
        body = _clean_text(p.get("selftext", ""))
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS] + "…"

        prompt = {
            "subreddit": subreddit,
            "title": title,
            "body": body,
        }

        # Use Responses API. Model can be changed if you prefer cheaper.
        # We keep max_output_tokens low; output is small JSON.
        resp = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5.2"),
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            max_output_tokens=250,
        )

        # openai-python provides output_text convenience
        out_text = getattr(resp, "output_text", "") or ""
        out_text = out_text.strip()

        # try to locate JSON object in the output
        m = re.search(r"\{.*\}", out_text, flags=re.DOTALL)
        if not m:
            # fallback
            sentiment = 3
            reason = "No JSON parsed."
            items = []
        else:
            try:
                obj = json.loads(m.group(0))
                sentiment = _safe_int(obj.get("sentiment_1_5"), 3)
                sentiment = max(1, min(5, sentiment))
                reason = str(obj.get("sentiment_reason", "")).strip()[:200]
                items = obj.get("requested_items", [])
                if not isinstance(items, list):
                    items = []
                # sanitize phrases
                clean_items = []
                for it in items[:5]:
                    it2 = _clean_text(str(it))
                    it2 = re.sub(r"[^\w\s\-\+&'/]", "", it2).strip()
                    if it2:
                        clean_items.append(it2[:60])
                items = clean_items
            except Exception:
                sentiment = 3
                reason = "JSON parse error."
                items = []

        scored.append(
            ScoredPost(
                id=str(p.get("id", "")),
                title=title,
                selftext=body,
                url=str(p.get("url", "")),
                permalink="https://www.reddit.com" + str(p.get("permalink", "")),
                author=str(p.get("author", "")),
                created_utc=float(p.get("created_utc", 0.0)),
                num_comments=_safe_int(p.get("num_comments"), 0),
                score=_safe_int(p.get("score"), 0),
                sentiment_1_5=sentiment,
                sentiment_reason=reason,
                requested_items=items,
            )
        )

        # gentle pacing (helps avoid accidental API bursts)
        time.sleep(0.2)

    return scored


def build_word_freq(scored: List[ScoredPost]) -> Dict[str, int]:
    """
    Aggregate requested_items first (strong signal),
    then fall back to simple keyword extraction from titles/bodies.
    """
    freq: Dict[str, int] = {}

    def add(token: str, w: int = 1):
        token = token.strip()
        if not token:
            return
        freq[token] = freq.get(token, 0) + w

    # 1) requested items (weighted)
    for sp in scored:
        for it in sp.requested_items:
            add(it.lower(), 3)

    # 2) lightweight keyword extraction (for coverage)
    stop = set("""
        the a an and or but if then else when while to of in on for with without is are was were be been being
        i you he she they we it this that these those my your our their
        codm cod mobile call duty callofdutymobile
        pls please thanks thank
        just like game gameplay player players
        really very much
    """.split())

    def tokens_from(text: str) -> List[str]:
        text = text.lower()
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"[^a-z0-9\s\-\+&'/]", " ", text)
        parts = re.split(r"\s+", text)
        out = []
        for t in parts:
            t = t.strip("-'\"")
            if len(t) < 3:
                continue
            if t in stop:
                continue
            if t.isdigit():
                continue
            out.append(t)
        return out

    for sp in scored:
        for t in tokens_from(sp.title):
            add(t, 1)
        for t in tokens_from(sp.selftext):
            add(t, 1)

    # prune extremely common single letters etc.
    freq = {k: v for k, v in freq.items() if len(k) >= 3}

    return freq


def write_json(path: str, obj: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    load_dotenv()  # local only; in GitHub Actions env is passed separately

    subreddit = os.getenv("SUBREDDIT", "CallOfDutyMobile").strip()
    limit = _safe_int(os.getenv("POST_LIMIT", "50"), 50)
    max_age_hours = os.getenv("MAX_AGE_HOURS", "").strip()
    max_age_hours_i = _safe_int(max_age_hours, 0) if max_age_hours else None

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_key:
        raise SystemExit("OPENAI_API_KEY missing. Set it in env (GitHub Secret or scripts/.env).")

    print(f"Fetching r/{subreddit} newest posts…")
    raw_posts = fetch_reddit_new(subreddit=subreddit, limit=limit)
    raw_posts = filter_by_age(raw_posts, max_age_hours=max_age_hours_i)
    print(f"Got {len(raw_posts)} posts after filters.")

    client = OpenAI(api_key=openai_key)

    print("Scoring sentiment + extracting requested items via OpenAI…")
    scored = openai_score_posts(client, subreddit, raw_posts)

    # serialize posts
    posts_out = []
    for sp in scored:
        posts_out.append(
            {
                "id": sp.id,
                "title": sp.title,
                "selftext": sp.selftext,
                "url": sp.url,
                "permalink": sp.permalink,
                "author": sp.author,
                "created_utc": sp.created_utc,
                "created_iso": datetime.fromtimestamp(sp.created_utc, tz=timezone.utc).isoformat(),
                "num_comments": sp.num_comments,
                "score": sp.score,
                "sentiment_1_5": sp.sentiment_1_5,
                "sentiment_reason": sp.sentiment_reason,
                "requested_items": sp.requested_items,
            }
        )

    freq = build_word_freq(scored)

    # top terms
    top_terms = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:150]
    wordfreq_out = [{"term": k, "count": v} for k, v in top_terms]

    # summary
    if scored:
        avg_sent = sum(sp.sentiment_1_5 for sp in scored) / len(scored)
    else:
        avg_sent = 0.0

    summary = {
        "subreddit": subreddit,
        "post_count": len(scored),
        "generated_at_utc": _now_utc().isoformat(),
        "avg_sentiment": round(avg_sent, 3),
        "sentiment_histogram": {
            str(i): sum(1 for sp in scored if sp.sentiment_1_5 == i) for i in range(1, 6)
        },
        "top_requested_items": wordfreq_out[:30],
    }

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.path.join(root, "data")

    write_json(os.path.join(data_dir, "posts.json"), posts_out)
    write_json(os.path.join(data_dir, "wordfreq.json"), wordfreq_out)
    write_json(os.path.join(data_dir, "summary.json"), summary)

    print("Wrote:")
    print(f" - {os.path.join(data_dir, 'posts.json')}")
    print(f" - {os.path.join(data_dir, 'wordfreq.json')}")
    print(f" - {os.path.join(data_dir, 'summary.json')}")


if __name__ == "__main__":
    main()
