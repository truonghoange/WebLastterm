import re

from backend.models import CVDocument, CandidateProfile
from backend.normalization import extract_known_skills, normalize_skills
from processor import _match_section_heading, _normalize_text, _parse_skill_list, _extract_list_items


def extract_sections(text: str) -> dict[str, str]:
    """Reuse legacy heading rules, preserving repeated sections and inline headings."""
    parts: dict[str, list[str]] = {}
    current = None
    for line in _normalize_text(text).splitlines():
        heading, separator, rest = line.partition(":")
        detected = _match_section_heading(heading if separator else line)
        if heading.strip().lower() in {"summary", "profile", "professional summary", "objective"}:
            detected = "summary"
        if detected:
            current = detected
            parts.setdefault(current, [])
            if separator and rest.strip():
                parts[current].append(rest.strip())
        elif current:
            parts[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in parts.items()}


class CVParser:
    def parse(self, document: CVDocument, industry: str | None = None) -> CandidateProfile:
        sections = extract_sections(document.raw_text)
        # Known vocabulary is evidence extraction only; it never implies proficiency.
        body = "\n".join(line for line in document.raw_text.splitlines()
                         if not _match_section_heading(line)
                         and line.strip().lower().rstrip(":") not in
                         {"responsibilities", "requirements", "qualifications", "about the role", "job description"})
        skills = extract_known_skills(body)
        for value in _parse_skill_list(sections.get("skills", "")):
            # Do not turn prose/category headings into arbitrary skills.
            if len(value.split()) <= 5 and not re.search(r"\b(requirements|responsibilities|qualifications|job description)\b", value, re.I):
                skills.extend(extract_known_skills(value) or [value])
        return CandidateProfile(summary=sections.get("summary") or None,
                                skills=sorted(normalize_skills(skills)),
                                sections_detected=list(sections),
                                **{name: _extract_list_items(sections.get(name, ""))
                                   for name in ("education", "experience", "projects", "certifications")})
