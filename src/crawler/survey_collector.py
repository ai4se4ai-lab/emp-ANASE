"""
Survey Data Management Module
Handles collection, anonymization, and export of survey responses.

IMPORTANT: Survey data collection requires:
1. Institutional Review Board (IRB) approval
2. Informed consent from all participants
3. Data protection compliance (GDPR, CCPA, etc.)
4. Secure storage of raw responses
"""

import hashlib
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import yaml


class SurveyCollector:
    """Manage survey responses for analogical reasoning study."""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self.responses = []
        self.output_dir = self.config['project']['output_dir']
        os.makedirs(self.output_dir, exist_ok=True)

    def add_response(self,
                     participant_id: str,
                     experience_years: int,
                     primary_role: str,
                     ai_agent_used: str,
                     team_size: str,
                     uses_analogies: bool,
                     analogy_types: List[str],
                     sldc_phases: List[str],
                     effectiveness_rating: int,  # 1-5 Likert
                     critical_thinking_rating: int,  # 1-5 Likert
                     confusion_experienced: bool,
                     breakdown_experienced: bool,
                     breakdown_description: str = "",
                     challenges: List[str] = None,
                     open_ended_analogy: str = "",
                     open_ended_effectiveness: str = "",
                     open_ended_improvements: str = "",
                     consent_given: bool = False,
                     collection_date: str = None) -> Dict[str, Any]:
        """
        Add a single survey response.

        Args:
            participant_id: Unique identifier (will be hashed)
            experience_years: Years of software development experience
            primary_role: Frontend/Backend, Full-stack, DevOps, Architect, etc.
            ai_agent_used: GitHub Copilot, Cursor, Claude Code, Custom, etc.
            team_size: Solo, 2-5, 6-15, 16+
            uses_analogies: Whether participant uses analogies with AI agents
            analogy_types: List of analogy types used (structural, functional, process, cross-domain)
            sldc_phases: SDLC phases where analogies are used
            effectiveness_rating: 1-5 Likert scale for understanding improvement
            critical_thinking_rating: 1-5 Likert scale for critical thinking improvement
            confusion_experienced: Whether analogies ever caused confusion
            breakdown_experienced: Whether participant experienced analogy breakdown
            breakdown_description: Description of breakdown scenario
            challenges: List of challenges faced
            open_ended_analogy: Example analogy used by participant
            open_ended_effectiveness: Open-ended effectiveness description
            open_ended_improvements: Suggestions for improvement
            consent_given: Whether informed consent was obtained
            collection_date: ISO 8601 date string
        """

        if not consent_given:
            raise ValueError("Informed consent must be obtained before recording response!")

        response = {
            'response_id': f"SURV-{len(self.responses) + 1:03d}",
            'participant_hash': hashlib.sha256(participant_id.encode()).hexdigest()[:16],
            'experience_years': experience_years,
            'primary_role': primary_role,
            'ai_agent_used': ai_agent_used,
            'team_size': team_size,
            'uses_analogies': uses_analogies,
            'analogy_types': ','.join(analogy_types),
            'sldc_phases': ','.join(sldc_phases),
            'effectiveness_rating': effectiveness_rating,
            'critical_thinking_rating': critical_thinking_rating,
            'confusion_experienced': confusion_experienced,
            'breakdown_experienced': breakdown_experienced,
            'breakdown_description': breakdown_description,
            'challenges': ','.join(challenges) if challenges else '',
            'open_ended_analogy': open_ended_analogy,
            'open_ended_effectiveness': open_ended_effectiveness,
            'open_ended_improvements': open_ended_improvements,
            'consent_given': consent_given,
            'collection_date': collection_date or datetime.now().isoformat(),
            'collector_version': self.config['project']['version']
        }

        self.responses.append(response)
        return response

    def load_from_csv(self, filepath: str):
        """Load existing survey responses from CSV."""
        df = pd.read_csv(filepath)
        self.responses = df.to_dict('records')

    def get_demographics(self) -> Dict[str, Any]:
        """Calculate demographic statistics."""
        if not self.responses:
            return {}

        df = pd.DataFrame(self.responses)

        return {
            'n': len(df),
            'experience_median': df['experience_years'].median(),
            'experience_mean': df['experience_years'].mean(),
            'experience_std': df['experience_years'].std(),
            'role_distribution': df['primary_role'].value_counts().to_dict(),
            'agent_distribution': df['ai_agent_used'].value_counts().to_dict(),
            'team_size_distribution': df['team_size'].value_counts().to_dict(),
            'effectiveness_mean': df['effectiveness_rating'].mean(),
            'effectiveness_std': df['effectiveness_rating'].std(),
            'critical_thinking_mean': df['critical_thinking_rating'].mean(),
            'critical_thinking_std': df['critical_thinking_rating'].std(),
            'confusion_rate': df['confusion_experienced'].mean(),
            'breakdown_rate': df['breakdown_experienced'].mean()
        }

    def get_analogy_type_distribution(self) -> Dict[str, int]:
        """Count analogy types across all responses."""
        type_counts = {}
        for response in self.responses:
            types = response.get('analogy_types', '').split(',')
            for t in types:
                t = t.strip()
                if t:
                    type_counts[t] = type_counts.get(t, 0) + 1
        return type_counts

    def get_sdlc_phase_distribution(self) -> Dict[str, int]:
        """Count SDLC phases across all responses."""
        phase_counts = {}
        for response in self.responses:
            phases = response.get('sldc_phases', '').split(',')
            for p in phases:
                p = p.strip()
                if p:
                    phase_counts[p] = phase_counts.get(p, 0) + 1
        return phase_counts

    def export(self, filename: str = "survey_data.csv") -> str:
        """Export survey responses to CSV."""
        if not self.responses:
            print("No survey responses to export!")
            return ""

        filepath = os.path.join(self.output_dir, filename)
        df = pd.DataFrame(self.responses)
        df.to_csv(filepath, index=False, quoting=1)
        print(f"Survey data exported to {filepath}")
        return filepath

    def generate_report(self) -> str:
        """Generate survey statistics report."""
        demo = self.get_demographics()
        analogy_types = self.get_analogy_type_distribution()
        phases = self.get_sdlc_phase_distribution()

        report = []
        report.append("=" * 60)
        report.append("SURVEY DATA REPORT")
        report.append("=" * 60)
        report.append(f"Total Responses: {demo.get('n', 0)}")
        report.append("")
        report.append("DEMOGRAPHICS")
        report.append("-" * 40)
        report.append(f"Experience (median): {demo.get('experience_median', 'N/A')} years")
        report.append(f"Experience (mean ± SD): {demo.get('experience_mean', 'N/A'):.1f} ± {demo.get('experience_std', 'N/A'):.1f}")
        report.append("")
        report.append("Role Distribution:")
        for role, count in demo.get('role_distribution', {}).items():
            report.append(f"  {role}: {count}")
        report.append("")
        report.append("AI Agent Distribution:")
        for agent, count in demo.get('agent_distribution', {}).items():
            report.append(f"  {agent}: {count}")
        report.append("")
        report.append("EFFECTIVENESS")
        report.append("-" * 40)
        report.append(f"Understanding (mean ± SD): {demo.get('effectiveness_mean', 'N/A'):.2f} ± {demo.get('effectiveness_std', 'N/A'):.2f}")
        report.append(f"Critical Thinking (mean ± SD): {demo.get('critical_thinking_mean', 'N/A'):.2f} ± {demo.get('critical_thinking_std', 'N/A'):.2f}")
        report.append(f"Confusion Rate: {demo.get('confusion_rate', 'N/A'):.1%}")
        report.append(f"Breakdown Rate: {demo.get('breakdown_rate', 'N/A'):.1%}")
        report.append("")
        report.append("ANALOGY TYPE DISTRIBUTION")
        report.append("-" * 40)
        for atype, count in analogy_types.items():
            report.append(f"  {atype}: {count}")
        report.append("")
        report.append("SDLC PHASE DISTRIBUTION")
        report.append("-" * 40)
        for phase, count in phases.items():
            report.append(f"  {phase}: {count}")
        report.append("=" * 60)

        report_text = "\n".join(report)
        print(report_text)
        return report_text


if __name__ == "__main__":
    # Example usage
    survey = SurveyCollector()

    # Example: Add a sample response (in real use, this comes from survey instrument)
    survey.add_response(
        participant_id="P001",
        experience_years=6,
        primary_role="Full-stack Developer",
        ai_agent_used="GitHub Copilot",
        team_size="2-5",
        uses_analogies=True,
        analogy_types=["functional", "process"],
        sldc_phases=["development", "debugging"],
        effectiveness_rating=4,
        critical_thinking_rating=4,
        confusion_experienced=True,
        breakdown_experienced=False,
        open_ended_analogy="I think of Copilot like a very enthusiastic junior developer who writes tests that look comprehensive but miss edge cases.",
        consent_given=True
    )

    survey.generate_report()
    survey.export()