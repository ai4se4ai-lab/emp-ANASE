"""
Cross-Platform Deduplication Module
Uses TF-IDF + cosine similarity to detect near-duplicate content across platforms.
"""

import hashlib
import logging
from typing import Dict, List, Any, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class Deduplicator:
    """Deduplicate records across platforms using content similarity."""

    def __init__(self, similarity_threshold: float = 0.85, min_content_length: int = 50):
        self.similarity_threshold = similarity_threshold
        self.min_content_length = min_content_length
        self.logger = logging.getLogger('deduplicator')
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1
        )

    def _preprocess_text(self, text: str) -> str:
        """Normalize text for comparison."""
        import re
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _exact_hash_dedup(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """Remove exact duplicates by content hash."""
        seen_hashes = set()
        unique_records = []
        removed = 0

        for record in records:
            content = record.get('content', '')
            if len(content) < self.min_content_length:
                continue

            content_hash = hashlib.md5(content.encode()).hexdigest()

            if content_hash in seen_hashes:
                removed += 1
                continue

            seen_hashes.add(content_hash)
            unique_records.append(record)

        self.logger.info(f"Exact deduplication: removed {removed} duplicates")
        return unique_records, removed

    def _similarity_dedup(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """Remove near-duplicates using TF-IDF cosine similarity."""
        if len(records) < 2:
            return records, 0

        texts = [self._preprocess_text(r.get('content', '')) for r in records]

        try:
            tfidf_matrix = self.vectorizer.fit_transform(texts)
            similarity_matrix = cosine_similarity(tfidf_matrix)
        except ValueError:
            self.logger.warning("TF-IDF vectorization failed, skipping similarity dedup")
            return records, 0

        # Find pairs above threshold (excluding diagonal)
        to_remove = set()
        for i in range(len(records)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(records)):
                if j in to_remove:
                    continue
                if similarity_matrix[i, j] >= self.similarity_threshold:
                    # Keep the record with higher engagement
                    if records[i].get('engagement_score', 0) >= records[j].get('engagement_score', 0):
                        to_remove.add(j)
                    else:
                        to_remove.add(i)
                        break

        filtered_records = [r for i, r in enumerate(records) if i not in to_remove]
        removed = len(records) - len(filtered_records)

        self.logger.info(f"Similarity deduplication: removed {removed} near-duplicates")
        return filtered_records, removed

    def deduplicate(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Full deduplication pipeline.

        Returns:
            dict with 'records', 'exact_removed', 'similar_removed', 'total_original'
        """
        self.logger.info(f"Starting deduplication of {len(records)} records...")

        total_original = len(records)

        # Step 1: Exact deduplication
        step1_records, exact_removed = self._exact_hash_dedup(records)

        # Step 2: Similarity-based deduplication
        step2_records, similar_removed = self._similarity_dedup(step1_records)

        self.logger.info(f"Deduplication complete: {len(step2_records)} unique records retained")

        return {
            'records': step2_records,
            'total_original': total_original,
            'exact_removed': exact_removed,
            'similar_removed': similar_removed,
            'total_removed': exact_removed + similar_removed,
            'retention_rate': len(step2_records) / total_original if total_original > 0 else 0
        }

    def cross_platform_stats(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate statistics about unique developers per platform."""
        platform_stats = {}

        for record in records:
            platform = record.get('platform', 'unknown')
            author_hash = record.get('author_id_hash', '')

            if platform not in platform_stats:
                platform_stats[platform] = {'count': 0, 'unique_authors': set()}

            platform_stats[platform]['count'] += 1
            if author_hash:
                platform_stats[platform]['unique_authors'].add(author_hash)

        # Convert sets to counts
        for platform in platform_stats:
            platform_stats[platform]['unique_authors'] = len(platform_stats[platform]['unique_authors'])

        # Note: Cross-platform deduplication of authors is IMPOSSIBLE because
        # different platforms use different identifier namespaces.
        # The "753 unique developers" claim in the original paper is methodologically
        # unsound unless authors can demonstrate a verified identity linking mechanism.

        total_unique = sum(p['unique_authors'] for p in platform_stats.values())

        return {
            'by_platform': platform_stats,
            'total_unique_authors_uncorrected': total_unique,
            'note': 'Cross-platform author deduplication is not possible without verified identity linking.'
        }


if __name__ == "__main__":
    # Example usage
    dedup = Deduplicator()
    # Load records from CSV and deduplicate
    import pandas as pd
    # df = pd.read_csv('output/combined.csv')
    # result = dedup.deduplicate(df.to_dict('records'))
    pass