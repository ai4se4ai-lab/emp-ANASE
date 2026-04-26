"""
Hacker News Collector
Uses the official Algolia HN Search API (hn.algolia.com/api) — the
authoritative full-text search endpoint provided under Y Combinator's
official Algolia partnership. No authentication required.
API docs: https://hn.algolia.com/api

Firebase item API (hacker-news.firebaseio.com/v0) is used only to resolve
parent thread context for comments (title of the parent story).

Collected artifact types:
  - stories (Ask HN / Show HN / submissions)  → source_type = 'story'
  - comments                                   → source_type = 'comment'

Thread context normalization:
  Each comment record carries `thread_context` = title of the parent story,
  which is fetched once per story and cached in memory.
"""

import time
from typing import Any, Dict, List, Optional

import requests

from collectors.base import BaseCollector


_ALGOLIA_BASE = 'https://hn.algolia.com/api/v1'
_FIREBASE_ITEM = 'https://hacker-news.firebaseio.com/v0/item/{}.json'


class HackernewsCollector(BaseCollector):
    """Collector for Hacker News stories and comments via the Algolia API."""

    PLATFORM = 'hackernews'

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.per_page = int(self.platform_config.get('per_page', 20))
        self.max_pages = int(self.platform_config.get('max_pages', 20))
        self.fetch_comments = bool(self.platform_config.get('fetch_comments', True))
        self.rate_limit = self.config['rate_limits'].get('hackernews', 0.3)

        self._session = requests.Session()
        self._session.headers['User-Agent'] = 'AnalogicalReasoningResearch/1.0'
        # Parent-story title cache: story_id -> title string
        self._story_title_cache: Dict[int, str] = {}

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _algolia_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = 'search' if params.get('query') else 'search_by_date'
        url = f"{_ALGOLIA_BASE}/{endpoint}"
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(self.rate_limit)
            return resp.json()
        except requests.exceptions.RequestException as exc:
            self.logger.error("HN Algolia request failed: %s", exc)
            return {}

    def _fetch_story_title(self, story_id: int) -> str:
        """Resolve the title of a parent story via Firebase (cached)."""
        if story_id in self._story_title_cache:
            return self._story_title_cache[story_id]
        try:
            resp = self._session.get(
                _FIREBASE_ITEM.format(story_id), timeout=10
            )
            resp.raise_for_status()
            title = (resp.json() or {}).get('title', '')
            time.sleep(self.rate_limit)
        except Exception:
            title = ''
        self._story_title_cache[story_id] = title
        return title

    # ------------------------------------------------------------------ #
    # Record processors                                                    #
    # ------------------------------------------------------------------ #

    def _process_hit(self, hit: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single Algolia hit (story or comment)."""
        is_comment = hit.get('_tags', []) and 'comment' in hit.get('_tags', [])

        # Resolve content and context
        if is_comment:
            content = hit.get('comment_text', '') or ''
            parent_id = hit.get('story_id') or hit.get('parent_id')
            parent_title = self._fetch_story_title(parent_id) if parent_id else ''
            title = f"Comment on: {parent_title}"
            thread_context = parent_title
            record_id = f"HNS-CMT-{hit.get('objectID', 'unknown')}"
            source_type = 'comment'
        else:
            title = hit.get('title', '')
            content = hit.get('story_text', '') or ''
            thread_context = title
            record_id = f"HNS-{hit.get('objectID', 'unknown')}"
            source_type = 'story'

        # Combine title + body for detection
        full_text = f"{title}\n{content}"
        if self.should_exclude(full_text):
            return None

        has_analogy, confidence = self.contains_analogy(full_text)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(full_text)
        analogy_quote = self.extract_analogy_quote(full_text)
        sdlc_phase = self.determine_sdlc_phase(full_text)

        url = hit.get('url') or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

        return self.create_record(
            record_id=record_id,
            source_type=source_type,
            url=url,
            archive_url='',
            title=title,
            author_handle=hit.get('author', 'anonymous'),
            post_date=hit.get('created_at', ''),
            content=content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(full_text),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=hit.get('points', 0) or 0,
            upvotes=hit.get('points', 0) or 0,
            replies=hit.get('num_comments', 0) or 0,
            views=0,
            verified_by='api',
        )

    # ------------------------------------------------------------------ #
    # Collection logic                                                      #
    # ------------------------------------------------------------------ #

    def _build_queries(self) -> List[str]:
        """Build broad SE analogy queries for HN search."""
        indicators = ['analogy', 'metaphor', '"like a"', '"similar to"', '"works like"']
        contexts = [
            'bug', 'debugging', 'architecture', 'api', 'database',
            'cache', 'testing', 'deployment', 'refactoring', 'performance',
        ]
        return [f'{indicator} {context}' for indicator in indicators for context in contexts]

    def _search_type(self, query: str, tags: str) -> List[Dict[str, Any]]:
        """Paginate through Algolia search results for a single query + tag filter."""
        hits: List[Dict[str, Any]] = []
        for page in range(self.max_pages):
            self.logger.info("HN Algolia query='%s' tags=%s page %d", query, tags, page)
            data = self._algolia_search({
                'query': query,
                'tags': tags,
                'hitsPerPage': self.per_page,
                'page': page,
            })
            batch = data.get('hits', [])
            hits.extend(batch)
            if len(batch) < self.per_page or page >= data.get('nbPages', 0) - 1:
                break
        return hits

    def collect(self) -> List[Dict[str, Any]]:
        self.logger.info("Starting Hacker News collection...")
        records: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for query in self._build_queries():
            for tags in ['story', 'comment'] if self.fetch_comments else ['story']:
                for hit in self._search_type(query, tags):
                    oid = hit.get('objectID')
                    if oid in seen_ids:
                        continue
                    seen_ids.add(oid)
                    rec = self._process_hit(hit)
                    if rec:
                        records.append(rec)

        self.logger.info("Hacker News collection complete. %d analogy records.", len(records))
        self.save_records(records, "hackernews_analogies.csv")
        return records


if __name__ == "__main__":
    collector = HackernewsCollector()
    collector.collect()
