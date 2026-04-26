"""
Hashnode Collector
Uses the Hashnode GraphQL API (gql.hashnode.com) — official, no auth required.
API explorer: https://gql.hashnode.com

Collected artifact types:
  - blog posts (publications) → source_type = 'post'
  - post replies/comments     → source_type = 'reply'

Discovery strategy: search the global feed with analogy + agent keyword
combinations, then walk pagination cursors.
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from collectors.base import BaseCollector


_SEARCH_QUERY = """
query SearchPosts($query: String!, $first: Int!, $after: String) {
  searchPostsOfHashnode(input: {query: $query, first: $first, after: $after}) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        brief
        content {
          markdown
        }
        url
        publishedAt
        views
        reactionCount
        responseCount
        author {
          username
        }
      }
    }
  }
}
"""


class HashnodeCollector(BaseCollector):
    """Collector for Hashnode blog posts via the GraphQL API."""

    PLATFORM = 'hashnode'

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_url = self.platform_config.get('api_url', 'https://gql.hashnode.com')
        self.per_page = int(self.platform_config.get('per_page', 20))
        self.max_pages = int(self.platform_config.get('max_pages', 25))
        self.rate_limit = self.config['rate_limits'].get('hashnode', 0.5)

        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'AnalogicalReasoningResearch/1.0',
        })

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _gql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self._session.post(
                self.api_url,
                json={'query': query, 'variables': variables},
                timeout=30,
            )
            resp.raise_for_status()
            time.sleep(self.rate_limit)
            return resp.json()
        except requests.exceptions.RequestException as exc:
            self.logger.error("Hashnode GQL request failed: %s", exc)
            return {}

    # ------------------------------------------------------------------ #
    # Record processors                                                    #
    # ------------------------------------------------------------------ #

    def _process_post(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        title = node.get('title', '')
        body = (node.get('content') or {}).get('markdown') or node.get('brief', '')
        content = f"{title}\n{body}"

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)
        username = (node.get('author') or {}).get('username', 'anonymous')

        return self.create_record(
            record_id=f"HN-{node.get('id', 'unknown')}",
            source_type='post',
            url=node.get('url', ''),
            archive_url='',
            title=title,
            author_handle=username,
            post_date=node.get('publishedAt', ''),
            content=body,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(content),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=node.get('reactionCount', 0),
            upvotes=node.get('reactionCount', 0),
            replies=node.get('responseCount', 0),
            views=node.get('views', 0),
            verified_by='api',
        )

    # ------------------------------------------------------------------ #
    # Collection logic                                                      #
    # ------------------------------------------------------------------ #

    def _build_search_queries(self) -> List[str]:
        """Combine analogy phrases with broad software-engineering context terms."""
        indicators = ['analogy', 'metaphor', 'like a', 'similar to', 'works like']
        contexts = [
            'bug', 'debugging', 'architecture', 'api', 'database',
            'cache', 'testing', 'deployment', 'refactoring', 'performance',
            'microservices', 'git', 'docker',
        ]
        return [f'"{context}" "{indicator}"' for context in contexts for indicator in indicators[:3]]

    def collect(self) -> List[Dict[str, Any]]:
        self.logger.info("Starting Hashnode collection...")
        records: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for search_query in self._build_search_queries():
            cursor: Optional[str] = None
            for page in range(1, self.max_pages + 1):
                self.logger.info("Hashnode query='%s' page %d", search_query, page)
                variables: Dict[str, Any] = {
                    'query': search_query,
                    'first': self.per_page,
                    'after': cursor,
                }
                data = self._gql(_SEARCH_QUERY, variables)
                result = (data.get('data') or {}).get('searchPostsOfHashnode', {})
                edges = result.get('edges', [])

                for edge in edges:
                    node = edge.get('node') or {}
                    post_id = node.get('id')
                    if post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)

                    rec = self._process_post(node)
                    if rec:
                        records.append(rec)

                page_info = result.get('pageInfo', {})
                if not page_info.get('hasNextPage'):
                    break
                cursor = page_info.get('endCursor')

        self.logger.info("Hashnode collection complete. %d analogy records.", len(records))
        self.save_records(records, "hashnode_analogies.csv")
        return records


if __name__ == "__main__":
    collector = HashnodeCollector()
    collector.collect()
