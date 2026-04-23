"""
Zenodo Collector
Uses Zenodo REST API (zenodo.org/api) - Official, TOS-compliant.
No authentication required for search; recommended for deposits.
"""

import time
from typing import Dict, List, Any, Optional
import requests
from collectors.base import BaseCollector


class ZenodoCollector(BaseCollector):
    """Collector for Zenodo records related to software engineering and AI."""

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get('api_base', 'https://zenodo.org/api')
        self.max_records = self.platform_config.get('max_records', 500)
        self.communities = self.platform_config.get('communities', [])
        self.query = self.platform_config.get('query', 'analogical reasoning software engineering')
        self.rate_limit = self.config['rate_limits'].get('zenodo', 0.5)

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """Make request to Zenodo API."""
        url = f"{self.api_base}/{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            time.sleep(self.rate_limit)
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Zenodo API request failed: {e}")
            return {'hits': {'hits': []}}

    def _process_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a Zenodo record."""
        metadata = record.get('metadata', {})
        title = metadata.get('title', '')
        description = metadata.get('description', '')
        content = f"{title}\n{description}"

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        creators = metadata.get('creators', [])
        author_name = creators[0].get('name', 'Unknown') if creators else 'Unknown'

        return self.create_record(
            record_id=f"ZN-{record.get('id', 'unknown')}",
            source_type='zenodo_record',
            url=record.get('links', {}).get('html', ''),
            archive_url=record.get('links', {}).get('doi', ''),
            title=title,
            author_handle=author_name,
            post_date=metadata.get('publication_date', ''),
            content=description,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self._extract_target_domain(content),
            source_domain=self._extract_source_domain(analogy_quote) if analogy_quote else '',
            sdlc_phase=sdlc_phase,
            engagement_score=record.get('stats', {}).get('downloads', 0),
            upvotes=0,
            replies=0,
            views=record.get('stats', {}).get('views', 0),
            verified_by='api'
        )

    def _extract_target_domain(self, text: str) -> str:
        text_lower = text.lower()
        agents = {
            'github copilot': 'GitHub Copilot',
            'copilot': 'GitHub Copilot',
            'cursor': 'Cursor',
            'claude code': 'Claude Code',
            'claude': 'Claude',
            'chatgpt': 'ChatGPT',
            'ai agent': 'Generic AI Agent'
        }
        for key, value in agents.items():
            if key in text_lower:
                return value
        return 'Unspecified AI Tool'

    def _extract_source_domain(self, quote: str) -> str:
        if not quote:
            return ''
        import re
        match = re.search(r'like a[n]?\s+([^,.;]+)', quote.lower())
        if match:
            return match.group(1).strip()
        return ''

    def collect(self) -> List[Dict[str, Any]]:
        """Collect records from Zenodo."""
        self.logger.info("Starting Zenodo collection...")
        records = []
        page = 1
        size = 100

        while len(records) < self.max_records:
            self.logger.info(f"Fetching page {page}...")

            params = {
                'q': self.query,
                'type': 'publication',
                'page': page,
                'size': size,
                'sort': 'mostrecent'
            }

            # Add community filter if specified
            if self.communities:
                params['communities'] = ','.join(self.communities)

            data = self._make_request('records', params)
            hits = data.get('hits', {}).get('hits', [])

            if not hits:
                break

            for record in hits:
                processed = self._process_record(record)
                if processed:
                    records.append(processed)

            if len(hits) < size:
                break

            page += 1

        self.logger.info(f"Zenodo collection complete. {len(records)} analogy records found.")
        self.save_records(records, "zenodo_analogies.csv")
        return records


if __name__ == "__main__":
    collector = ZenodoCollector()
    collector.collect()