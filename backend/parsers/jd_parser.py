"""Conservative clause extraction; headings and duplicate keywords are excluded."""
import re

from backend.models import JDRequirement, JobDescription
from backend.normalization import extract_known_skills, normalize_skill
from constants import SOFT_SKILLS
from processor import _is_preferred_heading, _is_required_heading

IGNORED_HEADINGS = {"responsibilities", "key responsibilities", "about the role", "job description",
                    "about us", "benefits", "what we offer", "duties", "position", "jd"}
EDUCATION_PATTERN = r"\b(bachelor|master|ph\.?d|doctorate|degree|diploma|undergraduate|bsc|msc|mba)\b"


class JDParser:
    def parse(self, text: str) -> JobDescription:
        requirements = []
        title = None
        preferred_zone = False
        for original in text.splitlines():
            line = re.sub(r"^\s*(?:[-•●*]\s*|\d+[.)]\s+)?", "", original).strip()
            if not line:
                continue
            heading, separator, body = line.partition(":")
            if separator and (_is_required_heading(heading.lower()) or _is_preferred_heading(heading.lower())):
                preferred_zone = _is_preferred_heading(heading.lower())
                if not body.strip():
                    continue
                line = body.strip()
            lower = line.lower().rstrip(":")
            if _is_required_heading(lower):
                preferred_zone = False
                continue
            if _is_preferred_heading(lower):
                preferred_zone = True
                continue
            if lower in IGNORED_HEADINGS:
                continue
            # A short role/title line is kept in the role component, never as a skill.
            if title is None and len(line.split()) <= 8 and re.search(r"\b(intern|analyst|engineer|developer|manager|designer|consultant|specialist|officer)\b", lower) and not re.search(r"\b(must|required|preferred|experience|years?)\b", lower):
                title = line
                requirements.append(JDRequirement(requirement=line, category="role"))
                continue
            # Split mixed clauses before applying preferred markers, preserving local context.
            clauses = re.split(r";|[.!?]\s+|\bbut\b|\bwhile\b", line)
            for clause in clauses:
                clause = clause.strip(" ,.")
                if not clause:
                    continue
                # 'Python required and Power BI preferred' needs separate clauses.
                fragments = re.split(r",\s*(?=[A-Z])|\band\b(?=[^,;]*\b(?:preferred|optional|a plus|bonus)\b)", clause, flags=re.I)
                for fragment in fragments:
                    fragment = fragment.strip(" ,.")
                    if not fragment:
                        continue
                    is_preferred = bool(re.search(r"\b(preferred|optional|bonus|desired|desirable|advantage|plus)\b|nice to have", fragment, re.I))
                    is_required = bool(re.search(r"\b(must|required|essential|mandatory|minimum)\b", fragment, re.I))
                    preferred = is_preferred or (preferred_zone and not is_required)
                    skills = extract_known_skills(fragment)
                    if re.search(EDUCATION_PATTERN, fragment, re.I):
                        category = "education"
                    elif re.search(r"\b\d+\+?\s*(?:years?|yrs?)\b|\b(?:professional|work) experience\b", fragment, re.I):
                        category = "experience"
                    elif re.search(r"\bprojects?\b", fragment, re.I):
                        category = "project"
                    else:
                        category = None
                    if category:
                        requirements.append(JDRequirement(requirement=fragment, category=category, preferred=preferred,
                                                          skill_name=skills[0] if len(skills) == 1 else None))
                    elif skills:
                        for skill in skills:
                            requirements.append(JDRequirement(requirement=skill, skill_name=skill,
                                category="other" if skill.lower() in SOFT_SKILLS else "hard_skill", preferred=preferred))
                    else:
                        # Unknown prose stays an explicit requirement for AI to evaluate.
                        requirements.append(JDRequirement(requirement=fragment, category="other", preferred=preferred))
        unique = {}
        for requirement in requirements:
            key = normalize_skill(requirement.requirement).casefold()
            if key not in unique or (unique[key].preferred and not requirement.preferred):
                unique[key] = requirement
        return JobDescription(raw_text=text.strip(), job_title=title, requirements=list(unique.values()))
