"""
merge_discord.py
----------------
Merges a manually collected discord_posts.csv into the combined_dataset.csv
produced by collect_data.py.

Usage:
    python merge_discord.py \
        --discord  output/discord_posts.csv \
        --combined output/combined_dataset.csv \
        --output   output/full_dataset.csv
"""

import argparse
import pandas as pd
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ANALOGY_KEYWORDS = [
    "analogy", "metaphor", "like a", "similar to",
    "as if", "resembles", "just like", "think of it as",
]
AGENT_KEYWORDS = [
    "ai agent", "copilot", "cursor", "claude code",
    "github copilot", "agentic", "llm agent", "ai coding",
]


def contains_analogy_keyword(text: str) -> bool:
    return any(kw in text.lower() for kw in ANALOGY_KEYWORDS)


def contains_agent_keyword(text: str) -> bool:
    return any(kw in text.lower() for kw in AGENT_KEYWORDS)


def merge(discord_path: str, combined_path: str, output_path: str) -> None:
    discord_file  = Path(discord_path)
    combined_file = Path(combined_path)

    if not discord_file.exists():
        log.error("Discord file not found: %s", discord_path)
        return

    discord = pd.read_csv(discord_file, encoding="utf-8-sig")
    log.info("Discord posts loaded: %d rows", len(discord))

    # Normalise Discord columns to match combined schema
    discord["platform"]           = "discord"
    discord["post_id"]            = discord.get("message_id", discord.index.astype(str))
    discord["text_for_analysis"]  = (
        discord.get("message_content", "").fillna("")
    )
    discord["passes_dual_filter"] = (
        discord["text_for_analysis"].apply(contains_analogy_keyword) &
        discord["text_for_analysis"].apply(contains_agent_keyword)
    )

    if combined_file.exists():
        combined = pd.read_csv(combined_file, encoding="utf-8-sig")
        merged   = pd.concat([combined, discord], ignore_index=True, sort=False)
    else:
        log.warning("combined_dataset.csv not found — saving Discord data only")
        merged = discord

    merged = merged.drop_duplicates(subset=["platform", "post_id"])
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")

    log.info("Full dataset saved: %d rows → %s", len(merged), output_path)
    log.info("Platform breakdown:\n%s",
             merged["platform"].value_counts().to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discord",  default="output/discord_posts.csv")
    parser.add_argument("--combined", default="output/combined_dataset.csv")
    parser.add_argument("--output",   default="output/full_dataset.csv")
    args = parser.parse_args()
    merge(args.discord, args.combined, args.output)


if __name__ == "__main__":
    main()
