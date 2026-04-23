# Source Policy Matrix

This document is the authoritative allowlist for all data sources used in the
Analogical Reasoning Collector.  Every source **must** appear here before it
can be enabled in `config.yaml`.  If a source fails any gate it must remain
`enabled: false` until the issue is resolved.

---

## Gate Criteria

| Gate | Pass Condition |
|------|----------------|
| **API** | Public REST/GraphQL API exists with documented endpoints |
| **TOS** | Platform ToS permits non-commercial academic research scraping or explicitly provides an API for it |
| **Robots** | `robots.txt` does not disallow crawlers on target paths; or an official API is used (overrides robots) |
| **Auth** | Authentication mechanism is clearly documented and obtainable without special approval |
| **PII** | Data does not contain non-pseudonymous PII that cannot be anonymised at collection time |
| **Redistrib.** | Raw data can be shared in a replication package, OR schema + identifiers (no raw text) are sufficient |

---

## Current Allowlist

### Tier 1 — Active (enabled by default)

| Source | API | TOS | Robots | Auth | PII | Redistrib. | Env Var | Notes |
|--------|-----|-----|--------|------|-----|------------|---------|-------|
| Stack Overflow | REST (api.stackexchange.com/2.3) | [Stack Exchange API Terms](https://stackapps.com/terms) — academic use permitted | API used | Optional key | Username pseudonymous | CC BY-SA 4.0 | `STACKOVERFLOW_API_KEY` | No key = 300 req/day quota |
| Reddit | PRAW (official wrapper) | [Reddit API Terms](https://www.reddit.com/wiki/api-terms) — approved for academic | API used | Required: client_id + secret | Username pseudonymous | Content covered by Reddit ToS; identifiers shareable | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Free-tier API |
| GitHub | REST (api.github.com) | [GitHub ToS](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) — public data OK | API used | Required: PAT | Username pseudonymous | Public content shareable | `GITHUB_TOKEN` | `repo` + `read:discussion` scopes |
| Zenodo | REST (zenodo.org/api) | [Zenodo Privacy](https://about.zenodo.org/privacy-policy/) — open access | API used | None required | Authors listed by choice | Open Access; CC-BY | — | Rich metadata |
| Hugging Face | REST (huggingface.co/api) | [HF ToS](https://huggingface.co/terms-of-service) — public data OK | API used | Optional token | Username pseudonymous | Model cards shareable | `HUGGINGFACE_TOKEN` | Token gives higher limits |

### Tier 2 — Active (enabled by default, new sources)

| Source | API | TOS | Robots | Auth | PII | Redistrib. | Env Var | Notes |
|--------|-----|-----|--------|------|-----|------------|---------|-------|
| DEV Community (dev.to) | REST (dev.to/api) | [DEV ToS](https://dev.to/terms) — public articles; API available | API used | Optional key | Username pseudonymous | Content under author license; identifiers shareable | `DEVTO_API_KEY` | Key raises rate limit from 10 to 1000 req/min |
| Hashnode | GraphQL (gql.hashnode.com) | [Hashnode ToS](https://hashnode.com/terms) — public posts | API used | None required | Username pseudonymous | Identifiers shareable | — | Free, no auth needed |
| Hacker News | REST + Algolia Search | [HN Guidelines](https://news.ycombinator.com/newsguidelines.html); Algolia partnership official | Algolia API used | None required | Username pseudonymous | Public content; identifiers shareable | — | Firebase API fully public |
| Lobsters | JSON/RSS (lobste.rs) | [Lobsters FAQ](https://lobste.rs/about) — public data; JSON feed official | JSON feed used | None required | Username pseudonymous | Public content; identifiers shareable | — | No scraping; official JSON feed only |
| GitLab | REST (gitlab.com/api/v4) | [GitLab ToS](https://about.gitlab.com/terms/) — public projects API | API used | Optional token | Username pseudonymous | Public issues shareable | `GITLAB_TOKEN` | Without token: 60 req/hr |

### Tier 3 — Disabled (ethical/legal review required)

| Source | Blocker | Resolution Path |
|--------|---------|-----------------|
| Discord | Requires server owner written permission; no public API for message history | Get explicit written consent per server; re-enable per-channel in config |
| YouTube Transcripts | auto-generated captions: ToS §4.B forbids automated scraping without API; transcript API deprecated | Use YouTube Data API v3 captions endpoint; require video creator consent for research use |
| Podcast transcripts | Varies per publisher; no universal API | Obtain permission from publisher; use official transcript feeds (e.g., Changelog provides transcripts) |
| Slack archives | Requires workspace admin export; ToS restricts redistribution | Only usable with explicit organizational data sharing agreement + IRB |
| Jira/internal tools | Proprietary; ToS prohibits access without account | Formal data sharing agreement + IRB approval required |

---

## Per-Source Attribution Requirements

When publishing a replication package, include the following per source:

| Source | Required Attribution |
|--------|---------------------|
| Stack Overflow | "Data collected via Stack Exchange API under CC BY-SA 4.0. Original post links included." |
| Reddit | "Data collected via Reddit API. Per Reddit Terms, raw content not redistributed; record IDs and metadata only." |
| GitHub | "Data collected via GitHub API. Public issue/discussion data under repository's license." |
| Zenodo | "Data collected via Zenodo API. Records under their respective open-access licenses (see `archive_url` field)." |
| Hugging Face | "Data collected via Hugging Face API. Model card content under repository license." |
| DEV Community | "Data collected via DEV.to API. Articles under author-specified licenses." |
| Hashnode | "Data collected via Hashnode GraphQL API. Articles under author-specified licenses." |
| Hacker News | "Data collected via Algolia HN Search API. Content under HN terms." |
| Lobsters | "Data collected via Lobsters official JSON feed." |
| GitLab | "Data collected via GitLab API. Public issue content under repository license." |

---

## Adding a New Source

1. Verify all 6 gate criteria above.
2. Add a row to the appropriate tier table in this file.
3. Add the platform section to `config.yaml` with `enabled: false` initially.
4. Implement `collectors/<platform>.py` inheriting from `BaseCollector`.
5. Register in `core/orchestrator.py` `PLATFORM_COLLECTORS` dict.
6. Add credentials to `.env.example` if needed.
7. Run a 1-day pilot crawl and record yield in this file.
8. Set `enabled: true` once quality review passes.
