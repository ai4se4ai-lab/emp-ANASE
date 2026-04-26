"""
Manual analogy validation harness.

Presents a random sample of records from a collected CSV, prints the analogy
quote + surrounding context, and asks the user to label each as y(es, genuine
analogy) or n(ot an analogy).  Writes a labeled CSV for precision/recall analysis.

Usage:
    python -m tools.validate_analogies --csv output/github_microsoft_vscode_analogies.csv
    python -m tools.validate_analogies --csv output/combined_analogies.csv --sample 50 --out labeled.csv

Optional arguments:
    --csv      Path to input CSV (required)
    --sample   Number of records to sample (default: 50)
    --out      Output path for labeled CSV (default: output/validated_<timestamp>.csv)
    --seed     Random seed for reproducible sampling (default: 42)
    --llm-col  Column name holding the LLM verdict to compare against (default: llm_verified)
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

try:
    import pandas as pd
except ImportError:
    print("pandas is required: pip install pandas")
    sys.exit(1)


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _truncate(text: str, n: int = 600) -> str:
    return text[:n] + ('…' if len(text) > n else '')


def _label_record(idx: int, total: int, row: pd.Series) -> Optional[bool]:
    """Interactively prompt the user to label one record. Returns True/False/None (skip)."""
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"Record {idx + 1}/{total}  |  ID: {row.get('record_id', '?')}")
    print(f"Platform : {row.get('platform', '?')}  |  URL: {row.get('url', '?')}")
    print(f"Title    : {_truncate(str(row.get('title', '')), 120)}")
    print("-" * 72)
    print("CONTEXT:")
    content = str(row.get('content', ''))
    print(_truncate(content, 600))
    print("-" * 72)
    print("DETECTED ANALOGY QUOTE:")
    print(f"  {_truncate(str(row.get('analogy_quote', '(none)')), 300)}")
    print("-" * 72)
    print(f"Heuristic confidence : {row.get('analogy_confidence', '?')}")
    print(f"Analogy types        : {row.get('analogy_types', '?')}")
    if str(row.get('llm_verified', '')) not in ('', 'nan', 'False', 'false'):
        print(f"LLM verdict          : YES  ({row.get('llm_mapping_summary', '')})")
    elif str(row.get('llm_verified', '')) in ('False', 'false'):
        print("LLM verdict          : NO")
    print(sep)

    while True:
        answer = input("Is this a genuine cross-domain analogy? [y / n / s(kip) / q(uit)] ").strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        if answer in ('s', 'skip', ''):
            return None
        if answer in ('q', 'quit', 'exit'):
            raise KeyboardInterrupt
        print("Please enter y, n, s, or q.")


# ------------------------------------------------------------------ #
# Precision comparison                                                #
# ------------------------------------------------------------------ #

def _compute_stats(df: pd.DataFrame, llm_col: str):
    labeled = df[df['human_label'].notna()]
    if labeled.empty:
        return

    total = len(labeled)
    tp = int((labeled['human_label'] == True).sum())
    fp = int((labeled['human_label'] == False).sum())
    precision = tp / total if total else 0.0

    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    print(f"  Records reviewed     : {total}")
    print(f"  Human TRUE (analogy) : {tp}")
    print(f"  Human FALSE (no)     : {fp}")
    print(f"  Human precision      : {precision:.1%}")

    if llm_col in labeled.columns:
        llm_yes = labeled[llm_col].astype(str).str.lower().isin(['true', '1', 'yes'])
        both_yes = int(((labeled['human_label'] == True) & llm_yes).sum())
        human_yes = tp
        if human_yes:
            recall = both_yes / human_yes
            print(f"  LLM recall (vs human): {recall:.1%} "
                  f"({both_yes}/{human_yes} human-yes confirmed by LLM)")

    print("=" * 50)


# ------------------------------------------------------------------ #
# Main                                                                #
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="Interactively label a sample of collected analogy records."
    )
    parser.add_argument('--csv', required=True, help='Path to collected analogies CSV')
    parser.add_argument('--sample', type=int, default=50, help='Number of records to sample')
    parser.add_argument('--out', default=None, help='Output path for labeled CSV')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for sampling')
    parser.add_argument('--llm-col', default='llm_verified',
                        help='Column holding LLM verdict (for comparison)')
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"ERROR: file not found: {args.csv}")
        sys.exit(1)

    df = pd.read_csv(args.csv)
    print(f"Loaded {len(df)} records from {args.csv}")

    sample_n = min(args.sample, len(df))
    sample = df.sample(n=sample_n, random_state=args.seed).reset_index(drop=True)

    sample['human_label'] = None  # will be True/False/NaN

    print(f"\nYou will be shown {sample_n} randomly selected records.")
    print("For each, enter:")
    print("  y  — genuine cross-domain analogy")
    print("  n  — NOT an analogy (exemplification, preference, same-domain, etc.)")
    print("  s  — skip (uncertain, label stays blank)")
    print("  q  — quit and save what you have so far")

    try:
        for i, (orig_idx, row) in enumerate(sample.iterrows()):
            verdict = _label_record(i, sample_n, row)
            sample.at[orig_idx, 'human_label'] = verdict
    except KeyboardInterrupt:
        print("\nSession interrupted. Saving labeled records…")

    # Default output path
    out_path = args.out
    if not out_path:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_dir = os.path.dirname(args.csv)
        out_path = os.path.join(out_dir, f"validated_{ts}.csv")

    sample.to_csv(out_path, index=False, encoding='utf-8')
    print(f"\nLabeled records saved to: {out_path}")

    _compute_stats(sample, args.llm_col)


if __name__ == '__main__':
    main()
