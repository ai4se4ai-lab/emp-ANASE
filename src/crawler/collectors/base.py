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
from typing import Dict, List, Optional, Any, Union, Tuple
import yaml


# ------------------------------------------------------------------ #
# Compile-once patterns for the heuristic sense-disambiguation filter #
# ------------------------------------------------------------------ #

# Exemplification heads that precede "like": "things like X" means "such as X",
# not an analogy. Ordered longest-first so multi-word heads match before shorter ones.
_EXEMPLIFICATION_HEADS = [
    'anything like', 'nothing like', 'something like',
    'frameworks like', 'languages like', 'options like',
    'examples like', 'features like', 'topics like',
    'items like', 'cases like', 'tools like', 'stuff like',
    'things like', 'such as', 'e.g.', 'etc.',
]
_EXEMPLIFICATION_PATTERN = re.compile(
    '|'.join(re.escape(h) for h in _EXEMPLIFICATION_HEADS),
    re.IGNORECASE,
)

# Preference / desire / hedging constructions — "I'd like", "would like", etc.
_PREFERENCE_PATTERN = re.compile(
    r"\b(would\s+like|i'?d\s+like|we'?d\s+like|i\s+would\s+like|we\s+would\s+like"
    r"|i\s+like|you\s+like|we\s+like|they\s+like)\b",
    re.IGNORECASE,
)

# Backtick or code-fence spans — indicators inside code are not analogies.
_CODE_SPAN_PATTERN = re.compile(r'`[^`]*`|```[\s\S]*?```')

# Copula / stance verbs that legitimise a comparison: "X IS like a Y", "treat it LIKE"
_COPULA_VERBS = re.compile(
    r'\b(is|are|was|were|be|been|feels?|looks?|seems?|appears?|becomes?|'
    r'treats?|views?|think\s+of|imagine|picture|consider)\b',
    re.IGNORECASE,
)

# Strong indicators that almost certainly signal a true analogy phrase.
# "think of X as" is matched broadly (any noun between "think of" and "as").
_STRONG_ANALOGY_PHRASES = re.compile(
    r'\b(analogy|metaphor|analogous\s+to|just\s+like|much\s+like|works\s+like|'
    r'behaves\s+like|acts\s+like|functions\s+like|resembles|serves\s+as|'
    r'think\s+of\s+(?:\w+\s+)+as|imagine\s+(?:\w+\s+)+as|'
    r'similar\s+to|compared\s+to)\b',
    re.IGNORECASE,
)


class BaseCollector(abc.ABC):
    """Abstract base class for all platform data collectors."""

    def __init__(self, config_path: Union[str, Dict[str, Any]] = "config.yaml"):
        if isinstance(config_path, dict):
            self.config = config_path
        else:
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
        # Broad SE context terms define relevance for software-engineering analogies.
        self.se_context_terms = self.config['keywords'].get('se_context_terms', [])
        self.exclusion_terms = self.config['keywords']['exclusion_terms']
        self.analogy_patterns = self.config['analogy_patterns']

        # Load analogy filter settings from config (with safe defaults when key absent).
        _af = self.config.get('analogy_filters', {})
        self._reject_exemplification: bool = _af.get('reject_exemplification', True)
        self._reject_preference: bool = _af.get('reject_preference', True)
        self._copula_window: int = int(_af.get('require_copula_within_tokens', 6))
        # SE terms that ARE metaphorical targets even though they look domain-internal.
        self._cross_domain_keep: List[str] = [
            t.lower() for t in _af.get('cross_domain_keep', [
                'pipeline', 'factory', 'assembly line', 'warehouse',
                'garden', 'traffic', 'recipe', 'map',
            ])
        ]

        # spaCy NLP object — loaded lazily to avoid startup cost when cross-domain
        # head-noun checking is not needed.
        self._nlp = None

        # LLM second-pass verifier — loaded lazily (import lives in core/).
        self._verifier = None
        self._llm_rejections: int = 0  # counter exposed for reporting

    # ------------------------------------------------------------------ #
    # Lazy loaders                                                        #
    # ------------------------------------------------------------------ #

    def _get_verifier(self):
        """Lazily instantiate the LLMVerifier the first time it is needed."""
        if self._verifier is None:
            from core.llm_verifier import LLMVerifier
            self._verifier = LLMVerifier(self.config)
        return self._verifier

    def _get_nlp(self):
        """Load the spaCy small English model on first use."""
        if self._nlp is None:
            try:
                import spacy
                try:
                    self._nlp = spacy.load('en_core_web_sm', disable=['ner', 'lemmatizer'])
                except OSError:
                    self.logger.warning(
                        "spaCy model 'en_core_web_sm' not found. "
                        "Run: python -m spacy download en_core_web_sm"
                    )
                    self._nlp = False  # sentinel — skip spaCy checks for this run
            except ImportError:
                self._nlp = False
        return self._nlp if self._nlp is not False else None

    # ------------------------------------------------------------------ #
    # Sentence-level sense disambiguation                                 #
    # ------------------------------------------------------------------ #

    def _is_likely_analogy_sentence(self, sentence: str) -> bool:
        """
        Return True when *sentence* looks like a genuine cross-domain analogy.

        Checks (in order, short-circuiting early):
        1. Strip inline code spans so indicators inside backticks are invisible.
        2. Reject exemplification heads ("things like", "such as", …).
        3. Reject preference/desire constructions ("I'd like", "would like", …).
        4. If a strong analogy phrase is present (metaphor, works like, …), accept.
        5. Require a copula verb within `_copula_window` words before the indicator.
        6. Cross-domain head-noun check via spaCy (if available).
        """
        # 1. Strip code spans to avoid matching indicators inside backticks.
        cleaned = _CODE_SPAN_PATTERN.sub('', sentence)
        cl = cleaned.lower()

        # 2. Exemplification rejection.
        if self._reject_exemplification and _EXEMPLIFICATION_PATTERN.search(cl):
            return False

        # 3. Preference/desire rejection.
        if self._reject_preference and _PREFERENCE_PATTERN.search(cl):
            return False

        # 4. Strong phrases are accepted without further checks.
        if _STRONG_ANALOGY_PHRASES.search(cl):
            return self._cross_domain_head_is_ok(cleaned)

        # 5. Weak indicators ("like a", "like an") require a copula verb nearby.
        tokens = cl.split()
        for i, token in enumerate(tokens):
            # Find "like" in token stream and check for copula within window before it.
            if token in ('like',):
                window_start = max(0, i - self._copula_window)
                window = ' '.join(tokens[window_start:i])
                if _COPULA_VERBS.search(window):
                    return self._cross_domain_head_is_ok(cleaned)
        return False

    def _cross_domain_head_is_ok(self, sentence: str) -> bool:
        """
        Return True when the comparison in *sentence* crosses into a different domain.

        Strategy:
        1. Try "like a/an <noun>" (articles present).
        2. Fall back to "like <CapitalisedWord>" (proper/technical noun, no article).
        3. If spaCy is available, use it for the article-free case.
        Falls back to True when the noun cannot be determined.
        """
        sent_lower = sentence.lower()

        # --- Case 1: "like a/an <noun>" ---
        m = re.search(r'\blike\s+an?\s+(\w+)', sentence, re.IGNORECASE)
        if m:
            candidate = m.group(1).lower()
            if any(candidate == keep or candidate in keep for keep in self._cross_domain_keep):
                return True
            if any(candidate == term.lower() or candidate in term.lower()
                   for term in self.se_context_terms):
                return False
            return True

        # --- Case 2: "like <word>" without article — check if it's an SE term. ---
        m2 = re.search(r'\blike\s+([A-Z]\w*)', sentence)  # proper / technical noun
        if m2:
            candidate = m2.group(1).lower()
            if any(candidate == keep or candidate in keep for keep in self._cross_domain_keep):
                return True
            if any(candidate == term.lower() for term in self.se_context_terms):
                return False

        # Cannot determine → degrade gracefully (keep record, let LLM decide).
        return True

    # ------------------------------------------------------------------ #
    # Core detection                                                      #
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        """Main collection method. Must be implemented by subclasses."""
        pass

    def should_exclude(self, text: str) -> bool:
        """Check if content should be excluded based on exclusion terms."""
        text_lower = text.lower()
        return any(term.lower() in text_lower for term in self.exclusion_terms)

    def contains_analogy(self, text: str) -> Tuple[bool, float]:
        """
        Heuristic detection of analogical language.

        Two-stage gate:
        1. Document must contain both an analogy indicator and an SE context term.
        2. At least one sentence containing an indicator must pass the sense
           disambiguation filter (_is_likely_analogy_sentence).

        Returns (contains_analogy, confidence_score).
        """
        text_lower = text.lower()

        # Stage 1: quick document-level check (cheap).
        indicator_hits = sum(1 for ind in self.analogy_indicators if ind.lower() in text_lower)
        context_hits = sum(1 for term in self.se_context_terms if term.lower() in text_lower)

        if indicator_hits == 0 or context_hits == 0:
            return False, 0.0

        # Stage 2: sentence-level disambiguation.
        sentences = re.split(r'(?<=[.!?])\s+', text)
        qualifying_sentences = [
            s for s in sentences
            if any(ind.lower() in s.lower() for ind in self.analogy_indicators)
            and self._is_likely_analogy_sentence(s)
        ]

        if not qualifying_sentences:
            return False, 0.0

        # Confidence: based on qualifying sentences and SE context.
        confidence = min(0.7, (len(qualifying_sentences) * 0.3) + (context_hits * 0.1))

        # Boost for strong analogy language (only when structure check already passed).
        if _STRONG_ANALOGY_PHRASES.search(text_lower):
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
        """Extract the best sentence containing a genuine analogy."""
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Primary: sentence with indicator + SE context + passes disambiguation.
        for sentence in sentences:
            if (any(ind.lower() in sentence.lower() for ind in self.analogy_indicators)
                    and any(t.lower() in sentence.lower() for t in self.se_context_terms)
                    and self._is_likely_analogy_sentence(sentence)):
                quote = sentence.strip()
                return quote[:max_length] + ('...' if len(quote) > max_length else '')

        # Secondary: analogy sentence that passes disambiguation (anaphoric references).
        for sentence in sentences:
            if (any(ind.lower() in sentence.lower() for ind in self.analogy_indicators)
                    and self._is_likely_analogy_sentence(sentence)):
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

    _TARGET_SYSTEM_MAP: Dict[str, str] = {
        'architecture': 'Architecture',
        'design pattern': 'Design Pattern',
        'api': 'API',
        'endpoint': 'API Endpoint',
        'database': 'Database',
        'schema': 'Database Schema',
        'cache': 'Cache',
        'queue': 'Queue',
        'thread': 'Concurrency',
        'process': 'Process',
        'dependency': 'Dependency',
        'bug': 'Bug',
        'error': 'Error',
        'exception': 'Exception',
        'crash': 'Crash',
        'debug': 'Debugging',
        'fix': 'Fix/Solution',
        'solution': 'Solution',
        'test': 'Testing',
        'deploy': 'Deployment',
        'build': 'Build System',
        'ci': 'CI/CD',
        'pipeline': 'Pipeline',
        'refactor': 'Refactoring',
        'performance': 'Performance',
        'latency': 'Performance',
        'memory': 'Memory',
        'algorithm': 'Algorithm',
        'function': 'Function',
        'class': 'Class/Object',
        'method': 'Method',
        'compiler': 'Compiler',
        'runtime': 'Runtime',
        'docker': 'Containerization',
        'kubernetes': 'Orchestration',
        'git': 'Version Control',
        'branch': 'Version Control',
        'merge': 'Version Control',
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

    def extract_target_system(self, text: str) -> str:
        """Identify the software concept/tool being explained in *text*."""
        text_lower = text.lower()
        for key, value in self._TARGET_SYSTEM_MAP.items():
            if key in text_lower:
                return value
        return 'Unspecified Software Concept'

    def extract_target_domain(self, text: str) -> str:
        """Backward-compatible alias for the CSV field `target_domain`."""
        return self.extract_target_system(text)

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
            'collector_version': self.config['project']['version'],
            # LLM second-pass fields (empty when LLM is disabled).
            'llm_verified': kwargs.get('llm_verified', False),
            'llm_confidence': kwargs.get('llm_confidence', 0.0),
            'llm_source_domain': kwargs.get('llm_source_domain', ''),
            'llm_target_domain': kwargs.get('llm_target_domain', ''),
            'llm_mapping_summary': kwargs.get('llm_mapping_summary', ''),
            'llm_provider_model': kwargs.get('llm_provider_model', ''),
        }
        return record

    def verify_record_with_llm(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run the LLM second-pass verifier on *record*.

        Returns None when the LLM judges the record to be a false positive,
        otherwise returns the record enriched with llm_* fields.
        The verifier is skipped (record returned as-is) when LLM is disabled.
        """
        verifier = self._get_verifier()
        if not verifier.is_active:
            return record

        quote = record.get('analogy_quote', '') or record.get('content', '')[:300]
        context = record.get('content', '')

        result = verifier.verify(quote, context)

        if not result.get('is_analogy', True):
            self._llm_rejections += 1
            self.logger.debug(
                "LLM rejected record %s: %s",
                record.get('record_id', '?'),
                result.get('reason', '')
            )
            return None

        # Enrich the record with LLM output.
        record['llm_verified'] = True
        record['llm_confidence'] = result.get('confidence', 0.0)
        # LLM-provided domains override regex-based ones when non-empty.
        if result.get('source_domain'):
            record['llm_source_domain'] = result['source_domain']
            record['source_domain'] = result['source_domain']
        if result.get('target_domain'):
            record['llm_target_domain'] = result['target_domain']
            record['target_domain'] = result['target_domain']
        record['llm_mapping_summary'] = result.get('mapping_summary', '')
        record['llm_provider_model'] = result.get('llm_provider_model', '')
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