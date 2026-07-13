"""
reddit_gigs.py
Core search logic for finding bounty, website-gig, and product-design gigs on Reddit.

Works two ways:
  - No credentials set: falls back to Reddit's public JSON endpoints (www.reddit.com).
    Fine for light/occasional use, but Reddit rate-limits and sometimes blocks these.
  - REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET set as environment variables: authenticates
    via OAuth2 "client_credentials" grant and calls oauth.reddit.com instead, which is
    far more reliable and has a much higher rate limit. See README.md for how to get
    these from https://www.reddit.com/prefs/apps -- NEVER hardcode them in this file.

Single source of truth, imported by:
  - scraper.py       (standalone CLI, for local runs / cron jobs)
  - api/search.py    (Vercel serverless function, for the PWA frontend)
"""

import os
import time
import json
import base64
import urllib.request
import urllib.parse
import urllib.error

CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "python:reddit-gig-finder:v1.0 (by /u/gigfinder)")

_token_cache = {"token": None, "expires_at": 0}

# Posts on hiring boards use flair to say who is looking for who.
# We want posts where someone is looking to PAY for work (HIRING / TASK / bounty),
# not posts where a freelancer is advertising themselves (FOR HIRE).
EXCLUDE_FLAIRS = {"for hire", "forhire", "closed", "resolved", "hired"}
INCLUDE_HINTS = {"hiring", "task", "bounty", "paid", "gig", "budget", "job"}

CATEGORIES = {
    "bounty": {
        "label": "Bounties",
        "subreddits": ["slavelabour", "Jobs4Bitcoins", "INAT", "forhire", "gigwork"],
        "query": "bounty OR paid OR reward OR \"small task\"",
    },
    "website": {
        "label": "Website Gigs",
        "subreddits": ["forhire", "webdev", "WordPress", "freelance", "Shopify", "juniordevelopers"],
        "query": "website OR webdev OR wordpress OR shopify OR \"landing page\" OR frontend",
    },
    "design": {
        "label": "Product Design",
        "subreddits": ["forhire", "userexperience", "UI_Design", "graphic_design", "ProductDesign", "web_design"],
        "query": "logo OR \"product design\" OR \"UI/UX\" OR figma OR branding OR illustration",
    },
}


def _get_access_token():
    """Exchange REDDIT_CLIENT_ID/SECRET for a short-lived OAuth token (app-only, read-only)."""
    if not (CLIENT_ID and CLIENT_SECRET):
        return None
    if _token_cache["token"] and _token_cache["expires_at"] > time.time() + 30:
        return _token_cache["token"]

    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=data,
        headers={"Authorization": f"Basic {auth}", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        _token_cache["token"] = payload["access_token"]
        _token_cache["expires_at"] = time.time() + payload.get("expires_in", 3600)
        return _token_cache["token"]
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError):
        return None


def _fetch_json(url, headers, retries=2, backoff=1.5):
    """Fetch a URL and parse JSON, with a couple of polite retries."""
    req = urllib.request.Request(url, headers=headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _search_subreddit(subreddit, query, limit=15, time_filter="month"):
    """Search one subreddit. Uses OAuth (oauth.reddit.com) if credentials are set,
    otherwise falls back to the public JSON endpoint (www.reddit.com)."""
    params = {
        "q": query,
        "restrict_sr": "1",
        "sort": "new",
        "t": time_filter,
        "limit": str(limit),
    }
    token = _get_access_token()
    if token:
        base = "https://oauth.reddit.com"
        headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    else:
        base = "https://www.reddit.com"
        headers = {"User-Agent": USER_AGENT}

    url = f"{base}/r/{subreddit}/search.json?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_json(url, headers)
    except RuntimeError:
        return []
    children = data.get("data", {}).get("children", [])
    return [c.get("data", {}) for c in children if c.get("kind") == "t3"]


def _normalize(post, category_key):
    flair = (post.get("link_flair_text") or "").strip()
    return {
        "id": post.get("id"),
        "title": post.get("title", "").strip(),
        "subreddit": post.get("subreddit"),
        "author": post.get("author"),
        "flair": flair,
        "url": f"https://www.reddit.com{post.get('permalink', '')}",
        "created_utc": post.get("created_utc"),
        "score": post.get("score", 0),
        "num_comments": post.get("num_comments", 0),
        "snippet": (post.get("selftext") or "")[:220].strip(),
        "category": category_key,
    }


def _looks_like_a_gig(post):
    """Filter out freelancers advertising themselves; keep posts where someone wants to pay for work."""
    flair = (post.get("link_flair_text") or "").lower()
    title = (post.get("title") or "").lower()

    if any(bad in flair for bad in EXCLUDE_FLAIRS):
        return False
    if "[for hire]" in title:
        return False
    return True


def search_category(category_key, limit_per_sub=12, time_filter="month"):
    """Search all subreddits configured for one category, dedupe, and sort by newest."""
    if category_key not in CATEGORIES:
        raise ValueError(f"Unknown category: {category_key}")

    config = CATEGORIES[category_key]
    seen_ids = set()
    results = []

    for subreddit in config["subreddits"]:
        posts = _search_subreddit(subreddit, config["query"], limit=limit_per_sub, time_filter=time_filter)
        for post in posts:
            if not _looks_like_a_gig(post):
                continue
            pid = post.get("id")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            results.append(_normalize(post, category_key))

    results.sort(key=lambda p: p.get("created_utc") or 0, reverse=True)
    return results


def search_all(limit_per_sub=10, time_filter="month"):
    """Search every category. Returns {category_key: [posts...]}."""
    return {key: search_category(key, limit_per_sub=limit_per_sub, time_filter=time_filter) for key in CATEGORIES}


def search_keyword(keyword, limit_per_sub=8, time_filter="month"):
    """Free-text search across every category's subreddit list for a specific keyword."""
    seen_ids = set()
    results = []
    all_subs = []
    for config in CATEGORIES.values():
        for sub in config["subreddits"]:
            if sub not in all_subs:
                all_subs.append(sub)

    for subreddit in all_subs:
        posts = _search_subreddit(subreddit, keyword, limit=limit_per_sub, time_filter=time_filter)
        for post in posts:
            if not _looks_like_a_gig(post):
                continue
            pid = post.get("id")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            results.append(_normalize(post, "search"))

    results.sort(key=lambda p: p.get("created_utc") or 0, reverse=True)
    return results
