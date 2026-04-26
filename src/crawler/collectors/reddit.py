"""
Reddit Collector
Uses PRAW (Python Reddit API Wrapper) - Official, TOS-compliant.
REQUIRES Reddit API credentials (client_id, client_secret).
Register at: https://www.reddit.com/prefs/apps
"""

import os
import time
from typing import Dict, List, Any, Optional
import praw
from praw.models import Submission, Comment
from collectors.base import BaseCollector


class RedditCollector(BaseCollector):
    """Collector for Reddit posts and comments using PRAW."""

    def __init__(self, config_path: str = "config.yaml"):
        super().__init__(config_path)
        self.client_id = self.platform_config.get('client_id') or os.environ.get('REDDIT_CLIENT_ID')
        self.client_secret = self.platform_config.get('client_secret') or os.environ.get('REDDIT_CLIENT_SECRET')
        self.user_agent = self.platform_config.get('user_agent', 'AnalogicalReasoningResearch/1.0')
        self.subreddits = self.platform_config.get('subreddits', ['programming', 'softwareengineering'])
        self.sort = self.platform_config.get('sort', 'relevance')
        self.time_filter = self.platform_config.get('time_filter', 'year')
        self.limit = self.platform_config.get('limit', 1000)

        if not self.client_id or not self.client_secret:
            raise ValueError("Reddit API credentials required. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.")

        self.reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent
        )
        self.logger.info(f"Authenticated as: {self.reddit.user.me()}")

    def _process_submission(self, submission: Submission) -> Optional[Dict[str, Any]]:
        """Process a Reddit submission (post)."""
        content = f"{submission.title}\n{submission.selftext}"

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        return self.create_record(
            record_id=f"RD-{submission.id}",
            source_type='submission',
            url=f"https://www.reddit.com{submission.permalink}",
            archive_url=f"https://webcache.googleusercontent.com/search?q=cache:https://www.reddit.com{submission.permalink}",
            title=submission.title,
            author_handle=str(submission.author) if submission.author else '[deleted]',
            post_date=datetime.fromtimestamp(submission.created_utc).isoformat(),
            content=submission.selftext,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self._extract_target_domain(content),
            source_domain=self._extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=submission.score,
            upvotes=submission.score,
            replies=submission.num_comments,
            views=0,  # Reddit does not expose view counts via API
            verified_by='api'
        )

    def _process_comment(self, comment: Comment, submission_title: str = '') -> Optional[Dict[str, Any]]:
        """Process a Reddit comment."""
        content = comment.body

        if self.should_exclude(content):
            return None

        has_analogy, confidence = self.contains_analogy(content)
        if not has_analogy:
            return None

        analogy_types = self.classify_analogy_type(content)
        analogy_quote = self.extract_analogy_quote(content)
        sdlc_phase = self.determine_sdlc_phase(content)

        return self.create_record(
            record_id=f"RD-CMT-{comment.id}",
            source_type='comment',
            url=f"https://www.reddit.com{comment.permalink}",
            archive_url='',
            title=f"Comment on: {submission_title}",
            author_handle=str(comment.author) if comment.author else '[deleted]',
            post_date=datetime.fromtimestamp(comment.created_utc).isoformat(),
            content=content,
            analogy_present=True,
            analogy_types=analogy_types,
            analogy_quote=analogy_quote or '',
            analogy_confidence=confidence,
            target_domain=self._extract_target_domain(content),
            source_domain=self._extract_source_domain(analogy_quote) if analogy_quote else '',
            sldc_phase=sdlc_phase,
            engagement_score=comment.score,
            upvotes=comment.score,
            replies=0,
            views=0,
            verified_by='api'
        )

    def _extract_target_domain(self, text: str) -> str:
        return self.extract_target_system(text)

    def _extract_source_domain(self, quote: str) -> str:
        return self.extract_source_domain(quote)

    def collect(self) -> List[Dict[str, Any]]:
        """Collect submissions and comments from configured subreddits."""
        self.logger.info("Starting Reddit collection...")
        records = []

        # Subreddits already provide the SE context; keep Reddit search compact
        # because very long boolean queries are brittle in Reddit search.
        indicator_terms = self.config['keywords']['analogy_indicators']
        query = ' OR '.join([f'"{term}"' for term in indicator_terms[:20]])

        for subreddit_name in self.subreddits:
            self.logger.info(f"Searching r/{subreddit_name}...")
            subreddit = self.reddit.subreddit(subreddit_name)

            try:
                # Search submissions
                submissions = subreddit.search(
                    query=query,
                    sort=self.sort,
                    time_filter=self.time_filter,
                    limit=self.limit
                )

                for submission in submissions:
                    record = self._process_submission(submission)
                    if record:
                        records.append(record)

                    # Optionally collect top-level comments
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments[:10]:  # Limit to top 10 comments
                        comment_record = self._process_comment(comment, submission.title)
                        if comment_record:
                            records.append(comment_record)

                    time.sleep(0.5)  # Rate limiting

            except Exception as e:
                self.logger.error(f"Error collecting from r/{subreddit_name}: {e}")
                continue

        self.logger.info(f"Reddit collection complete. {len(records)} analogy records found.")
        self.save_records(records, "reddit_analogies.csv")
        return records


if __name__ == "__main__":
    collector = RedditCollector()
    collector.collect()