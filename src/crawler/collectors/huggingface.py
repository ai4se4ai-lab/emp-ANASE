"""
Hugging Face Collector
Uses Hugging Face Hub API (huggingface.co/api) - Official, TOS-compliant.
Token is optional for public data, but recommended for higher limits.
"""

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from collectors.base import BaseCollector


class HuggingfaceCollector(BaseCollector):
    """Collector for Hugging Face Hub community discussions."""

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.api_base = self.platform_config.get("api_base", "https://huggingface.co/api")
        self.token = self.platform_config.get("token") or os.environ.get("HUGGINGFACE_TOKEN", "")
        self.per_page = self.platform_config.get("per_page", 20)
        self.max_results = self.platform_config.get("max_results", 300)
        self.max_repositories = self.platform_config.get("max_repositories", 120)
        self.per_term_repo_limit = self.platform_config.get("per_term_repo_limit", 20)
        self.repo_types = self.platform_config.get("repo_types", ["models", "datasets", "spaces"])
        self.search_query = self.platform_config.get(
            "repository_search_query",
            "copilot cursor claude chatgpt coding assistant",
        )
        self.search_repos = self.platform_config.get("search_repos", [])
        self.rate_limit = self.config["rate_limits"].get("huggingface", 0.5)

        self.headers = {"User-Agent": "AnalogicalReasoningResearch/1.0"}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    @staticmethod
    def _search_terms(raw_query: str) -> List[str]:
        """Split repository search query into individual terms."""
        terms = [token.strip() for token in raw_query.replace(",", " ").split() if token.strip()]
        # Keep order but deduplicate
        return list(dict.fromkeys(terms))

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make request to Hugging Face API and return JSON payload."""
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            if response.status_code == 404:
                # Some discussions disappear between list and detail calls; skip silently.
                return {}
            if response.status_code == 429:
                self.logger.warning("Rate limited by Hugging Face API. Waiting before retry.")
                time.sleep(max(1.0, self.rate_limit * 4))
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            time.sleep(self.rate_limit)
            return response.json()
        except requests.exceptions.RequestException as exc:
            self.logger.error(f"Hugging Face API request failed: {exc}")
            return {}

    def _resolve_target_repositories(self) -> List[Dict[str, str]]:
        """
        Resolve candidate repositories to inspect for discussions.
        Returns: [{"repo_type": "models|datasets|spaces", "repo_id": "owner/name"}, ...]
        """
        repos: Dict[str, Dict[str, str]] = {}
        search_limit = max(1, min(self.per_term_repo_limit, 100))
        terms = self._search_terms(self.search_query)
        if not terms:
            terms = [""]

        for repo_type in self.repo_types:
            for term in terms:
                params = {
                    "sort": "downloads",
                    "direction": -1,
                    "limit": search_limit,
                    "full": False,
                }
                if term:
                    params["search"] = term
                items = self._make_request(repo_type, params=params)
                if not isinstance(items, list):
                    continue

                for item in items:
                    repo_id = item.get("id") or item.get("modelId")
                    if not repo_id:
                        continue
                    key = f"{repo_type}:{repo_id}"
                    repos[key] = {"repo_type": repo_type, "repo_id": repo_id}

        for full_name in self.search_repos:
            if "/" not in full_name:
                continue
            for repo_type in self.repo_types:
                key = f"{repo_type}:{full_name}"
                if key not in repos:
                    repos[key] = {"repo_type": repo_type, "repo_id": full_name}

        return list(repos.values())[: self.max_repositories]

    def _extract_target_domain(self, text: str) -> str:
        text_lower = text.lower()
        agents = {
            "github copilot": "GitHub Copilot",
            "copilot": "GitHub Copilot",
            "cursor": "Cursor",
            "claude code": "Claude Code",
            "claude": "Claude",
            "chatgpt": "ChatGPT",
            "gpt-4": "GPT-4",
            "gpt-5": "GPT-5",
            "ai agent": "Generic AI Agent",
        }
        for key, value in agents.items():
            if key in text_lower:
                return value
        return "Unspecified AI Tool"

    def _extract_source_domain(self, quote: str) -> str:
        if not quote:
            return ""
        import re

        match = re.search(r"like a[n]?\s+([^,.;]+)", quote.lower())
        if match:
            return match.group(1).strip()
        return ""

    def _discussion_body_from_details(self, details: Dict[str, Any]) -> str:
        """Extract discussion body text from detail payload events."""
        events = details.get("events", [])
        if not isinstance(events, list):
            return ""

        chunks: List[str] = []
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "comment":
                continue
            data = event.get("data") or {}
            latest = data.get("latest") if isinstance(data, dict) else None
            if isinstance(latest, dict):
                raw = latest.get("raw")
                if isinstance(raw, str) and raw.strip():
                    chunks.append(raw.strip())

        return "\n\n".join(chunks).strip()

    def _fetch_discussion_details(self, repo_type: str, repo_id: str, discussion_num: Any) -> Dict[str, Any]:
        endpoint = f"{repo_type}/{repo_id}/discussions/{discussion_num}"
        data = self._make_request(endpoint)
        return data if isinstance(data, dict) else {}

    def _process_discussion(
        self, repo_type: str, repo_id: str, discussion: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        discussion_num = discussion.get("num") or discussion.get("id") or "unknown"
        details = self._fetch_discussion_details(repo_type, repo_id, discussion_num)
        title = discussion.get("title", "") or details.get("title", "") or ""
        body = self._discussion_body_from_details(details)
        content = "\n".join([piece for piece in [title, body] if piece]).strip()
        if not content or self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        created_at = discussion.get("createdAt", "")
        if isinstance(created_at, (int, float)):
            created_at = datetime.fromtimestamp(created_at).isoformat()

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content) or ""
        sdlc_phase = self.determine_sdlc_phase(content)
        author = discussion.get("author") or details.get("author")
        author_handle = ""
        if isinstance(author, dict):
            author_handle = author.get("name") or author.get("fullname") or "anonymous"
        elif isinstance(author, str):
            author_handle = author

        url = f"https://huggingface.co/{repo_id}/discussions/{discussion_num}"
        if repo_type == "datasets":
            url = f"https://huggingface.co/datasets/{repo_id}/discussions/{discussion_num}"
        elif repo_type == "spaces":
            url = f"https://huggingface.co/spaces/{repo_id}/discussions/{discussion_num}"

        return self.create_record(
            record_id=f"HF-{repo_type[:2].upper()}-{repo_id}-{discussion_num}",
            source_type=f"{repo_type}_discussion",
            url=url,
            archive_url="",
            title=title,
            author_handle=author_handle or "anonymous",
            post_date=created_at,
            content=body or content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote,
            analogy_confidence=confidence,
            target_domain=self._extract_target_domain(content),
            source_domain=self._extract_source_domain(analogy_quote),
            sdlc_phase=sdlc_phase,
            engagement_score=discussion.get("upvotes", 0),
            upvotes=discussion.get("upvotes", 0),
            replies=discussion.get("numComments", 0),
            views=0,
            verified_by="api",
        )

    def _collect_repo_discussions(self, repo_type: str, repo_id: str) -> List[Dict[str, Any]]:
        endpoint = f"{repo_type}/{repo_id}/discussions"
        params = {"limit": self.per_page}
        data = self._make_request(endpoint, params=params)
        if isinstance(data, dict):
            discussions = data.get("discussions", [])
        elif isinstance(data, list):
            discussions = data
        else:
            return []

        records: List[Dict[str, Any]] = []
        for discussion in discussions:
            if len(records) >= self.max_results:
                break
            record = self._process_discussion(repo_type, repo_id, discussion)
            if record:
                records.append(record)
        return records

    def collect(self) -> List[Dict[str, Any]]:
        """Collect Hugging Face discussions matching analogical language."""
        self.logger.info("Starting Hugging Face collection...")
        repos = self._resolve_target_repositories()
        self.logger.info(f"Resolved {len(repos)} Hugging Face repositories for scanning")

        all_records: List[Dict[str, Any]] = []
        for repo in repos:
            if len(all_records) >= self.max_results:
                break

            repo_type = repo["repo_type"]
            repo_id = repo["repo_id"]
            self.logger.info(f"Fetching discussions for {repo_type}/{repo_id}")
            try:
                repo_records = self._collect_repo_discussions(repo_type, repo_id)
                remaining = self.max_results - len(all_records)
                all_records.extend(repo_records[:remaining])
            except Exception as exc:
                self.logger.error(f"Failed collecting discussions for {repo_type}/{repo_id}: {exc}")
                continue

        self.logger.info(f"Hugging Face collection complete. {len(all_records)} analogy records found.")
        self.save_records(all_records, "huggingface_analogies.csv")
        return all_records


if __name__ == "__main__":
    collector = HuggingfaceCollector()
    collector.collect()
