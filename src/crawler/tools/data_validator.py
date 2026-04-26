"""
Data Validation Module
Verifies that collected data is authentic, URLs are valid, and content matches sources.
This is critical for ensuring research integrity and ICSE compliance.
"""

import logging
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd
import requests
from tqdm import tqdm


class DataValidator:
    """Validate collected data for authenticity and completeness."""

    def __init__(self, timeout: int = 10, rate_limit: float = 0.5):
        self.timeout = timeout
        self.rate_limit = rate_limit
        self.logger = logging.getLogger('validator')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AnalogicalReasoningResearch/1.0 (Data Validation)'
        })

    def _check_url(self, url: str) -> Tuple[bool, int, str]:
        """
        Check if URL is accessible.
        Returns: (is_accessible, status_code, error_message)
        """
        if not url or pd.isna(url):
            return False, 0, "Empty URL"

        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            time.sleep(self.rate_limit)

            if response.status_code == 200:
                return True, 200, "OK"
            elif response.status_code == 429:
                return False, 429, "Rate limited"
            elif response.status_code == 404:
                return False, 404, "Not found"
            else:
                # Try GET if HEAD fails
                response = self.session.get(url, timeout=self.timeout)
                time.sleep(self.rate_limit)
                return response.status_code == 200, response.status_code, response.reason

        except requests.exceptions.Timeout:
            return False, 0, "Timeout"
        except requests.exceptions.ConnectionError:
            return False, 0, "Connection error"
        except Exception as e:
            return False, 0, str(e)

    def _check_github_discussion_exists(self, url: str) -> Tuple[bool, str]:
        """Verify GitHub discussion number exists."""
        match = re.search(r'/discussions/(\d+)', url)
        if not match:
            return False, "Not a discussion URL"

        discussion_num = match.group(1)
        is_valid, status, msg = self._check_url(url)

        if not is_valid and status == 404:
            return False, f"Discussion #{discussion_num} does not exist"

        return is_valid, msg

    def _check_reddit_post_exists(self, url: str) -> Tuple[bool, str]:
        """Verify Reddit post ID exists."""
        match = re.search(r'/comments/(\w+)/', url)
        if not match:
            return False, "Not a Reddit post URL"

        post_id = match.group(1)
        is_valid, status, msg = self._check_url(url)

        if not is_valid and status == 404:
            return False, f"Post ID {post_id} does not exist"

        return is_valid, msg

    def _check_stackoverflow_post_exists(self, url: str) -> Tuple[bool, str]:
        """Verify Stack Overflow question ID exists."""
        match = re.search(r'/questions/(\d+)/', url)
        if not match:
            return False, "Not a Stack Overflow question URL"

        qid = match.group(1)
        is_valid, status, msg = self._check_url(url)

        if not is_valid and status == 404:
            return False, f"Question {qid} does not exist"

        return is_valid, msg

    # ------------------------------------------------------------------ #
    # Thread-integrity helpers for new sources                             #
    # ------------------------------------------------------------------ #

    def _check_thread_context(self, record: Dict[str, Any]) -> List[str]:
        """
        Validate thread-context fields for comment/note records from
        platforms that carry a parent-thread relationship.

        Returns a list of warning strings (empty = no issues found).
        """
        warnings: List[str] = []
        source_type = record.get('source_type', '')
        title = record.get('title', '') or ''

        if source_type in ('comment', 'issue_note', 'reply'):
            # These should always have a "Comment on: ..." title
            if not title.startswith('Comment on:'):
                warnings.append(
                    f"Comment record missing thread context in title field "
                    f"(got: '{title[:60]}')"
                )
            parent_ref = title.replace('Comment on:', '').strip()
            if not parent_ref:
                warnings.append("Thread context title is empty after 'Comment on:' prefix")

        return warnings

    def _check_new_source_url(self, url: str, platform: str) -> Tuple[bool, str]:
        """
        Lightweight structural URL check for new sources before hitting the network.
        Returns (structurally_valid, reason).
        """
        if not url:
            return False, "Empty URL"

        parsed = urlparse(url)
        expected_hosts = {
            'devto': ('dev.to',),
            'hashnode': ('hashnode.com', 'hashnode.dev'),
            'hackernews': ('news.ycombinator.com', 'hn.algolia.com'),
            'lobsters': ('lobste.rs',),
            'gitlab': ('gitlab.com',),
        }
        if platform in expected_hosts:
            if not any(parsed.netloc.endswith(h) for h in expected_hosts[platform]):
                return False, (
                    f"URL host '{parsed.netloc}' unexpected for platform '{platform}'. "
                    f"Expected one of: {expected_hosts[platform]}"
                )
        return True, "OK"

    def _verify_content_match(self, url: str, expected_content: str) -> Tuple[bool, str]:
        """
        Verify that URL content contains expected text.
        This is expensive (full page fetch) so use sparingly.
        """
        if not expected_content or len(expected_content) < 20:
            return True, "Content too short to verify"

        try:
            response = self.session.get(url, timeout=self.timeout)
            time.sleep(self.rate_limit)

            if response.status_code != 200:
                return False, f"HTTP {response.status_code}"

            page_text = response.text
            # Check for a distinctive substring (first 50 chars of content)
            check_text = expected_content[:50].strip()

            if check_text in page_text:
                return True, "Content verified"
            else:
                return False, "Content mismatch - expected text not found on page"

        except Exception as e:
            return False, str(e)

    def validate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single record comprehensively."""
        url = record.get('url', '')
        platform = record.get('platform', 'unknown')
        content = record.get('content', '')

        validation = {
            'record_id': record.get('record_id', 'unknown'),
            'url': url,
            'platform': platform,
            'url_valid': False,
            'url_status': 0,
            'url_error': '',
            'content_verified': False,
            'content_error': '',
            'overall_valid': False,
            'warnings': []
        }

        # Step 1: URL accessibility
        is_accessible, status, error = self._check_url(url)
        validation['url_valid'] = is_accessible
        validation['url_status'] = status
        validation['url_error'] = error

        # Platform-specific checks
        if platform == 'github' and 'discussions' in url:
            valid, msg = self._check_github_discussion_exists(url)
            if not valid:
                validation['url_valid'] = False
                validation['url_error'] = msg

        elif platform == 'reddit':
            valid, msg = self._check_reddit_post_exists(url)
            if not valid:
                validation['url_valid'] = False
                validation['url_error'] = msg

        elif platform == 'stackoverflow':
            valid, msg = self._check_stackoverflow_post_exists(url)
            if not valid:
                validation['url_valid'] = False
                validation['url_error'] = msg

        # Step 2: Content verification (only if URL is valid)
        if validation['url_valid'] and content:
            content_ok, content_msg = self._verify_content_match(url, content)
            validation['content_verified'] = content_ok
            validation['content_error'] = content_msg

        # Step 3: Structural URL check for new sources
        new_source_platforms = {'devto', 'hashnode', 'hackernews', 'lobsters', 'gitlab'}
        if platform in new_source_platforms:
            struct_ok, struct_msg = self._check_new_source_url(url, platform)
            if not struct_ok:
                validation['url_valid'] = False
                validation['url_error'] = struct_msg

        # Step 4: Thread-context integrity check
        thread_warnings = self._check_thread_context(record)
        validation['warnings'].extend(thread_warnings)

        # Step 5: General plausibility checks
        if record.get('upvotes', 0) > 10000:
            validation['warnings'].append("Suspiciously high upvote count")

        if record.get('content_length', 0) < 20:
            validation['warnings'].append("Very short content")

        if not record.get('author_handle'):
            validation['warnings'].append("Missing author information")

        if record.get('analogy_confidence', 0) == 0.0 and record.get('analogy_present'):
            validation['warnings'].append(
                "analogy_present=True but analogy_confidence=0.0 — possible detection issue"
            )

        # Overall validity
        validation['overall_valid'] = (
            validation['url_valid'] and
            (validation['content_verified'] or not content)
        )

        return validation

    def validate_dataset(self, csv_path: str, sample_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Validate entire dataset.

        Args:
            csv_path: Path to collected data CSV
            sample_size: If set, only validate random sample (for large datasets)

        Returns:
            Validation report dictionary
        """
        self.logger.info(f"Validating dataset: {csv_path}")

        df = pd.read_csv(csv_path)

        if sample_size and len(df) > sample_size:
            self.logger.info(f"Sampling {sample_size} records from {len(df)}")
            df = df.sample(n=sample_size, random_state=42)

        validations = []

        for _, row in tqdm(df.iterrows(), total=len(df), desc="Validating"):
            record = row.to_dict()
            validation = self.validate_record(record)
            validations.append(validation)

        validation_df = pd.DataFrame(validations)

        # Statistics
        total = len(validation_df)
        valid_urls = validation_df['url_valid'].sum()
        verified_content = validation_df['content_verified'].sum()
        overall_valid = validation_df['overall_valid'].sum()

        # Error breakdown
        url_errors = validation_df[~validation_df['url_valid']]['url_error'].value_counts().to_dict()
        content_errors = validation_df[
            (validation_df['url_valid']) & (~validation_df['content_verified'])
        ]['content_error'].value_counts().to_dict()

        # Platform breakdown with source-type sub-counts
        platform_stats = {}
        for platform in validation_df['platform'].unique():
            platform_df = validation_df[validation_df['platform'] == platform]
            stat: Dict[str, Any] = {
                'total': len(platform_df),
                'valid_urls': int(platform_df['url_valid'].sum()),
                'valid_content': int(platform_df['content_verified'].sum()),
                'overall_valid': int(platform_df['overall_valid'].sum()),
            }
            # Source-type sub-breakdown from the original df (before validation)
            if 'source_type' in df.columns:
                src_counts = df[df['platform'] == platform]['source_type'].value_counts().to_dict()
                stat['source_type_counts'] = src_counts
            platform_stats[platform] = stat

        # Count thread-integrity warnings
        thread_warn_count = sum(
            1 for v in validation_df['warnings']
            if any('thread context' in w.lower() for w in (v if isinstance(v, list) else []))
        )

        report = {
            'total_records': total,
            'valid_urls': int(valid_urls),
            'valid_url_rate': valid_urls / total if total > 0 else 0,
            'verified_content': int(verified_content),
            'content_verification_rate': verified_content / total if total > 0 else 0,
            'overall_valid': int(overall_valid),
            'overall_valid_rate': overall_valid / total if total > 0 else 0,
            'url_errors': url_errors,
            'content_errors': content_errors,
            'platform_stats': platform_stats,
            'thread_warnings_count': thread_warn_count,
            'validation_details': validation_df
        }

        self.logger.info(f"Validation complete: {overall_valid}/{total} records valid ({report['overall_valid_rate']:.1%})")

        return report

    def generate_validation_report(self, report: Dict[str, Any], output_path: str = "validation_report.txt"):
        """Generate human-readable validation report."""
        lines = []
        lines.append("=" * 70)
        lines.append("DATA VALIDATION REPORT")
        lines.append("=" * 70)
        lines.append(f"Total Records Checked: {report['total_records']}")
        lines.append("")
        lines.append("URL VALIDITY")
        lines.append("-" * 40)
        lines.append(f"Valid URLs: {report['valid_urls']} / {report['total_records']} ({report['valid_url_rate']:.1%})")
        lines.append("")
        lines.append("CONTENT VERIFICATION")
        lines.append("-" * 40)
        lines.append(f"Verified Content: {report['verified_content']} / {report['total_records']} ({report['content_verification_rate']:.1%})")
        lines.append("")
        lines.append("OVERALL VALIDITY")
        lines.append("-" * 40)
        lines.append(f"Valid Records: {report['overall_valid']} / {report['total_records']} ({report['overall_valid_rate']:.1%})")
        lines.append("")

        if report['url_errors']:
            lines.append("URL ERROR BREAKDOWN")
            lines.append("-" * 40)
            for error, count in report['url_errors'].items():
                lines.append(f"  {error}: {count}")
            lines.append("")

        if report['content_errors']:
            lines.append("CONTENT ERROR BREAKDOWN")
            lines.append("-" * 40)
            for error, count in report['content_errors'].items():
                lines.append(f"  {error}: {count}")
            lines.append("")

        lines.append("PLATFORM BREAKDOWN")
        lines.append("-" * 40)
        for platform, stats in report['platform_stats'].items():
            total_p = stats['total']
            valid_p = stats['overall_valid']
            rate_p = valid_p / total_p if total_p else 0.0
            lines.append(
                f"  {platform:20s}: {valid_p:4d}/{total_p:4d} valid ({rate_p:.0%})"
                f"  |  URL ok: {stats['valid_urls']:4d}"
            )
            # Per source-type sub-breakdown if available
            if 'source_type_counts' in stats:
                for stype, scnt in stats['source_type_counts'].items():
                    lines.append(f"    {'- ' + stype:22s}: {scnt:4d}")
        lines.append("")

        # Thread-integrity warnings summary
        if report.get('thread_warnings_count', 0):
            lines.append("THREAD INTEGRITY WARNINGS")
            lines.append("-" * 40)
            lines.append(
                f"  {report['thread_warnings_count']} comment/note records have "
                "missing or malformed thread context. Review before publication."
            )
            lines.append("")

        # Critical warnings
        if report['overall_valid_rate'] < 0.9:
            lines.append("WARNING: Less than 90% of records are valid!")
            lines.append("    Review invalid records before publication.")

        if report['valid_url_rate'] < 0.95:
            lines.append("WARNING: Significant number of broken URLs detected!")
            lines.append("    These may be fabricated or deleted posts.")

        lines.append("=" * 70)

        report_text = "\n".join(lines)

        with open(output_path, 'w') as f:
            f.write(report_text)

        print(report_text)
        return report_text


if __name__ == "__main__":
    # Example usage
    validator = DataValidator()

    # Validate a single record
    test_record = {
        'record_id': 'GH-001',
        'url': 'https://github.com/orgs/community/discussions/163630',
        'platform': 'github',
        'content': "It's like babysitting a junior dev with amnesia"
    }

    result = validator.validate_record(test_record)
    print(f"Validation result: {result}")