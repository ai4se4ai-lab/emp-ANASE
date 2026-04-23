"""
GitLab Collector
Uses the GitLab REST API v4 (gitlab.com/api/v4) — official, TOS-compliant.
API docs: https://docs.gitlab.com/ee/api/rest/

Project discovery strategy:
  1. Keyword search via GET /search?scope=projects to find SE/AI-related repos.
  2. Hard-coded `search_projects` list in config for known relevant projects.
  3. Issues in each discovered project are searched for analogy keywords.
  4. Top-voted issue notes (comments) are optionally fetched for more signal.

Requires GITLAB_TOKEN (personal access token) for >60 req/hr.
Token needs no special scopes for public project access.

Collected artifact types:
  - issues       → source_type = 'issue'
  - issue notes  → source_type = 'issue_note'
"""

import os
import time
from typing import Any, Dict, List, Optional

import requests

from collectors.base import BaseCollector


class GitlabCollector(BaseCollector):
    """Collector for GitLab public issues and comments via the REST API."""

    PLATFORM = 'gitlab'

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get('api_base', 'https://gitlab.com/api/v4')
        self.token = self.platform_config.get('token') or os.environ.get('GITLAB_TOKEN', '')
        self.per_page = int(self.platform_config.get('per_page', 100))
        self.max_pages = int(self.platform_config.get('max_pages', 10))
        self.max_projects = int(self.platform_config.get('max_projects', 30))
        self.fetch_notes = bool(self.platform_config.get('fetch_notes', True))
        self.search_projects: List[str] = self.platform_config.get('search_projects', [])
        self.project_search_terms: List[str] = self.platform_config.get(
            'project_search_terms', ['copilot', 'ai coding', 'llm', 'chatgpt']
        )
        self.rate_limit = self.config['rate_limits'].get('gitlab', 0.5)

        self._session = requests.Session()
        self._session.headers['User-Agent'] = 'AnalogicalReasoningResearch/1.0'
        if self.token:
            self._session.headers['PRIVATE-TOKEN'] = self.token

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        try:
            resp = self._session.get(url, params=params, timeout=30)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get('Retry-After', 60))
                self.logger.warning("GitLab rate limited. Waiting %ds...", retry_after)
                time.sleep(retry_after)
                return self._get(endpoint, params)

            if resp.status_code in (401, 403, 404):
                self.logger.warning("GitLab %d for %s", resp.status_code, url)
                return []

            resp.raise_for_status()
            time.sleep(self.rate_limit)
            return resp.json()
        except requests.exceptions.RequestException as exc:
            self.logger.error("GitLab request failed [%s]: %s", url, exc)
            return []

    def _paginate(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect all pages from a paginated GitLab list endpoint."""
        items: List[Dict[str, Any]] = []
        for page in range(1, self.max_pages + 1):
            params['page'] = page
            params['per_page'] = self.per_page
            batch = self._get(endpoint, params)
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            if len(batch) < self.per_page:
                break
        return items

    # ------------------------------------------------------------------ #
    # Project discovery                                                    #
    # ------------------------------------------------------------------ #

    def _discover_projects(self) -> List[str]:
        """
        Return a list of project ID-or-path strings.
        Combines config-listed search_projects with discovered projects via
        the /search?scope=projects endpoint.
        """
        project_ids: List[str] = list(self.search_projects)

        for term in self.project_search_terms:
            self.logger.info("Discovering GitLab projects matching '%s'...", term)
            results = self._paginate('search', {
                'scope': 'projects',
                'search': term,
                'order_by': 'stars',
                'sort': 'desc',
            })
            for proj in results:
                pid = str(proj.get('id', ''))
                if pid and pid not in project_ids:
                    project_ids.append(pid)
                if len(project_ids) >= self.max_projects:
                    break
            if len(project_ids) >= self.max_projects:
                break

        return project_ids[:self.max_projects]

    # ------------------------------------------------------------------ #
    # Record processors                                                    #
    # ------------------------------------------------------------------ #

    def _process_issue(self, issue: Dict[str, Any],
                        project_path: str) -> Optional[Dict[str, Any]]:
        title = issue.get('title', '')
        body = issue.get('description', '') or ''
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
            record_id=f"GL-{project_path.replace('/', '_')}-{issue.get('iid', 'unknown')}",
            source_type='issue',
            url=issue.get('web_url', ''),
            archive_url='',
            title=title,
            author_handle=(issue.get('author') or {}).get('username', 'anonymous'),
            post_date=issue.get('created_at', ''),
            content=body,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self.extract_target_domain(content),
            source_domain=self.extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=issue.get('upvotes', 0),
            upvotes=issue.get('upvotes', 0),
            replies=issue.get('user_notes_count', 0),
            views=0,
            verified_by='api',
        )

    def _process_note(self, note: Dict[str, Any],
                       issue_title: str, issue_url: str) -> Optional[Dict[str, Any]]:
        content = note.get('body', '') or ''
        if note.get('system', False):
            return None  # skip system notes (status changes etc.)

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        return self.create_record(
            record_id=f"GL-NOTE-{note.get('id', 'unknown')}",
            source_type='issue_note',
            url=issue_url,
            archive_url='',
            title=f"Comment on: {issue_title}",
            author_handle=(note.get('author') or {}).get('username', 'anonymous'),
            post_date=note.get('created_at', ''),
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
    # Issue search per project                                             #
    # ------------------------------------------------------------------ #

    def _search_issues(self, project_id: str) -> List[Dict[str, Any]]:
        """Search issues inside a single project for analogy keywords."""
        # GitLab /projects/:id/search supports issue scope with full-text query
        merged: Dict[Any, Dict[str, Any]] = {}
        keyword_batches = [
            'analogy OR metaphor',
            '"like a" OR "similar to"',
            '"junior dev" OR "black box"',
        ]
        for kw in keyword_batches:
            results = self._paginate(
                f"projects/{project_id}/search",
                {'scope': 'issues', 'search': kw},
            )
            for issue in results:
                iid = issue.get('iid')
                if iid is not None:
                    merged[iid] = issue
        return list(merged.values())

    # ------------------------------------------------------------------ #
    # Main collect                                                         #
    # ------------------------------------------------------------------ #

    def collect(self) -> List[Dict[str, Any]]:
        self.logger.info("Starting GitLab collection...")
        records: List[Dict[str, Any]] = []

        project_ids = self._discover_projects()
        self.logger.info("Processing %d GitLab projects...", len(project_ids))

        for pid in project_ids:
            self.logger.info("Searching issues in project %s...", pid)
            try:
                # Resolve namespace/path for logging
                proj_info = self._get(f"projects/{pid}")
                project_path = (proj_info or {}).get('path_with_namespace', pid) if isinstance(proj_info, dict) else str(pid)

                for issue in self._search_issues(pid):
                    rec = self._process_issue(issue, project_path)
                    if rec:
                        records.append(rec)

                    if self.fetch_notes:
                        iid = issue.get('iid')
                        if not iid:
                            continue
                        notes = self._paginate(
                            f"projects/{pid}/issues/{iid}/notes", {}
                        )
                        for note in notes:
                            n_rec = self._process_note(
                                note,
                                issue.get('title', ''),
                                issue.get('web_url', ''),
                            )
                            if n_rec:
                                records.append(n_rec)

            except Exception as exc:
                self.logger.error("Error processing project %s: %s", pid, exc)
                continue

        self.logger.info("GitLab collection complete. %d analogy records.", len(records))
        self.save_records(records, "gitlab_analogies.csv")
        return records


if __name__ == "__main__":
    collector = GitlabCollector()
    collector.collect()
