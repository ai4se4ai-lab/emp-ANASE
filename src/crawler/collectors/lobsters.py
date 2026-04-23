"""
Lobsters Collector
Uses the official Lobsters JSON feed and search endpoint (lobste.rs).
Policy: Lobsters provides official JSON endpoints; no scraping of HTML required.
API details: https://lobste.rs/about#whats-the-json-api

Collected artifact types:
  - stories                  → source_type = 'story'
  - story comments           → source_type = 'comment'

Thread context normalization:
  Each comment carries `title` = "Comment on: <story title>" using the
  parent story URL which is included in the comment payload.

Rate note: Lobsters is a small community — keep rate_limit >= 1.0 s.
"""

import time
from typing import Any, Dict, List, Optional

import requests

from collectors.base import BaseCollector


_LOBSTERS_BASE = 'https://lobste.rs'


class LobstersCollector(BaseCollector):
    """Collector for Lobsters stories and comments via the JSON API."""

    PLATFORM = 'lobsters'

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.max_pages = int(self.platform_config.get('max_pages', 10))
        self.fetch_comments = bool(self.platform_config.get('fetch_comments', True))
        # Tag filters to request from /hottest.json and /newest.json
        self.tags = self.platform_config.get('tags', [
            'ai', 'programming', 'practices', 'tools',
        ])
        self.rate_limit = self.config['rate_limits'].get('lobsters', 1.0)

        self._session = requests.Session()
        self._session.headers['User-Agent'] = 'AnalogicalReasoningResearch/1.0 (academic)'
        # Short-term cache: story short_id -> title (for comment context)
        self._story_title_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(self.rate_limit)
            return resp.json()
        except requests.exceptions.RequestException as exc:
            self.logger.error("Lobsters request failed [%s]: %s", url, exc)
            return []

    def _fetch_story_title(self, short_id: str) -> str:
        if short_id in self._story_title_cache:
            return self._story_title_cache[short_id]
        data = self._get_json(f"{_LOBSTERS_BASE}/s/{short_id}.json") or {}
        title = data.get('title', '') if isinstance(data, dict) else ''
        self._story_title_cache[short_id] = title
        return title

    # ------------------------------------------------------------------ #
    # Record processors                                                    #
    # ------------------------------------------------------------------ #

    def _process_story(self, story: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = story.get('title', '')
        body = story.get('description', '')
        content = f"{title}\n{body}"

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        short_id = story.get('short_id', 'unknown')
        self._story_title_cache[short_id] = title

        return self.create_record(
            record_id=f"LB-{short_id}",
            source_type='story',
            url=story.get('short_id_url', f"{_LOBSTERS_BASE}/s/{short_id}"),
            archive_url='',
            title=title,
            author_handle=story.get('submitter_user', {}).get('username', 'anonymous'),
            post_date=story.get('created_at', ''),
            content=body,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(content),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=story.get('score', 0),
            upvotes=story.get('upvotes', 0),
            replies=story.get('comment_count', 0),
            views=0,
            verified_by='api',
        )

    def _process_comment(self, comment: Dict[str, Any],
                          parent_title: str, story_url: str) -> Optional[Dict[str, Any]]:
        content = comment.get('comment', '') or ''
        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        return self.create_record(
            record_id=f"LB-CMT-{comment.get('short_id', 'unknown')}",
            source_type='comment',
            url=comment.get('short_id_url', story_url),
            archive_url='',
            title=f"Comment on: {parent_title}",
            author_handle=comment.get('commenting_user', {}).get('username', 'anonymous'),
            post_date=comment.get('created_at', ''),
            content=content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(content),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=comment.get('score', 0),
            upvotes=comment.get('upvotes', 0),
            replies=0,
            views=0,
            verified_by='api',
        )

    # ------------------------------------------------------------------ #
    # Collection logic                                                      #
    # ------------------------------------------------------------------ #

    def _paginate_feed(self, feed: str) -> List[Dict[str, Any]]:
        """Paginate through a Lobsters feed (hottest or newest)."""
        stories: List[Dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            url = f"{_LOBSTERS_BASE}/{feed}.json"
            self.logger.info("Lobsters feed=%s page %d", feed, page)
            batch = self._get_json(url, params={'page': page})
            if not batch:
                break
            stories.extend(batch)
            if len(batch) < 25:  # Lobsters returns 25 per page by default
                break
        return stories

    def _paginate_tag(self, tag: str) -> List[Dict[str, Any]]:
        """Fetch stories for a specific tag."""
        stories: List[Dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            url = f"{_LOBSTERS_BASE}/t/{tag}.json"
            self.logger.info("Lobsters tag=%s page %d", tag, page)
            batch = self._get_json(url, params={'page': page})
            if not batch:
                break
            stories.extend(batch)
            if len(batch) < 25:
                break
        return stories

    def collect(self) -> List[Dict[str, Any]]:
        self.logger.info("Starting Lobsters collection...")
        records: List[Dict[str, Any]] = []
        seen_story_ids: set = set()

        # Collect from tag-specific feeds
        all_stories: List[Dict[str, Any]] = []
        for tag in self.tags:
            all_stories.extend(self._paginate_tag(tag))

        # De-duplicate stories before processing
        unique_stories: Dict[str, Dict[str, Any]] = {}
        for story in all_stories:
            sid = story.get('short_id')
            if sid and sid not in unique_stories:
                unique_stories[sid] = story

        for short_id, story in unique_stories.items():
            rec = self._process_story(story)
            if rec:
                records.append(rec)

            if self.fetch_comments:
                # Story detail endpoint includes inline comments array
                detail = self._get_json(
                    f"{_LOBSTERS_BASE}/s/{short_id}.json"
                )
                if isinstance(detail, dict):
                    story_title = detail.get('title', story.get('title', ''))
                    story_url = detail.get('short_id_url', '')
                    for comment in detail.get('comments', []):
                        c_rec = self._process_comment(comment, story_title, story_url)
                        if c_rec:
                            records.append(c_rec)

        self.logger.info("Lobsters collection complete. %d analogy records.", len(records))
        self.save_records(records, "lobsters_analogies.csv")
        return records


if __name__ == "__main__":
    collector = LobstersCollector()
    collector.collect()
