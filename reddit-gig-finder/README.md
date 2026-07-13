# Gig Ronin — Reddit Bounty & Design Gig Finder

A Python-powered tool that searches public Reddit for **bounties**, **website gigs**,
and **product design gigs**, served through a Reddit-themed, installable PWA.

## How it actually works (important)

Reddit blocks most requests coming from datacenter/server IPs — including Vercel's —
and as of 2026 new OAuth API access is gated behind a manual approval process with no
guaranteed timeline. So this project deliberately **does not call Reddit live from
Vercel**. Instead:

1. You run `scraper.py` **on your own machine** (your home IP isn't blocked the way a
   server's is), which searches Reddit and saves a snapshot to `api/data/gigs.json`.
2. You deploy/redeploy to Vercel. The API (`api/search.py`) just reads that snapshot
   file and serves it — instant, reliable, and it never talks to Reddit itself.
3. Whenever you want fresh gigs, re-run the scraper and redeploy (or `git push` if
   Vercel auto-deploys your repo).

The site ships with a small sample snapshot so it renders correctly out of the box —
you'll see a gold banner saying so until you run the real scraper.

## What's inside

```
reddit-gig-finder/
├── api/
│   ├── search.py         # Vercel function -- serves api/data/gigs.json, no live calls
│   ├── reddit_gigs.py    # Reddit search logic (used only by scraper.py, run locally)
│   └── data/
│       └── gigs.json     # The snapshot the site reads. Regenerate with scraper.py.
├── scraper.py             # Run this locally to refresh api/data/gigs.json
├── public/                # The PWA frontend
│   ├── index.html
│   ├── manifest.json
│   ├── sw.js               # Service worker (offline app shell)
│   └── icons/               # Samurai favicon + PWA icons (SVG + PNG)
├── vercel.json             # Wires the static site + Python API together
└── requirements.txt
```

## Refreshing the data

```bash
python scraper.py                     # full snapshot -> api/data/gigs.json
python scraper.py --time week         # narrower time window
```

Then redeploy:

```bash
vercel --prod
```

Or, if your Vercel project is connected to a GitHub repo with auto-deploy on:

```bash
git add api/data/gigs.json
git commit -m "Refresh gigs"
git push
```

Want it hands-off? Set up a scheduled task on your own computer (cron on
macOS/Linux, Task Scheduler on Windows) to run the scraper + git push on a timer —
just make sure it runs from a machine with a normal residential IP, not a cloud VM,
or you'll hit the same blocking issue this architecture avoids.

## Reddit API credentials (optional, but recommended for scraper.py)

The tool works with **no credentials** by calling Reddit's public JSON endpoints,
but Reddit rate-limits and sometimes blocks those. For reliable use, get free
OAuth credentials:

1. Go to **https://www.reddit.com/prefs/apps** (log into Reddit first)
2. Click **create app** → choose type **script** → redirect uri can be
   `http://localhost:8080` (required but unused here)
3. Copy the **client ID** (short string under the app name) and **secret**

**Where these go — never hardcode them in a file:**

- **Local runs**: copy `.env.example` to `.env` and fill in your values.
  `scraper.py` loads it automatically (`pip install python-dotenv` if you want
  this convenience; otherwise just `export` the vars in your shell).
- **Vercel (production)**: add them as Environment Variables in your Vercel
  project — **Project → Settings → Environment Variables** — named exactly:
  - `REDDIT_CLIENT_ID`
  - `REDDIT_CLIENT_SECRET`
  - `REDDIT_USER_AGENT` (optional, defaults to a generic one)

  Or via CLI: `vercel env add REDDIT_CLIENT_ID`

`api/reddit_gigs.py` reads them with `os.environ.get(...)` — it never needs
the actual values in code, and `.env` is already in `.gitignore` so it can't
get committed by accident.

## Categories searched

| Category  | Subreddits searched |
|---|---|
| Bounties | r/slavelabour, r/Jobs4Bitcoins, r/INAT, r/forhire, r/gigwork |
| Website Gigs | r/forhire, r/webdev, r/WordPress, r/freelance, r/Shopify, r/juniordevelopers |
| Product Design | r/forhire, r/userexperience, r/UI_Design, r/graphic_design, r/ProductDesign, r/web_design |

Posts flaired `[For Hire]` (freelancers advertising themselves) are filtered out —
the tool only surfaces posts where someone is looking to **pay** for work.

## Run the API locally

```bash
npm install -g vercel
vercel dev
```

Then open `http://localhost:3000`. The frontend calls `/api/search`, which reads
`api/data/gigs.json` — run `scraper.py` first if you want real data instead of the
sample snapshot.

## Deploy to Vercel

1. Push this folder to a GitHub repo (or run `vercel` from inside it).
2. `vercel.json` is already configured to build the Python function in `api/`
   and serve everything in `public/` as the static site — no extra setup needed.
3. Deploy:

   ```bash
   vercel --prod
   ```

4. Your PWA is live. Visiting it on mobile shows an "Add to Home Screen" / "Install"
   prompt using the samurai icon and Reddit-orange theme color.

## API reference

`GET /api/search` (reads `api/data/gigs.json`, never calls Reddit)
- no params → all three categories
- `?category=bounty|website|design` → one category
- `?q=keyword` → filters the snapshot by keyword (title + snippet)

Every response includes `generated_at` (when the snapshot was last built) and
`is_sample` (true until you run the real scraper). The time window (`--time`) is
chosen when you *run* `scraper.py`, not per-request.

Response shape:

```json
{
  "categories": { "bounty": [ { "title": "...", "url": "...", "subreddit": "...", "score": 12, "created_utc": 1737600000 } ] },
  "generated_at": "2026-07-13T10:00:00+00:00",
  "is_sample": false
}
```

## Design

Colors follow Reddit's own palette (`#FF4500` orange, `#0079D3` blue, `#1A1A1B` dark
background) so the tool feels native to where its data comes from. The favicon and
app icon are a custom red samurai kabuto helmet emblem with a gold coin — a "ronin
who hunts gigs for money" — built as a single scalable SVG (`public/icons/favicon.svg`)
and rendered to every PNG size a browser or OS needs.
