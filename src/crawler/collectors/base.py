"""
Base Collector Class for Analogical Reasoning Data Collection
Provides abstract interface and shared utilities for all platform collectors.
"""

import abc
import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
import yaml


class BaseCollector(abc.ABC):
    """Abstract base class for all platform data collectors."""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.platform_name = self.__class__.__name__.replace('Collector', '').lower()
        self.platform_config = self.config['platforms'].get(self.platform_name, {})
        self.output_dir = self.config['project']['output_dir']
        os.makedirs(self.output_dir, exist_ok=True)

        # Setup logging
        log_dir = self.config['project'].get('log_dir', './logs')
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f"{log_dir}/{self.platform_name}.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(self.platform_name)

        # Load keywords
        self.analogy_indicators = self.config['keywords']['analogy_indicators']
        self.agent_terms = self.config['keywords']['agent_terms']
        self.exclusion_terms = self.config['keywords']['exclusion_terms']
        self.analogy_patterns = self.config['analogy_patterns']

    @abc.abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        """Main collection method. Must be implemented by subclasses."""
        pass

    def should_exclude(self, text: str) -> bool:
        """Check if content should be excluded based on exclusion terms."""
        text_lower = text.lower()
        return any(term.lower() in text_lower for term in self.exclusion_terms)

    def contains_analogy(self, text: str) -> tuple[bool, float]:
        """
        Heuristic detection of analogical language.
        Returns: (contains_analogy, confidence_score)
        """
        text_lower = text.lower()

        # Check for analogy indicators
        indicator_hits = sum(1 for ind in self.analogy_indicators if ind.lower() in text_lower)
        agent_term_hits = sum(1 for term in self.agent_terms if term.lower() in text_lower)

        # Must contain both analogy language AND agent reference
        if indicator_hits == 0 or agent_term_hits == 0:
            return False, 0.0

        # Confidence based on indicator density and proximity
        confidence = min(1.0, (indicator_hits * 0.3) + (agent_term_hits * 0.2))

        # Boost confidence for explicit analogy words
        if any(word in text_lower for word in ['analogy', 'metaphor', 'like a', 'similar to']):
            confidence = min(1.0, confidence + 0.3)

        return confidence >= 0.3, confidence

    def classify_analogy_type(self, text: str) -> List[str]:
        """Classify analogy into structural, functional, process, or cross-domain."""
        text_lower = text.lower()
        types = []

        for category, patterns in self.analogy_patterns.items():
            if any(pattern.lower() in text_lower for pattern in patterns):
                types.append(category)

        return types if types else ['uncategorized']

    def extract_analogy_quote(self, text: str, max_length: int = 500) -> Optional[str]:
        """Extract the sentence or phrase containing the analogy."""
        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            if any(ind.lower() in sentence.lower() for ind in self.analogy_indicators):
                if any(term.lower() in sentence.lower() for term in self.agent_terms):
                    quote = sentence.strip()
                    return quote[:max_length] + ('...' if len(quote) > max_length else '')

        return None

    def determine_sdlc_phase(self, text: str) -> str:
        """Heuristic determination of SDLC phase from content."""
        text_lower = text.lower()

        phase_keywords = {
            'requirements': ['requirement', 'spec', 'user story', 'feature request', 'planning'],
            'design': ['architecture', 'design pattern', 'blueprint', 'structure', 'model'],
            'development': ['implement', 'code', 'programming', 'function', 'class', 'method'],
            'code_review': ['review', 'pr ', 'pull request', 'approve', 'reject'],
            'debugging': ['bug', 'debug', 'fix', 'error', 'exception', 'crash', 'issue'],
            'testing': ['test', 'unit test', 'integration', 'qa', 'validation']
        }

        scores = {phase: sum(1 for kw in keywords if kw in text_lower) 
                  for phase, keywords in phase_keywords.items()}

        if max(scores.values()) == 0:
            return 'general'

        return max(scores, key=scores.get)

    # ------------------------------------------------------------------ #
    # Shared domain-extraction helpers (used by all collectors)           #
    # ------------------------------------------------------------------ #

    _AGENT_MAP: Dict[str, str] = {
        'github copilot': 'GitHub Copilot',
        'copilot': 'GitHub Copilot',
        'cursor': 'Cursor',
        'claude code': 'Claude Code',
        'claude': 'Claude',
        'chatgpt': 'ChatGPT',
        'gpt-4': 'GPT-4',
        'gpt-5': 'GPT-5',
        'gemini': 'Gemini',
        'ai agent': 'Generic AI Agent',
        'coding agent': 'Generic AI Agent',
        'swe agent': 'SWE-agent',
    }

    def extract_target_domain(self, text: str) -> str:
        """Identify which AI agent/tool is being discussed in *text*."""
        text_lower = text.lower()
        for key, value in self._AGENT_MAP.items():
            if key in text_lower:
                return value
        return 'Unspecified AI Tool'

    def extract_source_domain(self, quote: str) -> str:
        """Extract the source-side comparison noun from an analogy quote."""
        if not quote:
            return ''
        match = re.search(r'like a[n]?\s+([^,.;]+)', quote.lower())
        if match:
            return match.group(1).strip()
        return ''

    def anonymize_author(self, handle: str) -> str:
        """Create consistent anonymized hash of author identifier."""
        return hashlib.sha256(handle.encode()).hexdigest()[:16]

    def create_record(self, **kwargs) -> Dict[str, Any]:
        """Create a standardized record dictionary."""
        record = {
            'record_id': kwargs.get('record_id'),
            'platform': self.platform_name,
            'source_type': kwargs.get('source_type', 'unknown'),
            'url': kwargs.get('url'),
            'archive_url': kwargs.get('archive_url'),
            'title': kwargs.get('title', ''),
            'author_handle': kwargs.get('author_handle', ''),
            'author_id_hash': self.anonymize_author(kwargs.get('author_handle', '')) if kwargs.get('author_handle') else '',
            'post_date': kwargs.get('post_date'),
            'collection_date': datetime.now().isoformat(),
            'content': kwargs.get('content', ''),
            'content_length': len(kwargs.get('content', '')),
            'analogy_present': kwargs.get('analogy_present', False),
            'analogy_types': ','.join(kwargs.get('analogy_types', [])),
            'analogy_quote': kwargs.get('analogy_quote', ''),
            'analogy_confidence': kwargs.get('analogy_confidence', 0.0),
            'target_domain': kwargs.get('target_domain', ''),
            'source_domain': kwargs.get('source_domain', ''),
            'sldc_phase': kwargs.get('sldc_phase', 'general'),
            'engagement_score': kwargs.get('engagement_score', 0),
            'upvotes': kwargs.get('upvotes', 0),
            'replies': kwargs.get('replies', 0),
            'views': kwargs.get('views', 0),
            'verified_by': kwargs.get('verified_by', ''),
            'collector_version': self.config['project']['version']
        }
        return record

    def save_records(self, records: List[Dict[str, Any]], filename: Optional[str] = None):
        """Save collected records to CSV."""
        import pandas as pd

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.platform_name}_{timestamp}.csv"

        filepath = os.path.join(self.output_dir, filename)
        df = pd.DataFrame(records)
        df.to_csv(filepath, index=False, quoting=1)
        self.logger.info(f"Saved {len(records)} records to {filepath}")
        return filepath