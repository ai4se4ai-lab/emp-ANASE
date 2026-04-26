"""
LLM-based second-pass analogy verifier.

Determines whether a candidate quote identified by the heuristic filter is a
genuine cross-domain analogy (source domain mapped to target domain) or a false
positive (exemplification, preference statement, same-domain comparison, etc.).

Supported providers (selected via config.yaml -> llm_verifier.provider):
  openai            — OpenAI cloud API (GPT-4o, GPT-4o-mini, …)
  anthropic         — Anthropic Claude cloud API
  ollama            — Local Ollama server (no key required)
  lmstudio          — Local LM Studio OpenAI-compatible server
  openai_compatible — Any OpenAI-compatible endpoint (vLLM, llama.cpp, Groq, etc.)
  disabled          — Skip LLM verification; accept heuristic verdict unchanged

Responses are cached in a JSONL file keyed by sha256(provider+model+quote+ctx)
so repeat runs make zero new API calls.

On any network error or timeout the verifier falls back to the heuristic verdict
and logs a warning — it never crashes the collection pipeline.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger('llm_verifier')

# ------------------------------------------------------------------ #
# Prompt                                                               #
# ------------------------------------------------------------------ #

_SYSTEM_PROMPT = """\
You are a linguistic analyst specialising in analogical reasoning in technical discourse.

Your task: decide whether a candidate text excerpt is a genuine cross-domain analogy.

DEFINITION
A genuine analogy requires ALL THREE of:
  1. A SOURCE DOMAIN — something familiar from a different field (cooking, driving,
     biology, human roles, plumbing, weather, games, etc.)
  2. A TARGET DOMAIN — the software-engineering concept being explained (a bug, an
     API, an architecture pattern, a tool, a workflow, etc.)
  3. A MAPPING — the excerpt explicitly draws a structural or functional parallel
     between source and target ("X is like a Y", "works like", "behaves like", etc.)

NOT analogies:
  - Exemplification: "tools like a language server" means "such as", not a comparison.
  - Preference / desire: "I'd like a faster compiler" — no mapping.
  - Same-domain comparison: "Service A works like Service B" — same domain.
  - Plain description: "the cache stores key-value pairs" — no comparison at all.

OUTPUT FORMAT — respond ONLY with a JSON object, nothing else:
{
  "is_analogy": true | false,
  "source_domain": "<brief noun phrase or empty string>",
  "target_domain": "<brief noun phrase or empty string>",
  "mapping_summary": "<one sentence describing the structural mapping or empty string>",
  "confidence": <float 0.0–1.0>,
  "reason": "<one sentence explaining your decision>"
}

If you cannot extract source/target cleanly, leave those fields as empty strings.
"""

_USER_TEMPLATE = """\
CONTEXT (surrounding text for disambiguation):
{context}

CANDIDATE QUOTE:
{quote}

Is this a genuine cross-domain analogy? Respond with JSON only.
"""

# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _cache_key(provider: str, model: str, quote: str, context: str) -> str:
    payload = f"{provider}|{model}|{quote}|{context[:300]}"
    return hashlib.sha256(payload.encode('utf-8', errors='replace')).hexdigest()


def _parse_response(raw: str) -> Dict[str, Any]:
    """
    Extract JSON from the model response, tolerating markdown code fences.
    Returns a dict with is_analogy=True on parse failure so marginal cases
    are not silently dropped.
    """
    text = raw.strip()
    # Strip optional ``` fences
    if text.startswith('```'):
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'```$', '', text.strip())
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or 'is_analogy' not in data:
            raise ValueError("missing is_analogy key")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM response parse failed (%s); treating as analogy. Raw: %.200s", exc, raw)
        return {
            'is_analogy': True,
            'source_domain': '',
            'target_domain': '',
            'mapping_summary': '',
            'confidence': 0.5,
            'reason': f'parse_error: {exc}',
        }


# re import needed inside helpers above
import re


# ------------------------------------------------------------------ #
# LLMVerifier                                                         #
# ------------------------------------------------------------------ #

class LLMVerifier:
    """
    Provider-agnostic LLM analogy verifier.

    Usage:
        verifier = LLMVerifier(config)
        result = verifier.verify(quote, context_snippet)
        # result: {is_analogy, source_domain, target_domain,
        #          mapping_summary, confidence, reason}
    """

    def __init__(self, config: Dict[str, Any]):
        lv = config.get('llm_verifier', {})
        self.enabled: bool = lv.get('enabled', False)
        self.provider: str = lv.get('provider', 'disabled').lower()
        self.model: str = lv.get('model', '')
        self.temperature: float = float(lv.get('temperature', 0))
        self.rps: float = float(lv.get('requests_per_second', 2))
        self.timeout: int = int(lv.get('timeout_seconds', 60))
        self.health_check: bool = lv.get('health_check_on_start', True)
        self.context_chars: int = int(lv.get('context_chars', 600))

        cache_path = lv.get('cache_path', './output/llm_cache.jsonl')
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Load provider-specific settings
        providers_cfg = lv.get('providers', {})
        self._prov_cfg = providers_cfg.get(self.provider, {})

        # In-memory cache (populated from disk on first verify call)
        self._cache: Optional[Dict[str, Dict]] = None
        self._last_call_time: float = 0.0

        # Will be set to False if health check fails
        self._active = self.enabled and self.provider != 'disabled'

        if not self._active:
            logger.info("LLM verifier disabled (provider=%s).", self.provider)
            return

        logger.info("LLM verifier configured: provider=%s model=%s", self.provider, self.model)

        if self.health_check:
            self._run_health_check()

    # ------------------------------------------------------------------ #
    # Cache                                                               #
    # ------------------------------------------------------------------ #

    def _load_cache(self):
        self._cache = {}
        if self.cache_path.exists():
            with open(self.cache_path, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._cache[entry['key']] = entry['value']
                    except (json.JSONDecodeError, KeyError):
                        pass
            logger.info("LLM cache loaded: %d entries from %s", len(self._cache), self.cache_path)

    def _save_to_cache(self, key: str, value: Dict[str, Any]):
        self._cache[key] = value
        with open(self.cache_path, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps({'key': key, 'value': value}, ensure_ascii=False) + '\n')

    # ------------------------------------------------------------------ #
    # Rate limiting                                                       #
    # ------------------------------------------------------------------ #

    def _rate_limit(self):
        if self.rps <= 0:
            return
        min_interval = 1.0 / self.rps
        elapsed = time.monotonic() - self._last_call_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call_time = time.monotonic()

    # ------------------------------------------------------------------ #
    # Provider backends                                                   #
    # ------------------------------------------------------------------ #

    def _call_openai_sdk(self, messages: list, base_url: Optional[str] = None,
                          api_key: Optional[str] = None) -> str:
        """Send messages via the openai SDK (works for OpenAI, LM Studio, compatible)."""
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        kwargs: Dict[str, Any] = {}
        if base_url:
            kwargs['base_url'] = base_url
        if api_key:
            kwargs['api_key'] = api_key
        elif not base_url:
            # Cloud OpenAI — let SDK read OPENAI_API_KEY from env
            pass
        else:
            # Local server that ignores keys; pass a placeholder
            kwargs['api_key'] = 'local'

        client = OpenAI(timeout=self.timeout, **kwargs)
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            response_format={"type": "json_object"} if self.provider != 'ollama' else None,
        )
        return resp.choices[0].message.content or ''

    def _call_anthropic(self, messages: list) -> str:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        api_key_env = self._prov_cfg.get('api_key_env', 'ANTHROPIC_API_KEY')
        api_key = os.environ.get(api_key_env, '')
        client = anthropic.Anthropic(api_key=api_key, timeout=self.timeout)
        # Anthropic separates system from human turns
        system = messages[0]['content'] if messages and messages[0]['role'] == 'system' else ''
        human_msgs = [m for m in messages if m['role'] != 'system']
        resp = client.messages.create(
            model=self.model,
            max_tokens=512,
            temperature=self.temperature,
            system=system,
            messages=human_msgs,
        )
        return resp.content[0].text if resp.content else ''

    def _call_ollama(self, messages: list) -> str:
        """Call Ollama native /api/chat endpoint via requests."""
        import requests as req
        base_url = self._prov_cfg.get('base_url', 'http://localhost:11434')
        url = f"{base_url.rstrip('/')}/api/chat"
        payload = {
            'model': self.model,
            'messages': messages,
            'stream': False,
            'options': {'temperature': self.temperature},
            'format': 'json',
        }
        resp = req.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get('message', {}).get('content', '')

    def _call_backend(self, messages: list) -> str:
        """Route to the correct backend based on self.provider."""
        if self.provider == 'openai':
            api_key_env = self._prov_cfg.get('api_key_env', 'OPENAI_API_KEY')
            api_key = os.environ.get(api_key_env, '')
            base_url = self._prov_cfg.get('base_url')
            return self._call_openai_sdk(messages, base_url=base_url, api_key=api_key)

        if self.provider == 'anthropic':
            return self._call_anthropic(messages)

        if self.provider == 'ollama':
            return self._call_ollama(messages)

        if self.provider in ('lmstudio', 'openai_compatible'):
            base_url = self._prov_cfg.get('base_url', 'http://localhost:1234/v1')
            api_key_env = self._prov_cfg.get('api_key_env', '')
            api_key = os.environ.get(api_key_env, 'local') if api_key_env else 'local'
            return self._call_openai_sdk(messages, base_url=base_url, api_key=api_key)

        raise ValueError(f"Unknown provider: {self.provider}")

    # ------------------------------------------------------------------ #
    # Health check                                                        #
    # ------------------------------------------------------------------ #

    def _run_health_check(self):
        logger.info("Running LLM verifier health check (provider=%s model=%s)…",
                    self.provider, self.model)
        try:
            self._rate_limit()
            probe = [
                {"role": "system", "content": "Reply with the JSON: {\"ok\": true}"},
                {"role": "user", "content": "health check"},
            ]
            raw = self._call_backend(probe)
            data = json.loads(raw.strip())
            if data.get('ok'):
                logger.info("LLM verifier health check PASSED.")
            else:
                raise ValueError(f"Unexpected health-check response: {raw[:80]}")
        except Exception as exc:
            logger.warning(
                "LLM verifier health check FAILED (%s). "
                "Disabling LLM verification for this run.", exc
            )
            self._active = False

    # ------------------------------------------------------------------ #
    # Public verify()                                                     #
    # ------------------------------------------------------------------ #

    def verify(self, quote: str, context_snippet: str = '') -> Dict[str, Any]:
        """
        Verify whether *quote* is a genuine cross-domain analogy.

        Returns a dict with keys:
            is_analogy       bool
            source_domain    str
            target_domain    str
            mapping_summary  str
            confidence       float
            reason           str
            llm_provider_model str
        """
        _fallback = {
            'is_analogy': True,
            'source_domain': '',
            'target_domain': '',
            'mapping_summary': '',
            'confidence': 0.5,
            'reason': 'llm_disabled_or_error',
            'llm_provider_model': f"{self.provider}/{self.model}",
        }

        if not self._active:
            return _fallback

        # Lazy load disk cache
        if self._cache is None:
            self._load_cache()

        ctx = context_snippet[:self.context_chars]
        key = _cache_key(self.provider, self.model, quote, ctx)

        if key in self._cache:
            cached = dict(self._cache[key])
            cached['llm_provider_model'] = f"{self.provider}/{self.model}"
            return cached

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(
                context=ctx or "(no surrounding context provided)",
                quote=quote,
            )},
        ]

        try:
            self._rate_limit()
            raw = self._call_backend(messages)
            result = _parse_response(raw)
        except Exception as exc:
            logger.warning(
                "LLM verification call failed (%s); falling back to heuristic verdict.", exc
            )
            return _fallback

        result['llm_provider_model'] = f"{self.provider}/{self.model}"
        self._save_to_cache(key, result)
        return result

    @property
    def is_active(self) -> bool:
        return self._active
