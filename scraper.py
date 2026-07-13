#!/usr/bin/env python3
"""
scraper.py
Standalone CLI for the Reddit Gig Finder. Run this on YOUR OWN machine (not on Vercel --
Reddit blocks most datacenter/server IPs) to pull the latest bounty / website-gig /
product-design posts from Reddit and save a snapshot that the deployed site reads.

The Vercel API (api/search.py) does NOT call Reddit live -- it just serves whatever
snapshot is sitting in api/data/gigs.json. That means: no Reddit API approval needed,
no risk of the server getting IP-blocked. You refresh data by re-running this script
and redeploying (or just pushing to GitHub, if Vercel auto-deploys on push).

Usage:
    python scraper.py                       # full snapshot -> api/data/gigs.json (default)
    python scraper.py --time week            # hour|day|week|month|year|all (default: month)
    python scraper.py --category bounty      # one category only, ad-hoc -> gigs.json
    python scraper.py --keyword "figma"      # free-text search, ad-hoc -> gigs.json
    python scraper.py --out custom.json      # override the output path
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv  # optional -- pip install python-dotenv

    load_dotenv()
except ImportError:
    pass  # fine -- REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET can also be set directly in the shell

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))
import reddit_gigs  # noqa: E402

DEFAULT_SNAPSHOT_PATH = os.path.join("api", "data", "gigs.json")


def main():
    parser = argparse.ArgumentParser(description="Search Reddit for bounty, website, and product design gigs.")
    parser.add_argument("--category", choices=list(reddit_gigs.CATEGORIES.keys()), help="Search a single category")
    parser.add_argument("--keyword", help="Free-text keyword search across all gig subreddits")
    parser.add_argument("--time", default="month", choices=["hour", "day", "week", "month", "year", "all"])
    parser.add_argument("--out", default=None, help="Output JSON file path")
    args = parser.parse_args()

    print("Searching Reddit for gigs... this can take a few seconds per subreddit.")

    if args.keyword:
        results = reddit_gigs.search_keyword(args.keyword, time_filter=args.time)
        payload = {"query": args.keyword, "results": results}
        total = len(results)
        out_path = args.out or "gigs.json"
    elif args.category:
        results = reddit_gigs.search_category(args.category, time_filter=args.time)
        payload = {"category": args.category, "results": results}
        total = len(results)
        out_path = args.out or "gigs.json"
    else:
        payload = {"categories": reddit_gigs.search_all(time_filter=args.time)}
        total = sum(len(v) for v in payload["categories"].values())
        out_path = args.out or DEFAULT_SNAPSHOT_PATH

    payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Done. Found {total} gig(s). Saved to {out_path}")
    if out_path == DEFAULT_SNAPSHOT_PATH:
        print("This is the file the deployed site reads. Redeploy (or git push, if auto-deploy is on) to publish it.")


if __name__ == "__main__":
    main()
