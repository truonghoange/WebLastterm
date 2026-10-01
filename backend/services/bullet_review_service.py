"""Local bullet review and batched edit suggestions using only supplied CV facts."""
import re

from backend.exceptions import InvalidCVError
from backend.models import CVDocument
from backend.normalization import normalized_text, valid_evidence
from backend.parsers.cv_parser import extract_sections
from backend.review_models import BulletReview, BulletRewrite
from cv_checker import _analyze_bullets

MARKER = re.compile(r"^\s*(?:[-•●○◆▪▸►*]\s+|\d+[.)]\s+)(.+)")
ACTION = re.compile(r"\b(built|created|developed|implemented|designed|trained|evaluated|validated|deployed|"
                    r"processed|analyzed|analysed|automated|integrated|forecast|tested|optimized|improved|"
                    r"cleaned|used|using|engineered|compared|led|delivered)\b", re.I)
OUTCOME = re.compile(r"\b(result|outcome|improved|reduced|increased|achieved|delivered|enabled|"
                     r"rmsle|rmse|mae|accuracy|latency|validated|validation|evaluated|evaluation)\b", re.I)


def section_bullets(document: CVDocument) -> list[tuple[str, str]]:
    result = []
    for section, text in extract_sections(document.raw_text).items():
        if section not in {"experience", "projects"}:
            continue
        current = []
        for line in text.splitlines():
            match = MARKER.match(line)
            if match:
                if current:
                    result.append((section, " ".join(current)))
                current = [match.group(1).strip()]
            elif current:
                text = line.strip()
                is_title = bool(text and not line[:1].isspace() and len(text.split()) <= 8
                                and text[0].isupper() and not ACTION.search(text)
                                and not text.endswith((".", "!", "?")))
                if not text or is_title:
                    result.append((section, " ".join(current)))
                    current = []
                else:
                    # Wrapped implementation text belongs to the marked bullet.
                    current.append(text)
        if current:
            result.append((section, " ".join(current)))
    return result


def review_bullets(document: CVDocument) -> list[BulletReview]:
    reviews = []
    for number, (section, original) in enumerate(section_bullets(document)):
        signals = _analyze_bullets([original])[0]
        issues, actions = [], []
        if signals["is_long"]:
            issues.append("This bullet is long and may be difficult to scan.")
            actions.append("Split it into shorter points, keeping your contribution and result together.")
        if signals["has_weak_verb"]:
            issues.append("Your specific contribution is unclear.")
            actions.append("Describe the action you personally completed; choose a verb that accurately reflects your role.")
        if not ACTION.search(original):
            issues.append("The action or implementation is not clearly described.")
            actions.append("Clarify what you did and how, using only details you can substantiate.")
        if not OUTCOME.search(original):
            issues.append("Implementation is described, but the output or outcome is unclear.")
            actions.append("Consider adding the dataset size or performance result if you measured it; a truthful qualitative outcome also helps.")
        reviews.append(BulletReview(id=f"bullet-{number}", section=section, original=original,
                                   issues=list(dict.fromkeys(issues)), how_to_improve=list(dict.fromkeys(actions))))
    return reviews


def rewrite_bullets(bullets: list[str], context: CVDocument) -> list[BulletRewrite]:
    """One local batch, zero LLM calls. Preserve source wording; never invent facts."""
    if len(bullets) > 20:
        raise InvalidCVError("Select at most 20 bullets for one set of suggestions.")
    reviews = {normalized_text(item.original): item for item in review_bullets(context)}
    result = []
    for original in dict.fromkeys(bullets):
        item = reviews.get(normalized_text(original))
        if item is None or not valid_evidence([original], context.raw_text):
            raise InvalidCVError("Select an existing project or experience bullet from this CV.")
        additions, required = [], []
        if any("contribution" in issue or "action" in issue for issue in item.issues):
            additions.append("[your specific contribution]")
            required.append("your specific contribution")
        if any("outcome" in issue for issue in item.issues):
            additions.append("[verified output or outcome, if known]")
            required.append("verified output or outcome")
        rewrite = original
        if additions:
            rewrite = original.rstrip(" .") + ". " + "; ".join(additions) + "."
        elif len(original.split()) > 35:
            rewrite = original.replace("; ", ". ")
        result.append(BulletRewrite(original=original, rewrite=rewrite,
            notes="Your original facts are preserved. Replace bracketed text only with details you can verify; omit it if unknown.",
            requires_user_input=required))
    return result
