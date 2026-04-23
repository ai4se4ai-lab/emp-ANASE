"""
Stack Overflow Collector
Uses Stack Exchange API (api.stackexchange.com) - Official, TOS-compliant.
Requires API key for higher quota (optional but recommended).
"""

import time
import urllib.parse
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import requests
from base_collector import BaseCollector


class StackoverflowCollector(BaseCollector):
    """Collector for Stack Overflow posts using Stack Exchange API."""

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get('api_base', 'https://api.stackexchange.com/2.3')
        self.api_key = self.platform_config.get('api_key') or os.environ.get('STACKOVERFLOW_API_KEY', '')
        self.page_size = self.platform_config.get('page_size', 100)
        self.max_pages = self.platform_config.get('max_pages', 50)
        self.tags = self.platform_config.get('tags', ['github-copilot', 'cursor-ide'])
        self.rate_limit = self.config['rate_limits'].get('stackoverflow', 0.05)

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict:
        """Make authenticated request to Stack Exchange API."""
        url = f"{self.api_base}/{endpoint}"

        if self.api_key:
            params['key'] = self.api_key
        params['site'] = 'stackoverflow'
        params['pagesize'] = self.page_size

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            time.sleep(self.rate_limit)
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            return {'items': [], 'has_more': False}

    def _process_post(self, post: Dict[str, Any], post_type: str) -> Optional[Dict[str, Any]]:
        """Process a single post and extract analogy data."""
        content = post.get('body', '') or post.get('title', '')

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        # Extract target/source domains from quote if possible
        target_domain = self._extract_target_domain(content)
        source_domain = self._extract_source_domain(analogy_quote) if analogy_quote else ''

        post_id = post.get('question_id') or post.get('answer_id')
        question_id = post.get('question_id') or post.get('parent_id')

        return self.create_record(
            record_id=f"SO-{post_id}",
            source_type=post_type,
            url=f"https://stackoverflow.com/questions/{question_id}" if question_id else '',
            archive_url=(
                f"https://webcache.googleusercontent.com/search?q=cache:https://stackoverflow.com/questions/{question_id}"
                if question_id else ''
            ),
            title=post.get('title', ''),
            author_handle=post.get('owner', {}).get('display_name', 'anonymous'),
            post_date=datetime.fromtimestamp(post.get('creation_date', 0)).isoformat() if post.get('creation_date') else '',
            content=content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=target_domain,
            source_domain=source_domain,
            sldc_phase=sdlc_phase,
            engagement_score=post.get('score', 0),
            upvotes=post.get('score', 0),
            replies=post.get('answer_count', 0) if post_type == 'question' else 0,
            views=post.get('view_count', 0),
            verified_by='api'
        )

    def _fetch_question_answers(self, question_ids: List[int]) -> List[Dict[str, Any]]:
        """Fetch answers for a batch of question IDs."""
        if not question_ids:
            return []

        endpoint = f"questions/{';'.join(str(qid) for qid in question_ids)}/answers"
        params = {
            'sort': 'votes',
            'order': 'desc',
            'filter': 'withbody'
        }
        data = self._make_request(endpoint, params)
        return data.get('items', [])

    def _extract_target_domain(self, text: str) -> str:
        """Extract which AI agent/tool is being discussed."""
        text_lower = text.lower()
        agents = {
            'github copilot': 'GitHub Copilot',
            'copilot': 'GitHub Copilot',
            'cursor': 'Cursor',
            'claude code': 'Claude Code',
            'claude': 'Claude',
            'chatgpt': 'ChatGPT',
            'gpt-4': 'GPT-4',
            'ai agent': 'Generic AI Agent'
        }
        for key, value in agents.items():
            if key in text_lower:
                return value
        return 'Unspecified AI Tool'

    def _extract_source_domain(self, quote: str) -> str:
        """Extract source domain from analogy quote."""
        if not quote:
            return ''
        # Simple heuristic: look for "like a X" or "like an X"
        import re
        match = re.search(r'like a[n]?\s+([^,.;]+)', quote.lower())
        if match:
            return match.group(1).strip()
        return ''

    def collect(self) -> List[Dict[str, Any]]:
        """Collect questions and answers from Stack Overflow."""
        self.logger.info("Starting Stack Overflow collection...")
        records = []
        seen_post_ids = set()

        # Query each tag independently. `tagged=a;b` is logical AND in Stack Exchange API,
        # which is too restrictive for this use case and can severely limit recall.
        for tag in self.tags:
            self.logger.info(f"Collecting Stack Overflow posts for tag '{tag}'")

            for page in range(1, self.max_pages + 1):
                self.logger.info(f"Fetching questions for tag '{tag}' page {page}/{self.max_pages}")

                params = {
                    'tagged': tag,
                    'sort': 'creation',
                    'order': 'desc',
                    'page': page,
                    'filter': 'withbody'
                }

                data = self._make_request('questions', params)
                questions = data.get('items', [])
                if not questions:
                    break

                question_ids = []
                for question in questions:
                    question_id = question.get('question_id')
                    if question_id:
                        question_ids.append(question_id)

                    record = self._process_post(question, 'question')
                    if record and record['record_id'] not in seen_post_ids:
                        seen_post_ids.add(record['record_id'])
                        records.append(record)

                # Fetch top-voted answers for these questions for additional relevant signal.
                answers = self._fetch_question_answers(question_ids)
                question_titles = {
                    q.get('question_id'): q.get('title', '')
                    for q in questions if q.get('question_id')
                }
                for answer in answers:
                    parent_id = answer.get('question_id')
                    if parent_id:
                        answer['parent_id'] = parent_id
                        answer['title'] = question_titles.get(parent_id, '')

                    record = self._process_post(answer, 'answer')
                    if record and record['record_id'] not in seen_post_ids:
                        seen_post_ids.add(record['record_id'])
                        records.append(record)

                if not data.get('has_more', False):
                    break

        self.logger.info(f"Stack Overflow collection complete. {len(records)} analogy records found.")
        self.save_records(records, "stackoverflow_analogies.csv")
        return records


if __name__ == "__main__":
    collector = StackoverflowCollector()
    collector.collect()