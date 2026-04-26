#!/usr/bin/env python3
"""
Main Orchestrator for Analogical Reasoning Data Collection
Coordinates collection across all platforms, deduplication, and export.

Usage:
    python main.py --config config.yaml --platforms all
    python main.py --config config.yaml --platforms stackoverflow,reddit
    python main.py --config config.yaml --skip-dedup

Ethical Requirements:
1. All API keys must be obtained legitimately
2. Discord collection requires server owner written permission
3. Rate limits must be respected
4. Collected data must comply with platform Terms of Service
5. PII must be anonymized in any publication
"""

import argparse
import importlib
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv
import pandas as pd
import yaml

# Resolve project root and load environment variables from crawler/.env.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from core.deduplicator import Deduplicator


def setup_logging(log_dir: str = "./logs"):
    """Configure logging for the entire pipeline."""
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"{log_dir}/orchestrator_{timestamp}.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('orchestrator')


def load_config(config_path: str) -> Dict[str, Any]:
    """Load and validate configuration."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required directories
    os.makedirs(config['project']['output_dir'], exist_ok=True)
    os.makedirs(config['project'].get('log_dir', './logs'), exist_ok=True)

    return config


def collect_platform(platform_name: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Initialize and run a specific platform collector."""
    logger = logging.getLogger('orchestrator')

    collectors = {
        # Tier 1 — original sources
        'stackoverflow': 'collectors.stackoverflow.StackoverflowCollector',
        'reddit': 'collectors.reddit.RedditCollector',
        'github': 'collectors.github.GithubCollector',
        'zenodo': 'collectors.zenodo.ZenodoCollector',
        'huggingface': 'collectors.huggingface.HuggingfaceCollector',
        # Tier 2 — expanded sources (Batch A)
        'devto': 'collectors.devto.DevtoCollector',
        'hashnode': 'collectors.hashnode.HashnodeCollector',
        # Tier 2 — expanded sources (Batch B)
        'hackernews': 'collectors.hackernews.HackernewsCollector',
        'lobsters': 'collectors.lobsters.LobstersCollector',
        # Tier 2 — expanded sources (Batch C)
        'gitlab': 'collectors.gitlab.GitlabCollector',
        # Tier 3 — disabled by default (ethical/legal review required)
        'discord': 'collectors.discord.DiscordCollector',
    }

    if platform_name not in collectors:
        logger.error(f"Unknown platform: {platform_name}")
        return []

    module_name, class_name = collectors[platform_name].rsplit('.', 1)

    try:
        module = importlib.import_module(module_name)
        collector_class = getattr(module, class_name)
        collector = collector_class(config)

        logger.info(f"Starting collection from {platform_name}...")
        records = collector.collect()
        logger.info(f"Collected {len(records)} records from {platform_name}")
        return records

    except Exception as e:
        logger.error(f"Failed to collect from {platform_name}: {e}")
        return []


def apply_runtime_overrides(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Apply CLI-only overrides without mutating config.yaml on disk."""
    # --- GitHub repo selection ---
    github_cfg = config.setdefault('platforms', {}).setdefault('github', {})

    if args.github_repos:
        repos = [
            repo.strip()
            for repo in args.github_repos.split(',')
            if repo.strip()
        ]
        github_cfg['search_repos'] = repos

        if args.github_top_repos is None:
            top_cfg = github_cfg.setdefault('top_starred_repos', {})
            top_cfg['enabled'] = False

    if args.github_top_repos is not None:
        top_cfg = github_cfg.setdefault('top_starred_repos', {})
        top_cfg['enabled'] = True
        top_cfg['count'] = args.github_top_repos

    # --- LLM verifier overrides ---
    lv_cfg = config.setdefault('llm_verifier', {})

    if getattr(args, 'llm_enable', None):
        lv_cfg['enabled'] = True

    if getattr(args, 'llm_provider', None):
        lv_cfg['provider'] = args.llm_provider
        if args.llm_provider != 'disabled':
            lv_cfg['enabled'] = True

    if getattr(args, 'llm_model', None):
        lv_cfg['model'] = args.llm_model

    return config


def merge_records(all_records: List[List[Dict[str, Any]]]) -> pd.DataFrame:
    """Merge records from all platforms into a single DataFrame."""
    logger = logging.getLogger('orchestrator')

    flat_records = []
    for platform_records in all_records:
        flat_records.extend(platform_records)

    if not flat_records:
        logger.warning("No records collected!")
        return pd.DataFrame()

    df = pd.DataFrame(flat_records)
    logger.info(f"Merged {len(df)} total records from all platforms")
    return df


def generate_report(df: pd.DataFrame, dedup_result: Dict[str, Any], output_dir: str):
    """Generate collection statistics report."""
    logger = logging.getLogger('orchestrator')

    report = []
    report.append("=" * 70)
    report.append("ANALOGICAL REASONING DATA COLLECTION REPORT")
    report.append("=" * 70)
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("")

    # Collection stats
    report.append("COLLECTION STATISTICS")
    report.append("-" * 40)

    if not df.empty:
        # ---- per-platform breakdown with source-type sub-counts ----
        platform_counts = df['platform'].value_counts()
        for platform, count in platform_counts.items():
            report.append(f"  {platform:20s}: {count:5d} records")
            if 'source_type' in df.columns:
                sub = df[df['platform'] == platform]['source_type'].value_counts()
                for stype, scnt in sub.items():
                    report.append(f"    {'- ' + stype:20s}: {scnt:5d}")

        report.append(f"  {'TOTAL':20s}: {len(df):5d} records")
        report.append("")

        # ---- per-source analogy yield rate ----
        report.append("PER-SOURCE ANALOGY YIELD")
        report.append("-" * 40)
        report.append("  (ratio of records with analogy_present=True to total crawled)")
        if 'analogy_present' in df.columns:
            for platform, grp in df.groupby('platform'):
                total = len(grp)
                with_analogy = grp['analogy_present'].sum()
                rate = with_analogy / total if total else 0.0
                report.append(f"  {platform:20s}: {with_analogy:5d}/{total:5d} ({rate:.1%})")
        report.append("")

        # ---- average confidence per platform ----
        report.append("AVERAGE ANALOGY CONFIDENCE")
        report.append("-" * 40)
        if 'analogy_confidence' in df.columns:
            conf_by_platform = df.groupby('platform')['analogy_confidence'].mean()
            for platform, avg in conf_by_platform.items():
                report.append(f"  {platform:20s}: {avg:.3f}")
        report.append("")

        # ---- Analogy type distribution ----
        report.append("ANALOGY TYPE DISTRIBUTION")
        report.append("-" * 40)
        all_types = []
        for types_str in df['analogy_types'].dropna():
            all_types.extend(t.strip() for t in types_str.split(',') if t.strip())

        type_counts = pd.Series(all_types).value_counts()
        for analogy_type, count in type_counts.items():
            report.append(f"  {analogy_type:20s}: {count:5d} mentions")
        report.append("")

        # ---- SDLC phase distribution ----
        report.append("SDLC PHASE DISTRIBUTION")
        report.append("-" * 40)
        phase_col = 'sldc_phase' if 'sldc_phase' in df.columns else 'sdlc_phase'
        if phase_col in df.columns:
            phase_counts = df[phase_col].value_counts()
            for phase, count in phase_counts.items():
                report.append(f"  {phase:20s}: {count:5d} records")
        report.append("")

        # ---- LLM verifier stats ----
        if 'llm_verified' in df.columns:
            llm_run = df['llm_provider_model'].dropna().loc[lambda s: s != '']
            if not llm_run.empty:
                model_used = llm_run.iloc[0]
                llm_accepted = int(df['llm_verified'].sum())
                llm_total = len(df)
                report.append("LLM VERIFICATION RESULTS")
                report.append("-" * 40)
                report.append(f"  Model used           : {model_used}")
                report.append(f"  Records checked      : {llm_total}")
                report.append(f"  Confirmed analogies  : {llm_accepted}")
                report.append(f"  Acceptance rate      : {llm_accepted / llm_total:.1%}")
                report.append("")

        # ---- Deduplication stats ----
        if dedup_result:
            report.append("DEDUPLICATION RESULTS")
            report.append("-" * 40)
            report.append(f"  Original records:    {dedup_result['total_original']}")
            report.append(f"  Exact duplicates:    {dedup_result['exact_removed']}")
            report.append(f"  Near-duplicates:     {dedup_result['similar_removed']}")
            report.append(f"  Retained records:    {len(dedup_result['records'])}")
            report.append(f"  Retention rate:      {dedup_result['retention_rate']:.2%}")
            report.append("")

        # ---- Data quality warnings ----
        report.append("DATA QUALITY NOTES")
        report.append("-" * 40)
        report.append("  - Author deduplication across platforms is NOT possible")
        report.append("    without verified identity linking.")
        report.append("  - Discord data requires server owner permission.")
        report.append("  - All URLs should be manually verified before publication.")
        report.append("  - Survey data must be collected separately via institutional")
        report.append("    review board (IRB) approved instruments.")
        report.append("  - Lobsters/HN comments: thread context comes from parent title")
        report.append("    which is fetched live; check logs for any resolution failures.")
    else:
        report.append("  No records collected.")

    report.append("=" * 70)

    report_text = "\n".join(report)

    # Save report
    report_path = os.path.join(output_dir, "collection_report.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    logger.info(f"Report saved to {report_path}")
    print(report_text)

    return report_text


def main():
    parser = argparse.ArgumentParser(
        description="Collect analogical reasoning data from developer platforms"
    )
    parser.add_argument(
        '--config', 
        default=os.path.join(BASE_DIR, 'config.yaml'),
        help='Path to configuration file'
    )
    parser.add_argument(
        '--platforms',
        default='all',
        help=(
            'Comma-separated platform names or "all". '
            'Tier-1: stackoverflow,reddit,github,zenodo,huggingface. '
            'Tier-2: devto,hashnode,hackernews,lobsters,gitlab. '
            'Tier-3 (disabled by default): discord.'
        )
    )
    parser.add_argument(
        '--skip-dedup',
        action='store_true',
        help='Skip deduplication step'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Output filename for combined CSV'
    )
    parser.add_argument(
        '--github-repos',
        default=None,
        help=(
            'Comma-separated GitHub owner/repo names to search for this run, '
            'for example "microsoft/vscode" or "owner/a,owner/b". '
            'When provided without --github-top-repos, top-repo discovery is disabled.'
        )
    )
    parser.add_argument(
        '--github-top-repos',
        type=int,
        default=None,
        help=(
            'Enable GitHub top-starred repository discovery for this run and '
            'collect from the top N repositories. Can be combined with --github-repos.'
        )
    )
    parser.add_argument(
        '--llm-provider',
        default=None,
        help=(
            'Override llm_verifier.provider from config for this run. '
            'Choices: openai | anthropic | ollama | lmstudio | openai_compatible | disabled'
        )
    )
    parser.add_argument(
        '--llm-model',
        default=None,
        help='Override llm_verifier.model from config for this run (e.g. gpt-4o-mini).'
    )
    parser.add_argument(
        '--llm-enable',
        action='store_true',
        default=None,
        help='Enable the LLM second-pass verifier for this run (overrides config enabled: false).'
    )

    args = parser.parse_args()

    # Setup
    config = load_config(args.config)
    config = apply_runtime_overrides(config, args)
    logger = setup_logging(config['project'].get('log_dir', './logs'))

    logger.info("=" * 60)
    logger.info("ANALOGICAL REASONING DATA COLLECTION PIPELINE")
    logger.info("=" * 60)

    # Determine platforms
    # 'all' runs every platform whose config block has enabled: true.
    # Discord/Tier-3 sources are guarded at the config level (enabled: false).
    ALL_PLATFORMS = [
        'stackoverflow', 'reddit', 'github', 'zenodo', 'huggingface',
        'devto', 'hashnode', 'hackernews', 'lobsters', 'gitlab',
        'discord',  # skipped at runtime if config.enabled == false
    ]
    if args.platforms.lower() == 'all':
        platforms = ALL_PLATFORMS
    else:
        platforms = [p.strip().lower() for p in args.platforms.split(',')]

    logger.info(f"Platforms: {', '.join(platforms)}")

    # Collect data
    all_records = []
    for platform in platforms:
        if not config['platforms'].get(platform, {}).get('enabled', True):
            logger.info(f"Skipping {platform} (disabled in config)")
            continue

        records = collect_platform(platform, config)
        all_records.append(records)

    # Merge
    df = merge_records(all_records)

    if df.empty:
        logger.warning(
            "No records matched collection filters. Writing empty output and report."
        )
        output_dir = config['project']['output_dir']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = args.output or f"combined_analogies_{timestamp}.csv"
        output_path = os.path.join(output_dir, output_file)

        empty_columns = config.get('output_schema', [])
        pd.DataFrame(columns=empty_columns).to_csv(output_path, index=False, quoting=1)
        logger.info(f"Empty combined dataset saved to {output_path}")

        generate_report(df, None, output_dir)
        logger.info("Pipeline complete (no matching records found).")
        return 0

    # Deduplication
    dedup_result = None
    if not args.skip_dedup:
        dedup = Deduplicator(
            similarity_threshold=config['deduplication'].get('similarity_threshold', 0.85),
            min_content_length=config['deduplication'].get('min_content_length', 50)
        )
        dedup_result = dedup.deduplicate(df.to_dict('records'))
        df = pd.DataFrame(dedup_result['records'])

    # Save combined output
    output_dir = config['project']['output_dir']
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = args.output or f"combined_analogies_{timestamp}.csv"
    output_path = os.path.join(output_dir, output_file)

    df.to_csv(output_path, index=False, quoting=1)
    logger.info(f"Combined dataset saved to {output_path}")

    # Generate report
    generate_report(df, dedup_result, output_dir)

    logger.info("Pipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())