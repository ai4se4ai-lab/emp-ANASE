"""
GitHub Collector
Uses GitHub REST API (api.github.com) - Official, TOS-compliant.
REQUIRES GitHub Personal Access Token with 'repo' and 'read:discussion' scopes.
Create token at: https://github.com/settings/tokens
"""

import os
import time
import base64
from typing import Dict, List, Any, Optional
import requests
from base_collector import BaseCollector


class GithubCollector(BaseCollector):
    """Collector for GitHub Discussions and Issues."""

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get('api_base', 'https://api.github.com')
        self.token = self.platform_config.get('token') or os.environ.get('GITHUB_TOKEN')
        self.per_page = self.platform_config.get('per_page', 100)
        self.max_results = self.platform_config.get('max_results', 1000)
        self.search_repos = self.platform_config.get('search_repos', [])
        self.rate_limit = self.config['rate_limits'].get('github', 0.5)

        if not self.token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN environment variable.")

        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'AnalogicalReasoningResearch/1.0'
        }

    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict:
        """Make authenticated request to GitHub API."""
        url = f"{self.api_base}/{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 403:
                # Rate limit handling
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - int(time.time()), 60)
                self.logger.warning(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                return self._make_request(endpoint, params)

            response.raise_for_status()
            time.sleep(self.rate_limit)
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"GitHub API request failed: {e}")
            return {}

    def search_discussions(self, query: str) -> List[Dict]:
        """Search GitHub Discussions using GraphQL (fallback to REST search)."""
        # GitHub REST search API for discussions is limited; we use issue search with discussions
        params = {
            'q': f'{query} is:discussion',
            'per_page': self.per_page,
            'sort': 'updated',
            'order': 'desc'
        }

        data = self._make_request('search/issues', params)
        return data.get('items', [])

    def get_discussion_comments(self, repo: str, discussion_number: int) -> List[Dict]:
        """Fetch comments for a specific discussion."""
        # GitHub Discussions API requires GraphQL; using REST workaround
        endpoint = f"repos/{repo}/issues/{discussion_number}/comments"
        data = self._make_request(endpoint)
        return data if isinstance(data, list) else []

    def _process_item(self, item: Dict[str, Any], item_type: str = 'discussion') -> Optional[Dict[str, Any]]:
        """Process a GitHub discussion or issue."""
        title = item.get('title', '')
        body = item.get('body', '') or ''
        content = f"{title}\n{body}"

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        repo_name = item.get('repository_url', '').replace('https://api.github.com/repos/', '')

        return self.create_record(
            record_id=f"GH-{item.get('id', 'unknown')}",
            source_type=item_type,
            url=item.get('html_url', ''),
            archive_url='',
            title=title,
            author_handle=item.get('user', {}).get('login', 'anonymous'),
            post_date=item.get('created_at', ''),
            content=body,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self._extract_target_domain(content),
            source_domain=self._extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=item.get('reactions', {}).get('total_count', 0),
            upvotes=item.get('reactions', {}).get('+1', 0),
            replies=item.get('comments', 0),
            views=0,
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
        """Collect GitHub Discussions and Issues."""
        self.logger.info("Starting GitHub collection...")
        records = []

        # Search across configured repositories
        search_terms = ' OR '.join([
            'analogy', 'metaphor', '"like a"', '"similar to"', 
            '"junior dev"', '"autopilot"', '"black box"'
        ])

        for repo in self.search_repos:
            self.logger.info(f"Searching repository: {repo}")
            query = f"{search_terms} repo:{repo}"

            try:
                items = self.search_discussions(query)

                for item in items[:self.max_results]:
                    record = self._process_item(item, 'discussion')
                    if record:
                        records.append(record)

                time.sleep(self.rate_limit)

            except Exception as e:
                self.logger.error(f"Error searching {repo}: {e}")
                continue

        # Also search issues in popular agentic repos
        agent_repos = [
            "microsoft/vscode-jupyter",
            "github/copilot-cli-for-beginners",
            "getcursor/cursor",
            "anthropics/anthropic-cookbook"
        ]

        for repo in agent_repos:
            self.logger.info(f"Searching issues in {repo}...")
            query = f"{search_terms} repo:{repo} is:issue"
            params = {'q': query, 'per_page': self.per_page}

            try:
                data = self._make_request('search/issues', params)
                items = data.get('items', [])

                for item in items:
                    record = self._process_item(item, 'issue')
                    if record:
                        records.append(record)

            except Exception as e:
                self.logger.error(f"Error searching issues in {repo}: {e}")
                continue

        self.logger.info(f"GitHub collection complete. {len(records)} analogy records found.")
        self.save_records(records, "github_analogies.csv")
        return records


if __name__ == "__main__":
    collector = GithubCollector()
    collector.collect()