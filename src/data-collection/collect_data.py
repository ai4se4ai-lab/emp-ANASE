"""
Analogical Reasoning in Agentic SE — Data Collection Framework
===============================================================
Replicates the data collection methodology from:
  "An Empirical Study on Analogical Reasoning in Agentic Software Engineering"

Platforms: Stack Overflow, Reddit, GitHub, Zenodo
           (Discord requires manual export — see discord_manual_guide.md)

All collection respects official API rate limits and terms of service.
Authentication tokens are loaded from environment variables / .env file.

Usage:
    python collect_data.py [--platforms all|stackoverflow|reddit|github|zenodo]
                           [--max-results N]
                           [--output-dir ./output]

Outputs (CSV per platform + combined):
    output/stackoverflow_posts.csv
    output/reddit_posts.csv
    output/github_posts.csv
    output/zenodo_records.csv
    output/combined_dataset.csv
    output/collection_summary.csv
"""

import os
import sys
import time
import json
import logging
import argparse
import hashlib
import re
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import pandas as pd
from dotenv import load_dotenv

# ── optional PRAW for Reddit ──────────────────────────────────────────────────
try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("collection.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants matching the paper's search strategy (Section III-B)
# ─────────────────────────────────────────────────────────────────────────────
ANALOGY_KEYWORDS = [
    "analogy", "metaphor", "like a", "similar to",
    "as if", "resembles", "just like", "think of it as",
]

AGENT_KEYWORDS = [
    "AI agent", "Copilot", "Cursor", "Claude Code",
    "github copilot", "copilot agent", "agentic", "LLM agent",
    "ai coding", "code generation",
]

# Paper's date range: Oct 2025 – Feb 2026 (Unix timestamps)
DATE_FROM_UNIX = 1727740800   # 2024-10-01 (broadened for reproducibility)
DATE_TO_UNIX   = 1740873600   # 2025-03-01

# Stack Overflow tags from the paper
SO_TAGS = ["github-copilot", "cursor-ide", "ai-code-generation", "llm", "chatgpt"]

# Reddit subreddits from the paper
REDDIT_SUBS = [
    "ChatGPTCoding", "cursor", "ClaudeAI", "programming",
    "softwareengineering", "MachineLearning",
]

# GitHub repos / orgs to search
GITHUB_REPOS = [
    "microsoft/vscode-jupyter",
    "github/copilot-cli-for-beginners",
]

ZENODO_COMMUNITIES = ["software-engineering", "ai-agents", "llm"]

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def safe_get(url: str, params: dict = None, headers: dict = None,
             max_retries: int = 5, backoff: float = 2.0) -> Optional[dict]:
    """GET with exponential back-off; returns JSON or None."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = backoff ** attempt
                log.warning("Rate-limited (%s). Retrying in %.0fs…", url, wait)
                time.sleep(wait)
                continue
            if resp.status_code in (401, 403):
                log.error("Auth error %s for %s", resp.status_code, url)
                return None
            log.warning("HTTP %s for %s", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            log.warning("Request error: %s (attempt %d)", exc, attempt + 1)
            time.sleep(backoff ** attempt)
    return None


def contains_analogy_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in ANALOGY_KEYWORDS)


def contains_agent_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in AGENT_KEYWORDS)


def is_relevant(text: str) -> bool:
    """Paper's two-filter criterion: must mention analogy AND agent terms."""
    return contains_analogy_keyword(text) and contains_agent_keyword(text)


def stable_id(platform: str, raw_id) -> str:
    return hashlib.md5(f"{platform}:{raw_id}".encode()).hexdigest()[:12]


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Stack Overflow  (Stack Exchange API v2.3 — no key needed, 300 req/day)
# ─────────────────────────────────────────────────────────────────────────────

def collect_stackoverflow(max_results: int = 500) -> pd.DataFrame:
    """
    Uses the public Stack Exchange API.
    Key improves quota: set SO_API_KEY env var if available.
    """
    api_key = os.getenv("SO_API_KEY", "")
    base_url = "https://api.stackexchange.com/2.3/search/advanced"
    records = []

    for tag in SO_TAGS:
        for query in ANALOGY_KEYWORDS[:4]:           # top 4 keywords
            page = 1
            while True:
                params = {
                    "order": "desc",
                    "sort": "relevance",
                    "q": f"{query} agent OR copilot OR cursor",
                    "tagged": tag,
                    "site": "stackoverflow",
                    "filter": "!nNPvSNPI0g",         # include body excerpt
                    "pagesize": 100,
                    "page": page,
                    "fromdate": DATE_FROM_UNIX,
                    "todate": DATE_TO_UNIX,
                }
                if api_key:
                    params["key"] = api_key

                data = safe_get(base_url, params=params)
                if not data:
                    break

                items = data.get("items", [])
                for item in items:
                    title = item.get("title", "")
                    body  = strip_html(item.get("body", ""))
                    full  = f"{title} {body}"
                    if not is_relevant(full):
                        continue

                    records.append({
                        "platform":          "stackoverflow",
                        "post_id":           item.get("question_id"),
                        "stable_id":         stable_id("stackoverflow", item.get("question_id")),
                        "title":             title,
                        "body_excerpt":      body[:500],
                        "url":               item.get("link", ""),
                        "author":            item.get("owner", {}).get("display_name", ""),
                        "author_id":         item.get("owner", {}).get("user_id", ""),
                        "score":             item.get("score", 0),
                        "view_count":        item.get("view_count", 0),
                        "answer_count":      item.get("answer_count", 0),
                        "tags":              "|".join(item.get("tags", [])),
                        "creation_date":     datetime.fromtimestamp(
                                                item.get("creation_date", 0), tz=timezone.utc
                                             ).isoformat(),
                        "is_answered":       item.get("is_answered", False),
                        "analogy_keyword":   next((kw for kw in ANALOGY_KEYWORDS
                                                   if kw in full.lower()), ""),
                        "agent_keyword":     next((kw.lower() for kw in AGENT_KEYWORDS
                                                   if kw.lower() in full.lower()), ""),
                        "search_tag":        tag,
                        "collected_at":      datetime.utcnow().isoformat(),
                    })

                    if len(records) >= max_results:
                        break

                if not data.get("has_more") or len(records) >= max_results:
                    break

                page += 1
                # Stack Exchange: 30 requests/second without key; be polite
                time.sleep(1.0 if not api_key else 0.2)

            if len(records) >= max_results:
                break
        if len(records) >= max_results:
            break

    df = pd.DataFrame(records).drop_duplicates(subset=["post_id"]) if records else pd.DataFrame()
    log.info("Stack Overflow: %d relevant posts collected", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. Reddit  (via PRAW or public JSON API fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _reddit_praw(max_results: int) -> list:
    """Primary Reddit collector using PRAW (requires app credentials)."""
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT",
                             "AnalogyCrawler/1.0 (academic research)"),
        username=os.getenv("REDDIT_USERNAME", ""),
        password=os.getenv("REDDIT_PASSWORD", ""),
    )

    records = []
    query = "analogy OR metaphor OR \"like a\" " + \
            "AND (copilot OR cursor OR \"claude code\" OR \"ai agent\")"

    for sub_name in REDDIT_SUBS:
        try:
            sub = reddit.subreddit(sub_name)
            for submission in sub.search(query, limit=200, sort="relevance"):
                title = submission.title or ""
                body  = submission.selftext or ""
                full  = f"{title} {body}"

                if not is_relevant(full):
                    continue

                records.append({
                    "platform":      "reddit",
                    "post_id":       submission.id,
                    "stable_id":     stable_id("reddit", submission.id),
                    "title":         title,
                    "body_excerpt":  body[:500],
                    "url":           f"https://reddit.com{submission.permalink}",
                    "subreddit":     sub_name,
                    "author":        str(submission.author) if submission.author else "[deleted]",
                    "score":         submission.score,
                    "upvote_ratio":  submission.upvote_ratio,
                    "num_comments":  submission.num_comments,
                    "flair":         submission.link_flair_text or "",
                    "creation_date": datetime.fromtimestamp(
                                        submission.created_utc, tz=timezone.utc
                                     ).isoformat(),
                    "analogy_keyword": next((kw for kw in ANALOGY_KEYWORDS
                                            if kw in full.lower()), ""),
                    "agent_keyword":   next((kw.lower() for kw in AGENT_KEYWORDS
                                            if kw.lower() in full.lower()), ""),
                    "collected_at":  datetime.utcnow().isoformat(),
                })

                if len(records) >= max_results:
                    return records

            time.sleep(0.5)
        except Exception as exc:
            log.warning("Reddit PRAW error for r/%s: %s", sub_name, exc)

    return records


def _reddit_json(max_results: int) -> list:
    """Fallback: public subreddit JSON (no auth, limited to ~25 posts/call)."""
    records = []
    headers = {"User-Agent": "AnalogyCrawler/1.0 academic"}

    for sub_name in REDDIT_SUBS:
        after = None
        fetched = 0
        while fetched < 200:
            params = {"limit": 25, "t": "year"}
            if after:
                params["after"] = after

            url  = f"https://www.reddit.com/r/{sub_name}/search.json"
            qstr = ("analogy OR metaphor "
                    "AND (copilot OR cursor OR \"ai agent\")")
            params["q"] = qstr
            params["restrict_sr"] = 1

            data = safe_get(url, params=params, headers=headers)
            if not data:
                break

            children = data.get("data", {}).get("children", [])
            if not children:
                break

            for child in children:
                item  = child.get("data", {})
                title = item.get("title", "")
                body  = item.get("selftext", "")
                full  = f"{title} {body}"

                if not is_relevant(full):
                    fetched += 1
                    continue

                created = item.get("created_utc", 0)
                records.append({
                    "platform":      "reddit",
                    "post_id":       item.get("id"),
                    "stable_id":     stable_id("reddit", item.get("id")),
                    "title":         title,
                    "body_excerpt":  body[:500],
                    "url":           f"https://reddit.com{item.get('permalink','')}",
                    "subreddit":     sub_name,
                    "author":        item.get("author", ""),
                    "score":         item.get("score", 0),
                    "upvote_ratio":  item.get("upvote_ratio", 0),
                    "num_comments":  item.get("num_comments", 0),
                    "flair":         item.get("link_flair_text", ""),
                    "creation_date": datetime.fromtimestamp(
                                        created, tz=timezone.utc
                                     ).isoformat() if created else "",
                    "analogy_keyword": next((kw for kw in ANALOGY_KEYWORDS
                                            if kw in full.lower()), ""),
                    "agent_keyword":   next((kw.lower() for kw in AGENT_KEYWORDS
                                            if kw.lower() in full.lower()), ""),
                    "collected_at":  datetime.utcnow().isoformat(),
                })
                fetched += 1

                if len(records) >= max_results:
                    return records

            after = data.get("data", {}).get("after")
            if not after:
                break
            time.sleep(1.5)   # public endpoint: be polite

    return records


def collect_reddit(max_results: int = 500) -> pd.DataFrame:
    cid = os.getenv("REDDIT_CLIENT_ID", "")
    if PRAW_AVAILABLE and cid:
        log.info("Reddit: using PRAW (authenticated)")
        records = _reddit_praw(max_results)
    else:
        log.info("Reddit: using public JSON fallback (limited results)")
        records = _reddit_json(max_results)

    df = pd.DataFrame(records).drop_duplicates(subset=["post_id"]) if records else pd.DataFrame()
    log.info("Reddit: %d relevant posts collected", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. GitHub  (REST API v3 — requires GITHUB_TOKEN for higher rate limits)
# ─────────────────────────────────────────────────────────────────────────────

def _gh_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _gh_check_rate() -> None:
    """Pause if close to rate limit."""
    data = safe_get("https://api.github.com/rate_limit", headers=_gh_headers())
    if not data:
        return
    core = data.get("resources", {}).get("search", {})
    remaining = core.get("remaining", 99)
    reset_ts   = core.get("reset", time.time() + 60)
    if remaining < 3:
        wait = max(reset_ts - time.time() + 5, 5)
        log.info("GitHub rate limit low — sleeping %.0fs", wait)
        time.sleep(wait)


def collect_github(max_results: int = 400) -> pd.DataFrame:
    """
    Searches GitHub Issues + Discussions via the code-search & issue-search APIs.
    For Discussions (GraphQL), falls back to REST issue search.
    """
    records = []
    headers = _gh_headers()

    # ── A) Issue search across all repos ─────────────────────────────────────
    analogy_terms = "analogy OR metaphor OR \"like a\" OR \"similar to\""
    agent_terms   = "copilot OR cursor OR \"claude code\" OR \"ai agent\""
    search_query  = f"{analogy_terms} {agent_terms} is:issue"

    page = 1
    while len(records) < max_results:
        _gh_check_rate()
        data = safe_get(
            "https://api.github.com/search/issues",
            params={"q": search_query, "per_page": 100, "page": page,
                    "sort": "updated", "order": "desc"},
            headers=headers,
        )
        if not data:
            break

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            title = item.get("title", "")
            body  = item.get("body", "") or ""
            full  = f"{title} {body}"

            if not is_relevant(full):
                continue

            repo_url = item.get("repository_url", "")
            repo_name = repo_url.replace("https://api.github.com/repos/", "")

            records.append({
                "platform":       "github",
                "post_id":        item.get("id"),
                "stable_id":      stable_id("github", item.get("id")),
                "title":          title,
                "body_excerpt":   body[:500],
                "url":            item.get("html_url", ""),
                "repo":           repo_name,
                "author":         item.get("user", {}).get("login", ""),
                "author_id":      item.get("user", {}).get("id", ""),
                "state":          item.get("state", ""),
                "comments":       item.get("comments", 0),
                "reactions_total": item.get("reactions", {}).get("total_count", 0),
                "labels":         "|".join(
                                    lbl.get("name", "") for lbl in item.get("labels", [])
                                  ),
                "is_pull_request": "pull_request" in item,
                "creation_date":  item.get("created_at", ""),
                "updated_date":   item.get("updated_at", ""),
                "analogy_keyword": next((kw for kw in ANALOGY_KEYWORDS
                                         if kw in full.lower()), ""),
                "agent_keyword":   next((kw.lower() for kw in AGENT_KEYWORDS
                                         if kw.lower() in full.lower()), ""),
                "collected_at":   datetime.utcnow().isoformat(),
            })

            if len(records) >= max_results:
                break

        total_count = data.get("total_count", 0)
        if page * 100 >= min(total_count, 1000):   # GitHub caps at 1000
            break
        page += 1
        time.sleep(1.0)   # search API: 30 requests/min

    # ── B) Specific repos from the paper ─────────────────────────────────────
    for repo in GITHUB_REPOS:
        _gh_check_rate()
        data = safe_get(
            f"https://api.github.com/repos/{repo}/issues",
            params={"state": "all", "per_page": 100},
            headers=headers,
        )
        if not data:
            continue
        for item in data:
            title = item.get("title", "")
            body  = item.get("body", "") or ""
            full  = f"{title} {body}"
            if not is_relevant(full):
                continue
            existing_ids = {r["post_id"] for r in records}
            if item.get("id") in existing_ids:
                continue
            records.append({
                "platform":        "github",
                "post_id":         item.get("id"),
                "stable_id":       stable_id("github", item.get("id")),
                "title":           title,
                "body_excerpt":    body[:500],
                "url":             item.get("html_url", ""),
                "repo":            repo,
                "author":          item.get("user", {}).get("login", ""),
                "author_id":       item.get("user", {}).get("id", ""),
                "state":           item.get("state", ""),
                "comments":        item.get("comments", 0),
                "reactions_total": item.get("reactions", {}).get("total_count", 0),
                "labels":          "|".join(
                                     lbl.get("name", "") for lbl in item.get("labels", [])
                                   ),
                "is_pull_request": "pull_request" in item,
                "creation_date":   item.get("created_at", ""),
                "updated_date":    item.get("updated_at", ""),
                "analogy_keyword": next((kw for kw in ANALOGY_KEYWORDS
                                          if kw in full.lower()), ""),
                "agent_keyword":   next((kw.lower() for kw in AGENT_KEYWORDS
                                          if kw.lower() in full.lower()), ""),
                "collected_at":    datetime.utcnow().isoformat(),
            })
        time.sleep(0.5)

    df = pd.DataFrame(records).drop_duplicates(subset=["post_id"]) if records else pd.DataFrame()
    log.info("GitHub: %d relevant posts collected", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 4. Zenodo  (public REST API — no auth needed for metadata)
# ─────────────────────────────────────────────────────────────────────────────

def collect_zenodo(max_results: int = 100) -> pd.DataFrame:
    """
    Searches Zenodo for workshop papers / technical reports matching
    the paper's keywords. Open API, no token required for metadata.
    """
    records = []
    base_url = "https://zenodo.org/api/records"
    queries = [
        "analogical reasoning agentic software engineering",
        "analogy AI agent developer communication",
        "LLM analogy code generation",
        "copilot cursor analogy metaphor developer",
    ]

    for query in queries:
        page = 1
        while len(records) < max_results:
            data = safe_get(
                base_url,
                params={
                    "q":        query,
                    "sort":     "mostrecent",
                    "page":     page,
                    "size":     50,
                    "type":     "publication",
                    "access_right": "open",
                },
            )
            if not data:
                break

            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                meta      = hit.get("metadata", {})
                title     = meta.get("title", "")
                desc      = meta.get("description", "") or ""
                keywords  = " ".join(meta.get("keywords", []))
                full      = f"{title} {desc} {keywords}"

                records.append({
                    "platform":        "zenodo",
                    "post_id":         hit.get("id"),
                    "stable_id":       stable_id("zenodo", hit.get("id")),
                    "title":           title,
                    "description":     desc[:500],
                    "url":             hit.get("links", {}).get("html", ""),
                    "doi":             meta.get("doi", ""),
                    "publication_type": meta.get("publication_type", ""),
                    "resource_type":   meta.get("resource_type", {}).get("type", ""),
                    "creators":        "; ".join(
                                         c.get("name", "") for c in meta.get("creators", [])
                                       ),
                    "keywords":        keywords,
                    "journal":         meta.get("journal", {}).get("title", ""),
                    "publication_date": meta.get("publication_date", ""),
                    "access_right":    meta.get("access_right", ""),
                    "download_count":  hit.get("stats", {}).get("downloads", 0),
                    "view_count":      hit.get("stats", {}).get("views", 0),
                    "version":         meta.get("version", ""),
                    "license":         meta.get("license", {}).get("id", ""),
                    "analogy_keyword": next((kw for kw in ANALOGY_KEYWORDS
                                            if kw in full.lower()), ""),
                    "agent_keyword":   next((kw.lower() for kw in AGENT_KEYWORDS
                                            if kw.lower() in full.lower()), ""),
                    "is_relevant":     is_relevant(full),
                    "search_query":    query,
                    "collected_at":    datetime.utcnow().isoformat(),
                })

                if len(records) >= max_results:
                    break

            total = data.get("hits", {}).get("total", 0)
            if page * 50 >= total:
                break
            page += 1
            time.sleep(0.5)

        if len(records) >= max_results:
            break

    df = pd.DataFrame(records).drop_duplicates(subset=["post_id"]) if records else pd.DataFrame()
    relevant = int(df["is_relevant"].sum()) if not df.empty and "is_relevant" in df.columns else 0
    log.info("Zenodo: %d records collected (%d relevant)", len(df), relevant)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 5. Combine + Annotate
# ─────────────────────────────────────────────────────────────────────────────

def combine_datasets(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merges all platform DataFrames into one unified dataset with a
    harmonised schema. Adds filtering-flag columns used in the paper.
    """
    pieces = []
    for platform, df in dfs.items():
        if df.empty:
            continue
        df = df.copy()
        df["platform"] = platform
        # Unified text column for downstream analysis
        text_col = "body_excerpt" if "body_excerpt" in df.columns else \
                   "description" if "description" in df.columns else "title"
        df["text_for_analysis"] = df["title"].fillna("") + " " + \
                                   df[text_col].fillna("")
        pieces.append(df)

    if not pieces:
        return pd.DataFrame()

    combined = pd.concat(pieces, ignore_index=True, sort=False)

    # ── Relevance scoring ───────────────────────────────────────────────────
    def relevance_score(text: str) -> float:
        """Simple keyword density score (0–1) used as proxy for relevance."""
        text = text.lower()
        a_hits = sum(1 for kw in ANALOGY_KEYWORDS if kw in text)
        g_hits = sum(1 for kw in AGENT_KEYWORDS   if kw.lower() in text)
        return round(min((a_hits + g_hits) / (len(ANALOGY_KEYWORDS) + len(AGENT_KEYWORDS)), 1.0), 3)

    combined["relevance_score"] = combined["text_for_analysis"].apply(relevance_score)
    combined["passes_dual_filter"] = (
        combined["text_for_analysis"].apply(contains_analogy_keyword) &
        combined["text_for_analysis"].apply(contains_agent_keyword)
    )

    # ── Analogy category heuristic (mirrors paper's 4 categories) ──────────
    structural_kw  = ["stack", "tree", "architecture", "layer", "structure",
                      "hierarchy", "foundation", "pipeline"]
    functional_kw  = ["tool", "drill", "bit", "instrument", "switch",
                      "skill", "function", "autocomplete"]
    process_kw     = ["engineer", "intern", "colleague", "team", "collaborate",
                      "workflow", "junior", "review", "pair"]
    crossdomain_kw = ["lottery", "autopilot", "renovate", "babysit",
                      "amnesia", "temperature", "cruise control"]

    def classify_analogy(text: str) -> str:
        text = text.lower()
        scores = {
            "structural":   sum(1 for kw in structural_kw  if kw in text),
            "functional":   sum(1 for kw in functional_kw  if kw in text),
            "process":      sum(1 for kw in process_kw     if kw in text),
            "cross_domain": sum(1 for kw in crossdomain_kw if kw in text),
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "unknown"

    combined["predicted_analogy_type"] = combined["text_for_analysis"].apply(classify_analogy)

    # ── SDLC phase heuristic ────────────────────────────────────────────────
    phase_kw = {
        "requirements": ["requirement", "spec", "user story", "backlog"],
        "design":       ["design", "architect", "diagram", "schema", "uml"],
        "development":  ["implement", "code", "develop", "write", "feature"],
        "code_review":  ["review", "pr ", "pull request", "merge", "diff"],
        "debugging":    ["debug", "bug", "error", "fix", "crash", "trace"],
        "testing":      ["test", "unit test", "coverage", "assert", "mock"],
    }

    def detect_phase(text: str) -> str:
        text = text.lower()
        for phase, kws in phase_kw.items():
            if any(kw in text for kw in kws):
                return phase
        return "unknown"

    combined["predicted_sdlc_phase"] = combined["text_for_analysis"].apply(detect_phase)

    return combined


# ─────────────────────────────────────────────────────────────────────────────
# 6. Reporting
# ─────────────────────────────────────────────────────────────────────────────

def generate_summary(dfs: dict[str, pd.DataFrame], combined: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for platform, df in dfs.items():
        rows.append({
            "platform":            platform,
            "raw_collected":       len(df),
            "passes_dual_filter":  int(df["passes_dual_filter"].sum())
                                   if "passes_dual_filter" in df.columns
                                   else "n/a",
        })

    if not combined.empty:
        rows.append({
            "platform":           "COMBINED",
            "raw_collected":      len(combined),
            "passes_dual_filter": int(combined["passes_dual_filter"].sum()),
        })

    summary = pd.DataFrame(rows)
    log.info("\n%s", summary.to_string(index=False))
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 7. Save helpers
# ─────────────────────────────────────────────────────────────────────────────

def save(df: pd.DataFrame, filename: str) -> None:
    if df.empty:
        log.warning("No data to save for %s", filename)
        return
    path = OUTPUT_DIR / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    log.info("Saved %d rows → %s", len(df), path)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Demo mode — generates synthetic records to verify the pipeline end-to-end
#    when API credentials are not available.
# ─────────────────────────────────────────────────────────────────────────────

DEMO_POSTS = [
    # (platform, title, body)
    ("stackoverflow",
     "How to reason about GitHub Copilot agent like a junior developer?",
     "I'm trying to understand why Copilot agent sometimes misses edge cases. "
     "I use the analogy that it's similar to a junior developer who writes "
     "tests that look comprehensive but miss corner cases. Is this a useful metaphor?"),
    ("stackoverflow",
     "Cursor AI agent is like an autopilot — is that a fair analogy?",
     "When I use Cursor in agentic mode I treat it like autopilot but my colleague "
     "says that's wrong because you still need to review everything. Similar to "
     "adaptive cruise control — hands on wheel?"),
    ("stackoverflow",
     "Understanding Claude Code context window — stack analogy",
     "The agent's memory works like a stack — last context in, first context out. "
     "Is this analogy for ai-code-generation accurate for Claude Code?"),
    ("stackoverflow",
     "Copilot skills are like drill bits — functional analogy explanation",
     "A general-purpose drill is useful but specialized attachments make it powerful. "
     "Skills work the same way as swapping drill bits for different jobs with ai agent."),
    ("stackoverflow",
     "Temperature parameter analogy for LLM agents",
     "I use the 'temperature lottery' analogy to explain stochastic LLM behavior to my team. "
     "Is there a better metaphor for github-copilot randomness?"),
    ("reddit",
     "Using analogies to understand AI agents — what works for you?",
     "I've been thinking of Claude Code like a very enthusiastic junior developer. "
     "The analogy helps me remember to double-check everything rather than blindly accepting. "
     "What analogies do you use for agentic coding tools?"),
    ("reddit",
     "Cursor agent mode is like babysitting a junior dev with amnesia",
     "Every time I fire up Cursor agent I'm not getting a copilot, I'm getting barely-functioning "
     "autocomplete with vibes. The analogy of junior developer with amnesia really fits. "
     "Similar to dragging an AI intern."),
    ("reddit",
     "The 'two engineers' analogy from VS Code Jupyter is spot on",
     "Imagine two engineers working together to address a bug. This analogy for AI agent collaboration "
     "captures why shared context matters so much with Claude Code and GitHub Copilot."),
    ("reddit",
     "Analogical mismatch: the autopilot framing is dangerous for AI agents",
     "When I treated Cursor like an autopilot I kept making mistakes. It isn't autopilot — "
     "it's more like adaptive cruise control. Similar to power tools, you still need hands on."),
    ("reddit",
     "Cross-domain analogy: renovating a house with Copilot agent",
     "I compared the agent's refactoring to renovating a house while keeping the foundation. "
     "The metaphor was so compelling I missed that Claude Code had changed the interface contract!"),
    ("github",
     "Add analogy-aware explanation mode to agent responses",
     "Feature request: when a developer provides an analogy ('think of this agent as a junior developer'), "
     "the AI agent (Copilot, Cursor) should frame its uncertainty using that metaphor. "
     "Similar to how a junior dev would ask for clarification."),
    ("github",
     "Document: AI Ready wiki — two-engineer analogy for agent collaboration",
     "This PR adds documentation using the two-engineer collaboration analogy to explain "
     "how github copilot agent requires shared mental models, similar to pair programming."),
    ("github",
     "Bug: agent sycophancy amplified by self-deprecating analogies",
     "When I joked that the AI agent was 'like a confused intern', Cursor adopted that framing "
     "to justify a wrong answer. The analogy made the error harder to catch. Copilot has similar issue."),
    ("zenodo",
     "Analogical Reasoning in Human-AI Collaborative Software Engineering",
     "This workshop paper examines how developers use structural, functional, process, and "
     "cross-domain analogies when communicating with AI agents such as GitHub Copilot and Claude Code. "
     "We find functional analogies are most effective during debugging phases."),
    ("zenodo",
     "Empirical Study on Developer Mental Models for Agentic Coding Tools",
     "We surveyed 52 developers about analogy usage with AI agents. Similar to prior work on "
     "program comprehension metaphors, we find that analogies improve critical thinking but "
     "can introduce analogical complacency when too compelling."),
]


def generate_demo_data() -> dict[str, pd.DataFrame]:
    """Creates small but realistic DataFrames to verify the full pipeline."""
    import random, hashlib
    random.seed(42)
    by_platform: dict[str, list] = {}

    for i, (platform, title, body) in enumerate(DEMO_POSTS):
        raw_id = f"demo_{i:04d}"
        full   = f"{title} {body}"
        row = {
            "platform":      platform,
            "post_id":       raw_id,
            "stable_id":     stable_id(platform, raw_id),
            "title":         title,
            "body_excerpt":  body[:500],
            "url":           f"https://example.com/{platform}/{raw_id}",
            "author":        f"demo_user_{i % 5}",
            "score":         random.randint(1, 150),
            "creation_date": "2025-11-15T10:00:00+00:00",
            "analogy_keyword": next((kw for kw in ANALOGY_KEYWORDS if kw in full.lower()), ""),
            "agent_keyword":   next((kw.lower() for kw in AGENT_KEYWORDS if kw.lower() in full.lower()), ""),
            "collected_at":  datetime.utcnow().isoformat(),
            # platform-specific extras
            "tags" if platform == "stackoverflow" else
            "subreddit" if platform == "reddit" else
            "repo" if platform == "github" else "doi":
                "github-copilot" if platform == "stackoverflow" else
                "ChatGPTCoding"  if platform == "reddit" else
                "microsoft/vscode-copilot" if platform == "github" else
                f"10.5281/zenodo.demo{i}",
        }
        by_platform.setdefault(platform, []).append(row)

    result = {}
    for platform, rows in by_platform.items():
        result[platform] = pd.DataFrame(rows)
    return result



def main():
    parser = argparse.ArgumentParser(
        description="Collect analogical-reasoning discussion data for SE research"
    )
    parser.add_argument(
        "--platforms",
        default="all",
        help="Comma-separated list: stackoverflow,reddit,github,zenodo  (default: all)",
    )
    parser.add_argument("--max-results", type=int, default=300,
                        help="Max items to collect per platform (default: 300)")
    parser.add_argument("--output-dir", default="output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--demo", action="store_true",
                        help="Run with synthetic demo data (no API keys needed)")
    args = parser.parse_args()

    global OUTPUT_DIR
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Demo mode ──────────────────────────────────────────────────────────
    if args.demo:
        log.info("═" * 60)
        log.info("DEMO MODE — using synthetic data (no API calls)")
        log.info("═" * 60)
        dfs = generate_demo_data()
        for platform, df in dfs.items():
            save(df, f"{platform}_posts.csv")
        combined = combine_datasets(dfs)
        combined["passes_dual_filter"] = (
            combined["text_for_analysis"].apply(contains_analogy_keyword) &
            combined["text_for_analysis"].apply(contains_agent_keyword)
        )
        save(combined, "combined_dataset.csv")
        filtered = combined[combined["passes_dual_filter"]].copy()
        save(filtered, "combined_filtered.csv")
        summary = generate_summary(dfs, combined)
        save(summary, "collection_summary.csv")
        log.info("Demo complete — check the output/ directory.")
        return

    # ── Live collection ────────────────────────────────────────────────────
    platforms = (
        ["stackoverflow", "reddit", "github", "zenodo"]
        if args.platforms.lower() == "all"
        else [p.strip().lower() for p in args.platforms.split(",")]
    )

    log.info("═" * 60)
    log.info("Analogy SE Data Collector — platforms: %s", platforms)
    log.info("Max results per platform: %d", args.max_results)
    log.info("═" * 60)

    dfs: dict[str, pd.DataFrame] = {}

    if "stackoverflow" in platforms:
        log.info("── Stack Overflow ──────────────────────────────────────")
        dfs["stackoverflow"] = collect_stackoverflow(args.max_results)
        save(dfs["stackoverflow"], "stackoverflow_posts.csv")

    if "reddit" in platforms:
        log.info("── Reddit ──────────────────────────────────────────────")
        dfs["reddit"] = collect_reddit(args.max_results)
        save(dfs["reddit"], "reddit_posts.csv")

    if "github" in platforms:
        log.info("── GitHub ──────────────────────────────────────────────")
        dfs["github"] = collect_github(args.max_results)
        save(dfs["github"], "github_posts.csv")

    if "zenodo" in platforms:
        log.info("── Zenodo ──────────────────────────────────────────────")
        dfs["zenodo"] = collect_zenodo(args.max_results)
        save(dfs["zenodo"], "zenodo_records.csv")

    # Filter: only DataFrames that actually have rows
    non_empty = {k: v for k, v in dfs.items() if not v.empty}

    if non_empty:
        log.info("── Combining datasets ──────────────────────────────────")
        combined = combine_datasets(non_empty)

        # Apply dual-filter before saving combined
        combined["passes_dual_filter"] = (
            combined["text_for_analysis"].apply(contains_analogy_keyword) &
            combined["text_for_analysis"].apply(contains_agent_keyword)
        )
        save(combined, "combined_dataset.csv")

        filtered = combined[combined["passes_dual_filter"]].copy()
        save(filtered, "combined_filtered.csv")

        summary = generate_summary(dfs, combined)
        save(summary, "collection_summary.csv")

        log.info("═" * 60)
        log.info("Collection complete.")
        log.info("  Total collected  : %d", len(combined))
        log.info("  Passes dual-filter: %d", combined["passes_dual_filter"].sum())
        log.info("  Analogy types    : %s",
                 combined["predicted_analogy_type"].value_counts().to_dict())
        log.info("  SDLC phases      : %s",
                 combined["predicted_sdlc_phase"].value_counts().to_dict())
        log.info("═" * 60)
    else:
        log.warning("No data collected. Check API credentials and network access.")
        log.info("Tip: run with --demo to test the pipeline without credentials.")


if __name__ == "__main__":
    main()
