"""
DEV Community (dev.to) Collector
Uses the official DEV.to REST API — TOS-compliant for academic research.
API docs: https://developers.forem.com/api

Public endpoints require no auth.  An API key (DEVTO_API_KEY) raises the
rate limit from ~10 req/min to 1 000 req/min.

Collected artifact types:
  - articles (posts)        → source_type = 'article'
  - article comments        → source_type = 'comment'
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from collectors.base import BaseCollector


class DevtoCollector(BaseCollector):
    """Collector for DEV Community articles and comments via the Forem API."""

    PLATFORM = 'devto'

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get('api_base', 'https://dev.to/api')
        self.api_key = self.platform_config.get('api_key') or os.environ.get('DEVTO_API_KEY', '')
        self.per_page = min(int(self.platform_config.get('per_page', 30)), 30)
        self.max_pages = int(self.platform_config.get('max_pages', 50))
        self.fetch_comments = bool(self.platform_config.get('fetch_comments', True))
        self.tags = self.platform_config.get('tags', [
            'ai', 'machinelearning', 'github', 'programming',
            'copilot', 'chatgpt', 'llm',
        ])
        self.rate_limit = self.config['rate_limits'].get('devto', 0.5)

        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'AnalogicalReasoningResearch/1.0'})
        if self.api_key:
            self._session.headers['api-key'] = self.api_key

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(self.rate_limit)
            return resp.json()
        except requests.exceptions.RequestException as exc:
            self.logger.error("DEV.to request failed [%s]: %s", url, exc)
            return []

    # ------------------------------------------------------------------ #
    # Record processors                                                    #
    # ------------------------------------------------------------------ #

    def _process_article(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = article.get('title', '')
        body = article.get('body_markdown') or article.get('description', '')
        content = f"{title}\n{body}"

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)
        slug = article.get('slug', '')
        username = (article.get('user') or {}).get('username', 'anonymous')
        url = article.get('url') or f"https://dev.to/{username}/{slug}"

        return self.create_record(
            record_id=f"DV-{article.get('id', slug)}",
            source_type='article',
            url=url,
            archive_url='',
            title=title,
            author_handle=username,
            post_date=article.get('published_at', ''),
            content=body,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(content),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=article.get('public_reactions_count', 0),
            upvotes=article.get('positive_reactions_count', 0),
            replies=article.get('comments_count', 0),
            views=article.get('page_views_count', 0),
            verified_by='api',
        )

    def _process_comment(self, comment: Dict[str, Any], article_title: str,
                          article_url: str) -> Optional[Dict[str, Any]]:
        body = comment.get('body_html') or ''
        # Strip minimal HTML tags for content matching
        import re
        content = re.sub(r'<[^>]+>', ' ', body).strip()
        if not content:
            return None

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)
        username = (comment.get('user') or {}).get('username', 'anonymous')

        return self.create_record(
            record_id=f"DV-CMT-{comment.get('id_code', comment.get('id', 'unknown'))}",
            source_type='comment',
            url=article_url,
            archive_url='',
            title=f"Comment on: {article_title}",
            author_handle=username,
            post_date=comment.get('created_at', ''),
            content=content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(content),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=0,
            upvotes=0,
            replies=0,
            views=0,
            verified_by='api',
        )

    # ------------------------------------------------------------------ #
    # Collection logic                                                      #
    # ------------------------------------------------------------------ #

    def _fetch_articles_for_tag(self, tag: str) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            self.logger.info("DEV.to tag='%s' page %d/%d", tag, page, self.max_pages)
            batch = self._get('articles', {'tag': tag, 'per_page': self.per_page, 'page': page})
            if not batch:
                break
            articles.extend(batch)
            if len(batch) < self.per_page:
                break
        return articles

    def _fetch_comments(self, article_id: int) -> List[Dict[str, Any]]:
        return self._get('comments', {'a_id': article_id}) or []

    def collect(self) -> List[Dict[str, Any]]:
        self.logger.info("Starting DEV Community collection...")
        records: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for tag in self.tags:
            for article in self._fetch_articles_for_tag(tag):
                article_id = article.get('id')
                if article_id in seen_ids:
                    continue
                seen_ids.add(article_id)

                record = self._process_article(article)
                if record:
                    records.append(record)

                if self.fetch_comments and article_id:
                    for comment in self._fetch_comments(article_id):
                        c_rec = self._process_comment(
                            comment,
                            article.get('title', ''),
                            article.get('url', ''),
                        )
                        if c_rec:
                            records.append(c_rec)

        self.logger.info("DEV Community collection complete. %d analogy records.", len(records))
        self.save_records(records, "devto_analogies.csv")
        return records


if __name__ == "__main__":
    collector = DevtoCollector()
    collector.collect()
