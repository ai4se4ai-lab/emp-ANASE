"""
err_scorer.py
=============
Implements the ERR (Extensible-Relation Representation) analogy scoring
described in Section II-B of the paper.

ERR decomposes text into:
  - Objects  (nouns)
  - Relations (verbs connecting objects)

The key metric is **Relational Density** = |relations| / |objects|
This is used as the proxy for "analogy systematicity" in Figure 4.

Four evaluation dimensions (Gentner's structure-mapping criteria):
  1. factual_correctness  — does the analogy map real properties?
  2. adaptability         — can source facts transfer to target?
  3. goal_relevance       — does the analogy serve its purpose?
  4. knowledge_intensity  — depth of insight gained

Usage:
    from err_scorer import ERRScorer
    scorer = ERRScorer()
    result = scorer.score("The agent is like a junior developer who writes tests")
    print(result.relational_density)   # float
    print(result.analogy_category)     # "process"
"""

import re
import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Minimal POS tagging without external models (rule-based, sufficient for
# the noun/verb extraction the paper needs).
# Falls back to nltk if available for better accuracy.
# ---------------------------------------------------------------------------
try:
    import nltk
    nltk.download("averaged_perceptron_tagger_eng", quiet=True)
    nltk.download("punkt_tab", quiet=True)
    nltk.download("wordnet", quiet=True)
    from nltk import pos_tag, word_tokenize
    NLTK_AVAILABLE = True
except Exception:
    NLTK_AVAILABLE = False


# Common English stop-words (nouns/verbs that carry no domain meaning)
STOP_NOUNS = {
    "thing", "way", "time", "people", "man", "woman", "day", "year",
    "use", "part", "place", "case", "week", "company", "system", "program",
    "question", "problem", "hand", "work", "lot", "point", "play", "fact",
    "world", "life", "head", "room", "type", "kind", "number", "line",
    "end", "side", "bit", "idea", "body", "information", "back", "area",
    "result", "order", "sense", "term", "level", "example", "reason",
}

STOP_VERBS = {
    "be", "is", "are", "was", "were", "been", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "shall", "can", "need", "dare", "get", "got", "make",
    "made", "go", "went", "come", "came", "say", "said", "seem",
    "look", "feel", "know", "think", "want", "see",
}

# Verb patterns associated with each analogy category
ANALOGY_VERB_SIGNATURES = {
    "structural": [
        "contains", "holds", "stores", "organizes", "builds", "constructs",
        "structures", "layers", "stacks", "composes", "nests", "extends",
        "inherits", "references", "points",
    ],
    "functional": [
        "swaps", "attaches", "extends", "plugs", "connects", "enhances",
        "enables", "activates", "processes", "transforms", "converts",
        "executes", "runs", "performs", "operates",
    ],
    "process": [
        "collaborates", "reviews", "supervises", "delegates", "approves",
        "rejects", "submits", "discusses", "assigns", "mentors", "guides",
        "coordinates", "communicates", "negotiates",
    ],
    "cross_domain": [
        "drives", "flies", "pilots", "renovates", "repairs", "builds",
        "plants", "cooks", "navigates", "balances", "gambles", "rolls",
    ],
}

ANALOGY_NOUN_SIGNATURES = {
    "structural": [
        "stack", "tree", "layer", "architecture", "foundation", "pipeline",
        "hierarchy", "graph", "node", "edge", "interface", "module",
        "component", "dependency", "contract",
    ],
    "functional": [
        "tool", "drill", "bit", "attachment", "instrument", "switch",
        "skill", "plugin", "function", "capability", "feature", "mode",
        "parameter", "setting",
    ],
    "process": [
        "engineer", "developer", "intern", "colleague", "team", "manager",
        "reviewer", "junior", "senior", "mentor", "pair", "partner",
        "collaborator", "supervisor",
    ],
    "cross_domain": [
        "autopilot", "lottery", "temperature", "renovation", "babysitter",
        "amnesia", "cruise", "pilot", "chef", "garden", "gamble",
    ],
}

# SDLC phases keyword mapping
SDLC_PHASES = {
    "requirements": [
        "requirement", "spec", "specification", "user story", "backlog",
        "feature request", "acceptance criteria", "epic", "story",
    ],
    "design": [
        "design", "architect", "architecture", "diagram", "schema",
        "uml", "blueprint", "prototype", "wireframe", "model",
    ],
    "development": [
        "implement", "code", "develop", "write", "feature", "function",
        "method", "class", "module", "script", "build", "program",
    ],
    "code_review": [
        "review", "pr", "pull request", "merge", "diff", "comment",
        "feedback", "approve", "reject", "change request",
    ],
    "debugging": [
        "debug", "bug", "error", "fix", "crash", "trace", "exception",
        "issue", "fault", "problem", "breakpoint", "stack trace",
    ],
    "testing": [
        "test", "unit test", "coverage", "assert", "mock", "stub",
        "integration test", "regression", "qa", "quality",
    ],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ERRDecomposition:
    """Represents the ERR graph for a single text snippet."""
    objects: list[str] = field(default_factory=list)       # nouns
    relations: list[tuple[str, str, str]] = field(default_factory=list)  # (subj, verb, obj)
    raw_verbs: list[str] = field(default_factory=list)


@dataclass
class ERRScore:
    """Full scoring result for one analogy instance."""
    text: str
    objects: list[str]
    relations: list[tuple]
    raw_verbs: list[str]

    # Core ERR metric
    relational_density: float          # |relations| / |objects|  (= systematicity)

    # Gentner's 4 criteria (0–1 each)
    factual_correctness: float
    adaptability: float
    goal_relevance: float
    knowledge_intensity: float
    composite_score: float             # weighted average

    # Classification
    analogy_category: str              # structural|functional|process|cross_domain|unknown
    sdlc_phase: str
    contains_breakdown_risk: bool      # True if in "complacency zone" (density > 0.75)

    # Keyword evidence
    matched_analogy_kw: str
    matched_agent_kw: str


# ---------------------------------------------------------------------------
# ERR Scorer
# ---------------------------------------------------------------------------

class ERRScorer:
    """
    Implements the ERR-based analogy evaluation from Section II-B.

    The scorer:
      1. Extracts objects (nouns) and relations (verb triples) from text
      2. Computes relational density as proxy for analogy systematicity
      3. Scores four Gentner criteria via heuristic keyword matching
      4. Classifies the analogy type and SDLC phase
    """

    ANALOGY_KEYWORDS = [
        "analogy", "metaphor", "like a", "similar to",
        "as if", "resembles", "just like", "think of it as",
    ]
    AGENT_KEYWORDS = [
        "ai agent", "copilot", "cursor", "claude code",
        "github copilot", "agentic", "llm agent", "ai coding",
        "code generation", "autocomplete",
    ]

    # Weights for composite score (sum = 1.0)
    WEIGHTS = {
        "factual_correctness": 0.30,
        "adaptability":        0.25,
        "goal_relevance":      0.25,
        "knowledge_intensity": 0.20,
    }

    def score(self, text: str, context: str = "") -> ERRScore:
        """Score a single text snippet."""
        full = f"{text} {context}".strip()
        decomp = self._decompose(text)

        n_objects   = max(len(decomp.objects), 1)
        n_relations = len(decomp.relations)
        rel_density = round(n_relations / n_objects, 3)

        fc = self._factual_correctness(decomp, full)
        ad = self._adaptability(decomp, full)
        gr = self._goal_relevance(full)
        ki = self._knowledge_intensity(decomp, full)

        composite = round(
            fc * self.WEIGHTS["factual_correctness"] +
            ad * self.WEIGHTS["adaptability"] +
            gr * self.WEIGHTS["goal_relevance"] +
            ki * self.WEIGHTS["knowledge_intensity"],
            3,
        )

        category = self._classify_category(decomp, full)
        phase    = self._classify_phase(full)

        return ERRScore(
            text=text,
            objects=decomp.objects,
            relations=decomp.relations,
            raw_verbs=decomp.raw_verbs,
            relational_density=rel_density,
            factual_correctness=round(fc, 3),
            adaptability=round(ad, 3),
            goal_relevance=round(gr, 3),
            knowledge_intensity=round(ki, 3),
            composite_score=composite,
            analogy_category=category,
            sdlc_phase=phase,
            contains_breakdown_risk=rel_density > 0.75,
            matched_analogy_kw=next(
                (kw for kw in self.ANALOGY_KEYWORDS if kw in full.lower()), ""),
            matched_agent_kw=next(
                (kw.lower() for kw in self.AGENT_KEYWORDS if kw.lower() in full.lower()), ""),
        )

    def score_batch(self, texts: list[str]) -> list[ERRScore]:
        return [self.score(t) for t in texts]

    # ------------------------------------------------------------------
    # ERR Decomposition
    # ------------------------------------------------------------------

    def _decompose(self, text: str) -> ERRDecomposition:
        if NLTK_AVAILABLE:
            return self._decompose_nltk(text)
        return self._decompose_regex(text)

    def _decompose_nltk(self, text: str) -> ERRDecomposition:
        """Use NLTK POS tags for noun/verb extraction."""
        try:
            tokens = word_tokenize(text)
            tagged = pos_tag(tokens)

            nouns = [
                w.lower() for w, t in tagged
                if t.startswith("NN") and len(w) > 2 and w.lower() not in STOP_NOUNS
            ]
            verbs = [
                w.lower() for w, t in tagged
                if t.startswith("VB") and len(w) > 2 and w.lower() not in STOP_VERBS
            ]

            # Build simple subject-verb-object triples using proximity
            relations = self._build_triples(nouns, verbs, text.lower())
            return ERRDecomposition(objects=nouns, relations=relations, raw_verbs=verbs)
        except Exception:
            return self._decompose_regex(text)

    def _decompose_regex(self, text: str) -> ERRDecomposition:
        """Regex fallback: extract nouns (capitalized or domain-specific) and verbs."""
        text_l = text.lower()

        # Collect known domain nouns
        all_domain_nouns = set()
        for nouns in ANALOGY_NOUN_SIGNATURES.values():
            all_domain_nouns.update(nouns)

        nouns = [n for n in all_domain_nouns if n in text_l]

        # Also extract simple noun-like tokens (≥3 chars, no digits)
        candidates = re.findall(r"\b[a-z][a-z]{2,}\b", text_l)
        # Use a crude heuristic: tokens that appear after articles/determiners
        det_pattern = re.compile(r"\b(?:a|an|the|this|that|my|your|our|its)\s+([a-z][a-z]{2,})\b")
        noun_candidates = det_pattern.findall(text_l)
        nouns = list(set(nouns + [n for n in noun_candidates if n not in STOP_NOUNS]))

        # Collect known domain verbs
        all_domain_verbs = set()
        for verbs in ANALOGY_VERB_SIGNATURES.values():
            all_domain_verbs.update(verbs)

        verbs = [v for v in all_domain_verbs if v in text_l]

        # Generic verb-like patterns ending in common suffixes
        verb_pattern = re.compile(
            r"\b([a-z]+(?:ates|izes|ifies|s|es|ed|ing))\b"
        )
        verb_candidates = verb_pattern.findall(text_l)
        verbs = list(set(verbs + [
            v for v in verb_candidates
            if v not in STOP_VERBS and len(v) > 4
        ]))[:20]  # cap to avoid noise

        nouns = nouns[:20] if nouns else ["agent", "developer"]
        relations = self._build_triples(nouns, verbs, text_l)
        return ERRDecomposition(objects=nouns, relations=relations, raw_verbs=verbs)

    def _build_triples(
        self, nouns: list[str], verbs: list[str], text: str
    ) -> list[tuple[str, str, str]]:
        """
        Build (subj, verb, obj) triples by finding verb occurrences
        surrounded by nouns in the text.
        """
        triples = []
        for verb in verbs:
            # Find position of verb in text
            idx = text.find(verb)
            if idx == -1:
                continue
            # Find nearest noun before and after
            before = text[:idx]
            after  = text[idx + len(verb):]

            subj = next((n for n in reversed(nouns) if n in before), None)
            obj  = next((n for n in nouns if n in after), None)

            if subj and obj and subj != obj:
                triples.append((subj, verb, obj))
            elif subj:
                triples.append((subj, verb, "?"))
            elif obj:
                triples.append(("?", verb, obj))

        return triples

    # ------------------------------------------------------------------
    # Gentner's 4 criteria (heuristic scoring 0–1)
    # ------------------------------------------------------------------

    def _factual_correctness(self, decomp: ERRDecomposition, text: str) -> float:
        """
        High score if the analogy maps to real, verifiable properties of AI agents.
        Penalty if it maps known misconceptions (e.g. autonomous = autopilot).
        """
        misconception_kw = [
            "autopilot", "fully autonomous", "self-driving", "never wrong",
            "always correct", "perfect memory", "unlimited context",
        ]
        correct_kw = [
            "context", "token", "probabilistic", "stochastic", "uncertain",
            "verify", "check", "review", "oversight", "supervision",
        ]
        text_l = text.lower()
        penalty = sum(0.15 for kw in misconception_kw if kw in text_l)
        bonus   = sum(0.10 for kw in correct_kw      if kw in text_l)
        base    = 0.5 + min(bonus, 0.4) - min(penalty, 0.4)

        # More domain-relevant objects → higher factual score
        domain_ratio = len(decomp.objects) / max(len(decomp.objects) + 2, 1)
        return max(0.1, min(1.0, base + 0.1 * domain_ratio))

    def _adaptability(self, decomp: ERRDecomposition, text: str) -> float:
        """
        Measures how easily source-domain facts map to AI agent behavior.
        Structural analogies tend to be more adaptable; affective ones less so.
        """
        adapt_kw = [
            "just like", "same way", "similar to", "works like",
            "equivalent", "maps to", "corresponds", "analogous",
        ]
        hard_kw = [
            "completely different", "not really", "doesn't apply",
            "breaks down", "fails when", "wrong analogy",
        ]
        text_l = text.lower()
        score = 0.5
        score += sum(0.08 for kw in adapt_kw if kw in text_l)
        score -= sum(0.12 for kw in hard_kw  if kw in text_l)
        # Richer relation structure → better adaptability
        score += min(len(decomp.relations) * 0.05, 0.25)
        return max(0.1, min(1.0, score))

    def _goal_relevance(self, text: str) -> float:
        """
        Is the analogy serving the stated communication goal?
        """
        comm_goal_kw = [
            "understand", "explain", "clarify", "help", "communicate",
            "reason", "think", "mental model", "conceptualize", "frame",
        ]
        venting_kw = [
            "frustrated", "annoyed", "useless", "terrible", "awful",
            "garbage", "hate", "waste", "broken",
        ]
        text_l = text.lower()
        base   = 0.5
        base  += sum(0.08 for kw in comm_goal_kw if kw in text_l)
        base  -= sum(0.06 for kw in venting_kw   if kw in text_l)
        return max(0.1, min(1.0, base))

    def _knowledge_intensity(self, decomp: ERRDecomposition, text: str) -> float:
        """
        Depth of insight provided by the analogy.
        Higher relational structure → deeper insight.
        """
        insight_kw = [
            "because", "therefore", "implies", "means", "suggests",
            "indicates", "shows", "demonstrates", "reveals", "teaches",
        ]
        text_l = text.lower()
        base   = 0.4
        # Relation density is the main driver
        base  += min(len(decomp.relations) / max(len(decomp.objects), 1) * 0.3, 0.4)
        base  += sum(0.05 for kw in insight_kw if kw in text_l)
        return max(0.1, min(1.0, base))

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_category(self, decomp: ERRDecomposition, text: str) -> str:
        text_l = text.lower()
        scores = {}
        for cat in ["structural", "functional", "process", "cross_domain"]:
            noun_score = sum(1 for n in ANALOGY_NOUN_SIGNATURES[cat] if n in text_l)
            verb_score = sum(1 for v in ANALOGY_VERB_SIGNATURES[cat] if v in text_l)
            obj_score  = sum(1 for o in decomp.objects if o in ANALOGY_NOUN_SIGNATURES[cat])
            scores[cat] = noun_score * 2 + verb_score * 1.5 + obj_score

        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "unknown"

    def _classify_phase(self, text: str) -> str:
        text_l = text.lower()
        phase_scores = {
            phase: sum(1 for kw in kws if kw in text_l)
            for phase, kws in SDLC_PHASES.items()
        }
        best = max(phase_scores, key=phase_scores.get)
        return best if phase_scores[best] > 0 else "unknown"
