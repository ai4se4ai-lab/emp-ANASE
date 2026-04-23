# Analogical Reasoning Data Collector

A comprehensive, ethically-compliant data collection framework for studying analogical reasoning in agentic software engineering.

## ⚠️ Ethical & Legal Requirements

**Before using this tool, you must:**

1. **Obtain API keys legitimately** from each platform
2. **Respect rate limits** (configured in `config.yaml`)
3. **Comply with Terms of Service** for each platform:
   - [Stack Exchange API Terms](https://stackapps.com/terms)
   - [Reddit API Terms](https://www.reddit.com/wiki/api-terms)
   - [GitHub API Terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)
   - [Zenodo Policies](https://about.zenodo.org/privacy-policy/)
4. **Discord requires explicit server owner permission** — disabled by default
5. **Anonymize all PII** before publication
6. **Obtain IRB approval** if collecting survey data

## 📁 Project Structure

```
crawler/
├── config.yaml                 # Main configuration
├── .env.example               # API key template
├── requirements.txt           # Python dependencies
├── main.py                    # CLI entrypoint wrapper
├── SOURCE_POLICY.md            # Source allowlist + gate criteria
├── collectors/                # Platform-specific collectors
│   ├── base.py
│   ├── stackoverflow.py       # Tier 1
│   ├── reddit.py              # Tier 1
│   ├── github.py              # Tier 1
│   ├── zenodo.py              # Tier 1
│   ├── huggingface.py         # Tier 1
│   ├── devto.py               # Tier 2 — Batch A
│   ├── hashnode.py            # Tier 2 — Batch A
│   ├── hackernews.py          # Tier 2 — Batch B
│   ├── lobsters.py            # Tier 2 — Batch B
│   ├── gitlab.py              # Tier 2 — Batch C
│   └── discord.py             # Tier 3 — disabled by default
├── core/                      # Pipeline orchestration and core logic
│   ├── orchestrator.py
│   └── deduplicator.py
├── tools/                     # Data quality and survey utilities
│   ├── data_validator.py
│   └── survey_collector.py
├── examples/                  # Analysis scaffolding
│   └── analysis_template.py
└── output/                    # Collected data (created at runtime)
    ├── stackoverflow_analogies.csv
    ├── reddit_analogies.csv
    ├── github_analogies.csv
    ├── zenodo_analogies.csv
    ├── combined_analogies_YYYYMMDD_HHMMSS.csv
    └── collection_report.txt
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

**Required credentials:**

| Platform | Variable | Required? | How to Obtain |
|----------|----------|-----------|---------------|
| Stack Overflow | `STACKOVERFLOW_API_KEY` | Optional | [Stack Apps](https://stackapps.com/apps/oauth/register) |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | **Required** | [Reddit Apps](https://www.reddit.com/prefs/apps) |
| GitHub | `GITHUB_TOKEN` | **Required** | [GitHub Settings](https://github.com/settings/tokens) (`repo` + `read:discussion`) |
| Zenodo | — | None | Search is public |
| Hugging Face | `HUGGINGFACE_TOKEN` | Optional | [HF Settings](https://huggingface.co/settings/tokens) |
| DEV Community | `DEVTO_API_KEY` | Optional | [dev.to Settings](https://dev.to/settings/extensions) |
| Hashnode | — | None | GraphQL API is public |
| Hacker News | — | None | Algolia API is public |
| Lobsters | — | None | JSON feed is public |
| GitLab | `GITLAB_TOKEN` | Optional | [GitLab Settings](https://gitlab.com/-/user_settings/personal_access_tokens) (`read_api` scope) |
| Discord | `DISCORD_BOT_TOKEN` | Required + permission | [Discord Developer Portal](https://discord.com/developers/applications) (server owner consent required) |

### 3. Configure Collection Parameters

Edit `config.yaml` to adjust:
- Date ranges
- Target subreddits/tags
- Analogy detection keywords
- Rate limits
- Output schema

### 4. Run Collection

```bash
# Collect from all enabled platforms (Tier 1 + Tier 2)
python main.py

# Collect from specific platforms only
python main.py --platforms stackoverflow,reddit

# Collect from all Tier-2 new sources only
python main.py --platforms devto,hashnode,hackernews,lobsters,gitlab

# Skip deduplication (faster, but may include duplicates)
python main.py --skip-dedup
```

## 📊 Output Schema

Each collected record contains:

| Field | Description | Example |
|-------|-------------|---------|
| `record_id` | Unique identifier | `SO-12345678` |
| `platform` | Source platform | `stackoverflow` |
| `source_type` | Post, comment, issue, etc. | `question` |
| `url` | Direct link to source | `https://stackoverflow.com/questions/...` |
| `archive_url` | Web archive snapshot | `https://webcache.googleusercontent.com/...` |
| `title` | Post title | "How to debug Copilot suggestions?" |
| `author_handle` | Username (anonymized in replication) | `dev_user_42` |
| `author_id_hash` | SHA-256 hash for deduplication | `a3f5c8...` |
| `post_date` | ISO 8601 timestamp | `2025-10-15T14:30:00` |
| `collection_date` | When we collected it | `2026-04-22T09:23:00` |
| `content` | Full text | "Copilot is like a junior dev who..." |
| `content_length` | Character count | `450` |
| `analogy_present` | Boolean flag | `True` |
| `analogy_types` | Comma-separated categories | `functional,process` |
| `analogy_quote` | Exact analogy substring | "like a junior dev who..." |
| `analogy_confidence` | Detection confidence (0-1) | `0.85` |
| `target_domain` | AI tool being described | `GitHub Copilot` |
| `source_domain` | Real-world comparison | `junior developer` |
| `sldc_phase` | Software lifecycle phase | `debugging` |
| `engagement_score` | Platform-specific metric | `42` |
| `upvotes` | Positive votes | `42` |
| `replies` | Number of replies/comments | `5` |
| `views` | View count (if available) | `1200` |
| `verified_by` | Verification method | `api` |
| `collector_version` | Tool version | `1.0.0` |

## 🔍 Analogy Detection Methodology

The collector uses a two-stage heuristic:

1. **Keyword Matching**: Content must contain BOTH:
   - An analogy indicator ("like a", "similar to", "analogy", "metaphor", etc.)
   - An agent term ("Copilot", "Cursor", "AI agent", etc.)

2. **Exclusion Filtering**: Content is excluded if it contains:
   - AI art/generation terms ("DALL-E", "Midjourney")
   - Gaming terms
   - Non-developer contexts

3. **Classification**: Analogies are categorized using pattern matching:
   - **Structural**: architecture, stack, layer, foundation
   - **Functional**: tool, drill, engine, instrument
   - **Process**: junior dev, intern, collaboration, pair programming
   - **Cross-Domain**: lottery, weather, driving, cooking

## 🧮 Deduplication

The pipeline performs two-stage deduplication:

1. **Exact deduplication**: MD5 hash of content
2. **Near-duplicate detection**: TF-IDF cosine similarity ≥ 0.85

**Important limitation**: Cross-platform author deduplication is **impossible** without verified identity linking (e.g., OAuth). Stack Overflow usernames, Reddit handles, and GitHub logins are not cross-referenceable. Claims of "753 unique developers" across platforms are methodologically unsound without such linking.

## 📝 Survey Data Collection

For the survey component (n=52 in the paper), use `tools/survey_collector.py`:

```python
from tools.survey_collector import SurveyCollector

survey = SurveyCollector()
survey.add_response(
    participant_id="P001",
    experience_years=6,
    analogy_types=["functional", "process"],
    effectiveness_rating=4,
    critical_thinking_improved=True,
    breakdown_experienced=False,
    open_ended="I think of Copilot like a very fast junior dev..."
)
survey.export("survey_data.csv")
```

**Survey data requires IRB approval** and informed consent before collection.

## ✅ Data Validation

Use `tools/data_validator.py` to verify collected data before publication:

```python
from tools.data_validator import DataValidator

validator = DataValidator()
results = validator.validate_dataset("output/combined_analogies.csv")
# Checks:
# - All URLs resolve (200 OK)
# - No fabricated citations
# - Content matches URL
# - Engagement metrics are plausible
```

## 🧪 Staged Pilot Rollout

Before enabling new sources in a full collection run, validate each batch
with a 1-day smoke test.  The recommended sequence:

### Batch A — DEV Community + Hashnode

```bash
# Smoke test: 1 page per tag, no dedup
python main.py --platforms devto,hashnode --skip-dedup
# Review output
python -c "
import pandas as pd, glob
f = sorted(glob.glob('output/*analogies*.csv'))[-1]
df = pd.read_csv(f)
print(df[df.platform.isin(['devto','hashnode'])][['platform','source_type','analogy_confidence']].describe())
"
```

### Batch B — Hacker News + Lobsters

```bash
python main.py --platforms hackernews,lobsters --skip-dedup
```

### Batch C — GitLab

```bash
python main.py --platforms gitlab --skip-dedup
```

### Full Tier-2 run after pilots pass

```bash
python main.py --platforms devto,hashnode,hackernews,lobsters,gitlab
# Or combined with Tier-1:
python main.py
```

### Validate and compare yield

```bash
make validate
# Check collection_report.txt for per-source analogy yield rates
cat output/collection_report.txt
```

## 🐛 Troubleshooting

### "Rate limit exceeded"
- Increase `rate_limits` values in `config.yaml`
- For Stack Overflow, add an API key for 30 req/sec quota

### "Reddit authentication failed"
- Ensure your Reddit app is of type "script"
- Verify client_id and client_secret match exactly

### "GitHub search returns 422"
- GitHub search requires `repo:` qualifier for code search
- Ensure your token has `repo` scope

### "No records found"
- Check that date ranges in `config.yaml` are reasonable
- Verify keyword lists include relevant terms
- Some platforms may have no content matching criteria

## 📚 Citation

If you use this tool in your research, cite:

```bibtex
@software{analogical_reasoning_collector,
  title = {Analogical Reasoning Data Collector},
  year = {2026},
  note = {Academic data collection framework for agentic SE research}
}
```

## 📄 License

This tool is provided for academic research purposes. Users are responsible for complying with all applicable platform Terms of Service and data protection regulations.