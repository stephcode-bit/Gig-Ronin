"""
api/search.py
Vercel Python Serverless Function.

Serves gig data from a pre-generated local snapshot (api/data/gigs.json) instead of
calling Reddit live. This is deliberate: Reddit blocks most datacenter/server IPs and
gates new API access behind manual approval, so this function never talks to Reddit at
all. The snapshot is produced by running `python scraper.py` on your own machine and
redeploying (see README.md).

GET /api/search                    -> all categories from the snapshot
GET /api/search?category=bounty    -> one category (bounty | website | design)
GET /api/search?q=logo             -> keyword filter across the snapshot (client-side match)
"""

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "data", "gigs.json")


def _load_snapshot():
    if not os.path.exists(SNAPSHOT_PATH):
        return {"categories": {}, "generated_at": None}
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _all_posts(snapshot):
    categories = snapshot.get("categories", {})
    posts = []
    for cat_posts in categories.values():
        posts.extend(cat_posts)
    posts.sort(key=lambda p: p.get("created_utc") or 0, reverse=True)
    return posts


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        category = query.get("category", [None])[0]
        keyword = query.get("q", [None])[0]

        try:
            snapshot = _load_snapshot()
            generated_at = snapshot.get("generated_at")
            is_sample = snapshot.get("is_sample", False)

            if keyword:
                needle = keyword.lower()
                results = [
                    p for p in _all_posts(snapshot)
                    if needle in (p.get("title", "") + " " + p.get("snippet", "")).lower()
                ]
                payload = {"query": keyword, "results": results}
            elif category:
                results = snapshot.get("categories", {}).get(category, [])
                payload = {"category": category, "results": results}
            else:
                payload = {"categories": snapshot.get("categories", {})}

            payload["generated_at"] = generated_at
            payload["is_sample"] = is_sample

            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(body)

        except Exception as exc:  # noqa: BLE001
            error_body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_body)
