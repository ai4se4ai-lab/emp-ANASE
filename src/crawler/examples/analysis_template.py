"""
Analysis Template for Analogical Reasoning Data
Generates publication-ready statistics and visualizations.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats


def load_data(csv_path: str) -> pd.DataFrame:
    """Load and preprocess collected data."""
    df = pd.read_csv(csv_path)

    # Parse analogy types
    df['analogy_types_list'] = df['analogy_types'].str.split(',')

    # Parse SDLC phases
    df['sldc_phases_list'] = df['sldc_phase'].str.split(',')

    return df


def descriptive_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    """Generate descriptive statistics for the dataset."""
    stats_dict = {
        'total_records': len(df),
        'platform_distribution': df['platform'].value_counts().to_dict(),
        'analogy_type_distribution': {},
        'sldc_phase_distribution': {},
        'effectiveness_by_type': {},
        'engagement_stats': {
            'mean_upvotes': df['upvotes'].mean(),
            'median_upvotes': df['upvotes'].median(),
            'mean_replies': df['replies'].mean(),
            'median_replies': df['replies'].median()
        }
    }

    # Analogy type distribution
    all_types = []
    for types_list in df['analogy_types_list'].dropna():
        if isinstance(types_list, list):
            all_types.extend(types_list)

    stats_dict['analogy_type_distribution'] = pd.Series(all_types).value_counts().to_dict()

    # SDLC phase distribution
    stats_dict['sldc_phase_distribution'] = df['sldc_phase'].value_counts().to_dict()

    return stats_dict


def inferential_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate inferential statistics.

    Note: For Likert-scale data, use non-parametric tests:
    - Kruskal-Wallis H-test for >2 groups
    - Mann-Whitney U test for 2 groups
    - Spearman correlation for ordinal relationships
    """
    results = {}

    # Example: Compare analogy effectiveness across types
    # (Requires effectiveness_rating column from survey data)

    # Kruskal-Wallis test for analogy effectiveness across SDLC phases
    if 'effectiveness_rating' in df.columns and 'sldc_phase' in df.columns:
        groups = [group['effectiveness_rating'].values 
                  for name, group in df.groupby('sldc_phase') 
                  if len(group) > 5]

        if len(groups) >= 2:
            h_stat, p_value = stats.kruskal(*groups)
            results['kruskal_wallis'] = {
                'h_statistic': h_stat,
                'p_value': p_value,
                'significant': p_value < 0.05
            }

    # Spearman correlation between confidence and engagement
    if 'analogy_confidence' in df.columns and 'upvotes' in df.columns:
        rho, p_value = stats.spearmanr(df['analogy_confidence'], df['upvotes'])
        results['spearman_confidence_engagement'] = {
            'rho': rho,
            'p_value': p_value,
            'significant': p_value < 0.05
        }

    return results


def generate_visualizations(df: pd.DataFrame, output_dir: str = "output/figures"):
    """Generate publication-ready figures."""
    os.makedirs(output_dir, exist_ok=True)

    # Figure 1: Platform distribution
    plt.figure(figsize=(10, 6))
    df['platform'].value_counts().plot(kind='bar', color='steelblue')
    plt.title('Data Distribution by Platform')
    plt.xlabel('Platform')
    plt.ylabel('Number of Records')
    plt.tight_layout()
    plt.savefig(f"{output_dir}/platform_distribution.png", dpi=300)
    plt.close()

    # Figure 2: Analogy type distribution
    all_types = []
    for types_list in df['analogy_types_list'].dropna():
        if isinstance(types_list, list):
            all_types.extend(types_list)

    type_counts = pd.Series(all_types).value_counts()

    plt.figure(figsize=(10, 6))
    type_counts.plot(kind='barh', color='coral')
    plt.title('Distribution of Analogy Types')
    plt.xlabel('Frequency')
    plt.tight_layout()
    plt.savefig(f"{output_dir}/analogy_type_distribution.png", dpi=300)
    plt.close()

    # Figure 3: SDLC phase distribution
    plt.figure(figsize=(10, 6))
    df['sldc_phase'].value_counts().plot(kind='bar', color='seagreen')
    plt.title('SDLC Phase Distribution')
    plt.xlabel('SDLC Phase')
    plt.ylabel('Number of Records')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/sdlc_phase_distribution.png", dpi=300)
    plt.close()

    print(f"Figures saved to {output_dir}")


def export_summary_stats(stats_dict: Dict[str, Any], output_path: str = "output/summary_stats.json"):
    """Export statistics to JSON for replication."""
    import json

    with open(output_path, 'w') as f:
        json.dump(stats_dict, f, indent=2)

    print(f"Summary statistics exported to {output_path}")


if __name__ == "__main__":
    # Example workflow
    df = load_data("output/combined_analogies.csv")

    desc_stats = descriptive_statistics(df)
    inf_stats = inferential_statistics(df)

    generate_visualizations(df)
    export_summary_stats({**desc_stats, **inf_stats})