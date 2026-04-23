# Data Acquisition Strategy for Analogical Reasoning in Agentic Software Engineering

**Document type:** Methodology justification  
**Scope:** Source selection, ranking rationale, sampling design, and validity considerations for the empirical corpus used to study how software developers use analogical language when reasoning about AI coding agents.

---

## 1. Research Context

### 1.1 What Are Analogies in This Study?

In this research, an *analogy* is any passage in which a developer compares an AI coding agent (e.g., GitHub Copilot, Cursor, Claude Code, ChatGPT) to a concept drawn from another domain — human roles, mechanical tools, physical phenomena, or abstract processes.  Examples of the four analogy types the corpus targets:

| Type | Example |
|------|---------|
| **Process** | "Copilot is like a junior dev who never gets tired but also never remembers the last meeting." |
| **Functional** | "Think of it as a very fast search engine that can also write." |
| **Structural** | "It's an extra layer in your cognitive stack, sitting between intention and keystrokes." |
| **Cross-domain** | "Trusting an AI agent to merge a PR is like handing the wheel to autopilot during takeoff." |

Analogies are not merely rhetorical decoration.  Cognitive science research (Gentner, 1983; Hofstadter & Sander, 2013) establishes that analogical reasoning is a primary mechanism by which people construct and communicate mental models.  When developers write analogies about AI agents, they externalize the mental model they use to predict, trust, and debug those agents.  That makes analogies a direct empirical window into how agentic SE tools are actually understood in practice.

### 1.2 Why Developer Platforms Specifically?

Prior work on mental models of software tools (e.g., Ericsson & Simon's think-aloud studies; Ko et al.'s misconceptions research) relies heavily on lab studies that are expensive to conduct and difficult to scale.  Publicly available developer discourse offers a complementary, ecologically valid alternative: developers write about their real frustrations, surprises, and conceptual frames *at the moment they experience them*, without observer effects.

The platforms in this corpus represent the full spectrum of developer communication:

- **Q&A** (Stack Overflow, HN) — problem-framing language, highest density of "explain X to me" analogies
- **Long-form blogging** (DEV, Hashnode) — reflective, narrative analogies in tutorials and opinion pieces
- **Issue trackers** (GitHub, GitLab) — analogies in design rationale, bug descriptions, and code-review comments
- **Link aggregators** (HN, Lobsters) — conversational discussion analogies, often spontaneous
- **Research archives** (Zenodo) — formal analogies in academic writing and grey literature
- **ML community** (Hugging Face) — practitioner notes adjacent to model development

This breadth ensures the corpus captures analogies that arise at different communication registers (informal vs. technical vs. academic) and at different stages of the software development lifecycle.

---

## 2. Ranking Rationale

The sources are collected in five ordered batches, with each batch representing a distinct trade-off point on four dimensions: **expected analogy yield**, **methodological independence**, **acquisition friction**, and **ethical/legal risk**.

### 2.1 Scoring Framework

Each candidate source is scored on the following criteria:

| Dimension | Description | Weight |
|-----------|-------------|--------|
| **Analogy density** | Estimated fraction of posts/items expected to contain analogy language about AI agents | 35% |
| **Methodological independence** | How different the communicative register is from already-collected sources (reduces corpus bias) | 25% |
| **Acquisition friction** | Ease of API access, stability of endpoints, required credentials, and implementation effort | 25% |
| **Ethical/legal risk** | TOS compliance certainty, PII exposure, redistribution restrictions | 15% |

A source is promoted to the next tier when the expected marginal gain (new unique analogies) justifies the additional acquisition friction and risk.

### 2.2 Tier 1: Original Sources (Baseline Corpus)

The five Tier-1 sources were selected to establish a reliable, maximally accessible baseline before any expansion.

#### Stack Overflow

*Rationale:* Stack Overflow is the canonical reference for how developers articulate technical problems.  Its question-answer structure means analogies appear in two roles: explanatory (in answers, to clarify a concept) and problem-framing (in questions, to communicate symptoms).  The Stack Exchange API is among the most stable and well-documented in the developer tooling ecosystem, and data is released under CC BY-SA 4.0, which explicitly permits academic redistribution.

*Expected yield:* High for functional and structural analogies.  Tags like `github-copilot`, `ai-code-generation`, and `code-completion` surface posts where developers are actively reasoning about what the tool *is* and *does*.

*Independence:* Provides the "formal Q&A" register — structured, technical, post-edited.

#### Reddit

*Rationale:* Reddit communities (subreddits) capture spontaneous, conversational developer opinion.  Unlike Stack Overflow, Reddit posts are rarely edited for precision; they reflect unfiltered first-person experience.  The PRAW wrapper makes access reliable and rate-limit-safe.  Subreddits like `r/ChatGPTCoding`, `r/cursor`, and `r/ClaudeAI` are specifically dedicated to the AI coding tools under study.

*Expected yield:* High for process and cross-domain analogies.  "Copilot is like having a rubber duck that talks back" is Reddit-native language.

*Independence:* Provides the "informal community opinion" register — emotional, first-person, present-tense experience.

#### GitHub

*Rationale:* GitHub issues and discussion threads are written *inside* the tool workflow, often at the exact moment a developer is interacting with an AI agent.  This gives the highest ecological validity of any source.  The GitHub REST API provides full-text search with boolean operators, enabling targeted analogy retrieval without retrieving irrelevant content.

*Expected yield:* Moderate density but very high quality.  Analogies in issue descriptions tend to be precise and actionable ("it behaves like a stateless RPC call — it has no memory of context between sessions").

*Independence:* Provides the "in-workflow engineering" register — pragmatic, tool-specific, context-embedded.

#### Zenodo

*Rationale:* Zenodo hosts grey literature (preprints, technical reports, datasets) that does not appear in traditional academic databases.  This is critical for capturing analogies in semi-formal writing, where authors use analogies more freely than in peer-reviewed venues but more carefully than in blog posts.  No authentication is required, and all content is open access.

*Expected yield:* Low density but high academic rigor.  Analogies found in Zenodo records are likely to be deliberate and conceptually significant.

*Independence:* Provides the "grey literature / semi-academic" register — different from all conversational sources.

#### Hugging Face

*Rationale:* Hugging Face is where AI practitioners document models and datasets.  Model cards often contain explicit analogical explanations written for non-expert readers ("this model is like a translator that has read every programming forum on the internet").  The community is also the epicentre of practitioner-level AI tool development.

*Expected yield:* Low density overall but concentrated in the model card `description` fields of AI coding assistant models and the associated `Spaces` demo apps.

*Independence:* Provides the "ML practitioner" register — technically adjacent to the agents themselves, not just users of them.

---

### 2.3 Tier 2, Batch A: DEV Community and Hashnode

*Why this batch comes first among expansions:*

Both platforms are explicitly built for long-form technical writing.  They are the primary venues where developers publish personal perspectives on AI tools in narrative form — exactly the register most likely to contain sustained analogical reasoning (multiple analogies developed within a single article).  Their APIs are stable, require no authentication for read access, and impose no restrictions on academic use.

#### DEV Community (dev.to)

DEV is the largest open-source-focused developer blogging platform.  Unlike Medium, all content is indexed by a public REST API.  Articles tagged `ai`, `copilot`, `chatgpt`, and `llm` consistently reach tens of thousands of readers and generate comment threads with high analogy density.

*Methodological justification:*
The article-with-comments structure provides two independent analogy contexts from the same discussion: the author's composed, deliberate framing (article body) and the spontaneous reader reactions (comments).  This within-discussion contrast is methodologically valuable for studying whether analogies in reflective writing propagate into conversational agreement or challenge.

*Acquisition friction:* Minimal.  The Forem API is well-documented, requires no auth for up to ~10 req/min, and responses are JSON with clean body markdown.

#### Hashnode

Hashnode is the primary professional developer blogging platform, with a strong presence among practising software engineers (as opposed to students or hobbyists).  Its GraphQL API provides full article body as markdown, author metadata, reaction counts, and response counts in a single query.

*Methodological justification:*
Hashnode's author base skews toward senior engineers who use analogies prescriptively — to onboard their team or teach a mental model.  This provides a corpus complement to the reactive analogies found on Reddit and HN.

*Acquisition friction:* No authentication required.  The GraphQL API supports cursor-based pagination and full content in one call.

---

### 2.4 Tier 2, Batch B: Hacker News and Lobsters

*Why this batch comes second:*

Both are link-aggregator communities where comments (rather than articles) are the primary discourse medium.  The comment thread structure creates a specific analogy context that neither the Q&A sources (SO) nor the blog sources (DEV/Hashnode) cover: *real-time analogical negotiation*, where one commenter offers an analogy and others immediately accept, refine, or reject it.  This dynamic is particularly valuable for studying how developer communities converge on or dispute mental models of AI agents.

#### Hacker News

HN is the most widely read developer news community and has a strong presence among engineers from top-tier technology companies.  The official Algolia HN Search API provides full-text search across all stories and comments since 2006, including the date window relevant to this study (September 2025–February 2026).

*Methodological justification:*
HN threads about AI coding tools (e.g., Copilot launches, Claude Code announcements) generate hundreds of comments within hours of publication.  These threads contain concentrated bursts of comparative reasoning as developers rapidly form and share first impressions — a qualitatively distinct signal from the slower, more considered analogies in blog posts.

*Thread context normalization:* The parent story title is resolved via the Firebase API and stored in the `title` field of each comment record, preserving the semantic context needed to interpret the analogy.

*Acquisition friction:* Very low.  The Algolia API is public, rate-limit-generous, and returns structured JSON.

#### Lobsters

Lobsters is a smaller, curated link-aggregator with a technical audience.  Unlike HN, all submissions are manually tagged and the community is invite-only, which means the discourse quality is consistently high.  The official JSON feed (`lobste.rs/t/<tag>.json`) provides story and comment data without any authentication.

*Methodological justification:*
Lobsters' smaller scale (relative to HN) means analogy density per post is higher because discussions are more focused.  It also provides a different socio-demographic sample — predominantly practising systems and web engineers — which guards against HN's known over-representation of startup culture.

*Acquisition friction:* Minimal.  Official JSON feed with per-tag pagination.  Rate limit of 1 req/sec respects server capacity.

---

### 2.5 Tier 2, Batch C: GitLab

*Why this batch comes third:*

GitLab expands the code-forge coverage established by GitHub in Tier 1.  GitHub and GitLab are complementary, not substitutable: many open-source projects that are politically uncomfortable with GitHub's Microsoft ownership (particularly in the AI tooling space) host on GitLab.  GitLab issue discussions about AI coding tools therefore represent a systematically different project population than GitHub.

*Methodological justification:*
GitLab issues involving AI coding tools often arise in projects that are *building* AI tools or *integrating* them — not just using them.  The analogies in these discussions tend to be more technical and architecture-oriented ("the agent should behave like a POSIX subprocess — blocking, with a clear stdin/stdout contract").  This provides the "system designer" perspective absent from the user-perspective analogies dominant in other sources.

*Project discovery strategy:* The collector uses the GitLab search API to discover projects by keyword (`copilot`, `ai coding assistant`, `llm`, `chatgpt`), then searches for analogy keywords within each discovered project's issues.  This two-stage strategy avoids the combinatorial explosion of searching all ~10 million public projects.

*Acquisition friction:* Moderate.  Without a token the rate limit is 60 req/hr.  A `read_api` personal access token raises this to 2000 req/min.  The free tier is sufficient for pilot runs; a token is recommended for production collection.

---

### 2.6 Tier 3 (Future Batches): Discourse, Transcripts, Private Channels

These sources are ranked below Tier 2 not because of low analogy yield but because of elevated acquisition friction and ethical risk.

#### Batch D: Discourse Communities

Discourse powers forums for many influential developer communities: the Rust Users Forum, the Python Discussion Forum, the Julia Discourse, the PostgreSQL mailing list mirror, and dozens of framework-specific communities.  Each Discourse instance exposes a public JSON API at `/t/<topic-id>.json`.

*Why deferred:*
The primary barrier is that each instance requires its own policy check and allowlist decision.  There is no centralised "Discourse Network API"; each forum must be individually evaluated for TOS compliance, robots.txt constraints, and content licence.  This makes batch collection non-trivial to automate safely.

*Expected yield when implemented:* Very high.  Discourse threads tend to be longer and more substantive than Reddit threads, with higher analogy density per post.

#### Batch E: Conference and Podcast Transcripts

Conference talks (ICSE, FSE, MSR, PLDI) and practitioner podcasts (Changelog, Software Engineering Daily, CoRecursive) contain some of the most carefully constructed analogies produced by the community.  Speakers frequently open talks with an analogy to orient the audience.

*Why deferred:*
Speaker-attributed transcript data requires either (a) the YouTube Data API v3 captions endpoint, which returns timestamped caption segments that require sentence-boundary reconstruction, or (b) manual transcript sources, which vary in format and availability.  The processing pipeline for transcript data is substantially more complex than for structured API responses.

*Expected yield when implemented:* Moderate density, very high quality.  Analogies from named practitioners at named venues carry methodological weight for triangulating the findings from anonymous online discourse.

---

## 3. Corpus Validity Considerations

### 3.1 Construct Validity

The study's construct (analogical reasoning about AI agents) is operationalised through keyword matching: posts must contain both an *analogy indicator* (`"like a"`, `"similar to"`, `"metaphor"`, etc.) and an *agent term* (`"Copilot"`, `"Cursor"`, `"Claude Code"`, etc.).  This is a conservative, high-precision filter.

**Risk:** Analogies expressed without explicit indicators (e.g., "Copilot just autocompletes — it has no intent") will be missed.  
**Mitigation:** The keyword list is expandable via `config.yaml` without code changes.  The `analogy_confidence` score provides a graded measure that allows threshold tuning during analysis.

### 3.2 Internal Validity

The corpus spans multiple platforms, languages, and discourse contexts.  Analogy frequency and type may reflect platform culture as much as genuine reasoning patterns.

**Risk:** Source composition effects — if 80% of records come from one platform, findings may over-generalise from that platform's community norms.  
**Mitigation:** The collection report now includes per-source yield rates and analogy-type distributions.  Analysis should weight by source diversity, not raw record count.

### 3.3 External Validity

Developers who write publicly about their AI tool experiences are not a random sample of all developers.  They tend to be more active in open-source communities and more opinionated.

**Risk:** The corpus may over-represent enthusiasts (positive analogies) or vocal critics (negative analogies) and under-represent silent majority experiences.  
**Mitigation:** The survey component (`tools/survey_collector.py`) is designed to sample outside the public discourse community.  The two corpora (discourse + survey) should be analysed separately and compared explicitly.

### 3.4 Temporal Validity

AI coding tools are evolving rapidly.  An analogy that captures Copilot's behaviour in September 2025 may be obsolete by February 2026 after a major model update.

**Risk:** Temporal drift within the collection window may conflate different product states.  
**Mitigation:** The `post_date` field is collected for all records.  Temporal analysis (by quarter) is included in `examples/analysis_template.py`.

### 3.5 Cross-Platform Author Deduplication

As documented in the `README.md`, it is impossible to deduplicate authors *across* platforms without verified identity linking.  A developer who posts on Stack Overflow, Reddit, and HN about the same experience will contribute three records that appear to be from three different people.

**Risk:** Over-counting prolific multi-platform contributors inflates both sample size and analogy diversity estimates.  
**Mitigation:** All cross-platform count claims (e.g., "N unique developers") must explicitly acknowledge this limitation.  Within-platform deduplication (via `record_id` + TF-IDF near-duplicate detection) is performed in `core/deduplicator.py`.

---

## 4. Source Independence Matrix

A key methodological goal is that sources are not only numerous but *independent* — each capturing a different communicative register.  The matrix below characterises the independence of the ten sources across five dimensions:

| Source | Register | Synchrony | Audience | Artifact Type | Moderation |
|--------|----------|-----------|----------|---------------|------------|
| Stack Overflow | Formal Q&A | Async | Mixed | Question/Answer | Strong (votes/review) |
| Reddit | Informal opinion | Async | Consumer | Post/Comment | Community |
| GitHub | In-workflow engineering | Async | Developer | Issue/Discussion | None |
| Zenodo | Semi-academic | Async | Researcher | Paper/Report | Editorial |
| Hugging Face | ML practitioner | Async | Researcher/Practitioner | Model card | None |
| DEV Community | Personal blog | Async | Developer | Article/Comment | Light |
| Hashnode | Professional blog | Async | Engineer | Article | Light |
| Hacker News | Aggregator discussion | Near-realtime | Mixed | Story/Comment | Self-selection |
| Lobsters | Aggregator discussion | Near-realtime | Technical | Story/Comment | Invite-only |
| GitLab | In-workflow engineering | Async | Developer | Issue/Note | Repository-owner |

No two sources share the same combination of all five dimensions, which supports treating them as providing genuinely independent evidence about analogical reasoning patterns.

---

## 5. Expected Contribution Per Batch

The following estimates are based on pilot scoping runs and analogy density patterns from prior manual analysis:

| Batch | Sources | Expected New Analogies | Primary Analogy Type | Methodological Contribution |
|-------|---------|----------------------|---------------------|---------------------------|
| Tier 1 (baseline) | SO, Reddit, GitHub, Zenodo, HF | 15,000–25,000 | Mixed | Establishes baseline across Q&A, social, code forge, academic |
| Batch A | DEV, Hashnode | 3,000–8,000 | Process, Cross-domain | Long-form narrative analogies; author-deliberate framing |
| Batch B | HN, Lobsters | 5,000–12,000 | Functional, Cross-domain | Real-time analogical negotiation; community convergence |
| Batch C | GitLab | 2,000–5,000 | Structural, Functional | System-designer perspective; architecture analogies |
| Batch D (future) | Discourse communities | 4,000–10,000 | All types | High-quality sustained discussions |
| Batch E (future) | Transcripts | 500–2,000 | All types | Named-practitioner analogies; highest methodological weight |

---

## 6. References

Gentner, D. (1983). Structure-mapping: A theoretical framework for analogy. *Cognitive Science, 7*(2), 155–170.

Hofstadter, D., & Sander, E. (2013). *Surfaces and Essences: Analogy as the Fuel and Fire of Thinking*. Basic Books.

Ko, A. J., Myers, B. A., Coblenz, M. J., & Aung, H. H. (2006). An exploratory study of how developers seek, relate, and collect relevant information during software maintenance tasks. *IEEE Transactions on Software Engineering, 32*(12), 971–987.

Ericsson, K. A., & Simon, H. A. (1993). *Protocol Analysis: Verbal Reports as Data* (Rev. ed.). MIT Press.

Storey, M. A., Zagalsky, A., Filho, F. F., Singer, L., & German, D. M. (2016). How social and communication channels shape and challenge a participatory culture in software development. *IEEE Transactions on Software Engineering, 43*(2), 185–204.

Treude, C., & Robillard, M. P. (2016). Augmenting API documentation with insights from Stack Overflow. *Proceedings of ICSE 2016*, 392–403.

Vasilescu, B., Filkov, V., & Serebrenik, A. (2013). StackOverflow and GitHub: Associations between software development and crowdsourced knowledge. *Proceedings of SocialCom 2013*, 188–195.

---

*This document should be updated whenever a new source is added to the acquisition pipeline.  All claims about expected yield should be validated against actual pilot-run statistics and this document revised accordingly.*
