"""
GitHub Collector
Uses GitHub REST API (api.github.com) - Official, TOS-compliant.
REQUIRES GitHub Personal Access Token with 'repo' and 'read:discussion' scopes.
Create token at: https://github.com/settings/tokens

GitHub Search allows at most five AND/OR/NOT operators per query; keyword searches are batched.

REST /search/issues requires `is:issue` or `is:pull-request` (not `is:discussion`); we collect issues only unless GraphQL is added later.
"""

import os
import time
from typing import Dict, List, Any, Optional
import requests
from collectors.base import BaseCollector


class GithubCollector(BaseCollector):
    """Collector for GitHub issues (batched keyword search via REST)."""

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get('api_base', 'https://api.github.com')
        self.token = self.platform_config.get('token') or os.environ.get('GITHUB_TOKEN')
        self.per_page = self.platform_config.get('per_page', 100)
        self.max_results = self.platform_config.get('max_results', 1000)
        self.search_repos = self.platform_config.get('search_repos', [])
        # None = legacy config without top_starred_repos block (manual search_repos only)
        self._top_starred_block = self.platform_config.get('top_starred_repos')
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

            # Search API: some repos cannot be queried (private, opted out, etc.)
            if response.status_code == 422:
                try:
                    body = response.json()
                    detail = body.get("message", "")
                    errs = body.get("errors") or []
                    if errs and isinstance(errs[0], dict):
                        detail = errs[0].get("message", detail)
                except Exception:
                    detail = response.text[:200]
                self.logger.warning(f"GitHub API skipped request (422): {detail}")
                time.sleep(self.rate_limit)
                return {}

            response.raise_for_status()
            time.sleep(self.rate_limit)
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"GitHub API request failed: {e}")
            return {}

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
        return self.extract_target_system(text)

    def _extract_source_domain(self, quote: str) -> str:
        return self.extract_source_domain(quote)

    def _keyword_query_batches(self) -> List[str]:
        """Return search `q` fragments with at most five OR operators (GitHub Search limit)."""
        return [
            'analogy OR metaphor OR "like a" OR "similar to"',
            '"works like" OR "behaves like" OR "acts like" OR "think of it as"',
            'bug OR error OR exception OR debug OR fix',
            'architecture OR api OR database OR cache OR queue',
            'test OR deploy OR build OR refactor OR performance',
        ]

    def _search_repo_issues(self, repo: str) -> List[Dict[str, Any]]:
        """Merge batched keyword searches for one repo (REST search issues only)."""
        merged: Dict[Any, Dict[str, Any]] = {}
        for batch in self._keyword_query_batches():
            query = f"{batch} repo:{repo} is:issue"
            data = self._make_request(
                "search/issues", {"q": query, "per_page": self.per_page}
            )
            for item in data.get("items", []):
                iid = item.get("id")
                if iid is not None:
                    merged[iid] = item
            time.sleep(self.rate_limit)
        return list(merged.values())[: self.max_results]

    def _fetch_top_starred_repo_full_names(self, limit: int) -> List[str]:
        """Top repositories by stars via GET /search/repositories (paginate if limit > 100)."""
        cfg = self._top_starred_block if isinstance(self._top_starred_block, dict) else {}
        q = (cfg.get("repository_search_query") or "stars:>=1").strip()
        cap = max(1, min(int(limit), 1000))  # Search API returns at most 1000 results
        out: List[str] = []
        page = 1
        max_per_page = min(100, self.per_page)

        while len(out) < cap:
            per_page = min(max_per_page, cap - len(out))
            params: Dict[str, Any] = {
                "q": q,
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }
            data = self._make_request("search/repositories", params)
            items = data.get("items", [])
            if not items:
                if page == 1:
                    self.logger.warning(
                        "Repository search returned no items; check top_starred_repos.repository_search_query"
                    )
                break
            for repo in items:
                fn = repo.get("full_name")
                if fn:
                    out.append(fn)
                if len(out) >= cap:
                    break
            page += 1
            if len(items) < per_page:
                break

        self.logger.info(
            "Resolved %d repositories for keyword issue search (target %d)",
            len(out),
            cap,
        )
        return out[:cap]

    def collect(self) -> List[Dict[str, Any]]:
        """Collect GitHub issues matching analogy keywords (see module doc for REST limits)."""
        self.logger.info("Starting GitHub collection...")
        records = []

        all_repos: List[str] = []
        top = self._top_starred_block
        if top is None:
            # Legacy YAML without top_starred_repos: use only search_repos
            all_repos = list(dict.fromkeys([r for r in self.search_repos if r]))
        elif isinstance(top, dict) and top.get("enabled", True):
            n = int(top.get("count", 100))
            self.logger.info("Resolving top %d starred repositories via search API...", n)
            all_repos.extend(self._fetch_top_starred_repo_full_names(n))
            for r in self.search_repos:
                if r and r not in all_repos:
                    all_repos.append(r)
        else:
            # top_starred_repos present but disabled, or invalid block: manual list only
            all_repos = list(dict.fromkeys([r for r in self.search_repos if r]))

        if not all_repos:
            self.logger.warning("No repositories to search; enable top_starred_repos or set search_repos")

        for repo in all_repos:
            self.logger.info(f"Searching issues in {repo}...")
            try:
                for item in self._search_repo_issues(repo):
                    record = self._process_item(item, "issue")
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