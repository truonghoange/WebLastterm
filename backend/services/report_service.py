"""Portable Markdown review without provider/debug metadata."""
from backend.review_models import AnalyzerReview


def _text(value):
    return str(value).replace("\r", "").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")


def generate_report(review: AnalyzerReview) -> str:
    result = review.analysis
    lines = ["# CVision Review", "", f"Target: {_text(review.target_role or 'CV Review')}",
             f"Industry: {_text(review.industry)}", f"Analysis: {'Full analysis' if result.ai_available else 'Basic analysis'}",
             "", _text(review.summary), "", f"## CV {'Quality ' if result.mode == 'job_match' else ''}Score: {review.cv_quality.overall_score}/100", "",
             "### CV score breakdown", ""]
    for name, score in review.cv_quality.scores.model_dump(exclude_none=True).items():
        lines.append(f"- {name.replace('_', ' ').title()}: {score}/100")
    lines.extend(["", "## Your strengths", ""])
    for item in review.strengths:
        lines.append(f"- {_text(item.title)}" + (f": {_text(item.explanation)}" if item.explanation else ""))
        lines.extend(f"  - Evidence: {_text(quote)}" for quote in item.evidence)
    if not review.strengths:
        lines.append("No specific strengths were identified in this review.")
    lines.extend(["", "## Areas to improve", ""])
    for item in review.improvement_areas:
        lines.extend([f"- {_text(item.issue)}", f"  - Why it matters: {_text(item.why_it_matters)}",
                      f"  - Action: {_text(item.recommended_action)}"])
    lines.extend(["", "## Skills evidence", ""])
    for item in review.skill_evidence:
        lines.append(f"- {_text(item.skill)}: {item.strength.replace('_', ' ')} — {_text(item.explanation)}")
        lines.extend(f"  - {_text(quote)}" for quote in (item.evidence or item.mention_evidence)[:4])
    lines.extend(["", "## Fix these first", ""])
    for number, item in enumerate(review.top_recommendations, 1):
        lines.append(f"{number}. {_text(item.title)}: {_text(item.action)}")
    lines.extend(["", "## Bullet Review", ""])
    for item in review.bullet_reviews:
        if item.issues:
            lines.extend([f"- Original: {_text(item.original)}", f"  - Issue: {_text('; '.join(item.issues))}",
                          f"  - How to improve: {_text(' '.join(item.how_to_improve))}"])
    if result.mode == "job_match":
        lines.extend(["", f"## Job Match Score: {result.overall_score}/100", "", "### Why this match score?", ""])
        names = {"hard_skills": "Hard skills", "experience": "Experience relevance", "projects": "Projects",
                 "education": "Education alignment", "role": "Role relevance", "other": "Soft/other requirements"}
        for name, value in result.analysis_metadata.scoring_components.items() if result.analysis_metadata else []:
            lines.append(f"- {names.get(name, name)}: {value}/100")
        for state, label in (("matched", "Matched"), ("partial", "Partial"), ("missing", "Missing")):
            lines.extend(["", f"### {label} requirements", ""])
            for match in getattr(review.requirement_groups, state):
                lines.append(f"- {_text(match.requirement)}")
                lines.extend(f"  - Evidence: {_text(quote)}" for quote in match.evidence)
                if not match.evidence:
                    lines.append("  - No supporting CV evidence found.")
                if match.explanation:
                    lines.append(f"  - {_text(match.explanation)}")
        lines.extend(["", f"Matched skills: {', '.join(result.matched_skills) or 'None'}",
                      f"Partially matched skills: {', '.join(result.partially_matched_skills) or 'None'}",
                      f"Missing skills: {', '.join(result.missing_skills) or 'None'}"])
    if review.display_warnings:
        lines.extend(["", "## Review notes", ""] + [f"- {_text(text)}" for text in review.display_warnings])
    lines.extend(["", "Only add skills, experience or outcomes that reflect your actual background.",
                  "Scores are review aids, not hiring probabilities or official ATS scores.", ""])
    return "\n".join(lines)
