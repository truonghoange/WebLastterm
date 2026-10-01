import logging
import re

from backend.models import BasicChecks, CVDocument, CandidateProfile
from cv_checker import _check_ats_structure
from processor import _extract_bullets

logger = logging.getLogger(__name__)


class BasicAnalyzer:
    def analyze(self, document: CVDocument, profile: CandidateProfile) -> BasicChecks:
        checks = _check_ats_structure(document.raw_text, {"detected_sections": profile.sections_detected})
        has_email = next(item["passed"] for item in checks if item["check"] == "Email")
        # Avoid considering year ranges (2020-2024) to be telephone numbers.
        candidates = re.findall(r"(?<![\w])\+?\d[\d ().-]{6,}\d(?![\w])", document.raw_text)
        has_phone = any(9 <= len(re.sub(r"\D", "", phone)) <= 15
                        and not re.fullmatch(r"(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}", phone.strip())
                        for phone in candidates)
        missing = [section for section in ("education", "skills") if section not in profile.sections_detected]
        if not {"experience", "projects"}.intersection(profile.sections_detected):
            missing.append("experience_or_projects")
        bullets = _extract_bullets("\n".join(profile.experience + profile.projects))
        # Profile extraction removes markers; inspect raw text for exact bullet counts.
        marked = sum(bool(re.match(r"^\s*[-•●○◆▪▸►*]\s+", line)) for line in document.raw_text.splitlines())
        warning = "Text extraction quality is low. Review extracted text; scanned PDFs may need OCR." if document.extraction_quality == "low" else None
        logger.info("Basic analysis completed")
        return BasicChecks(has_email=has_email, has_phone=has_phone,
                           word_count=len(document.raw_text.split()), sections_detected=profile.sections_detected,
                           missing_sections=missing, bullet_count=marked or len(bullets), extraction_warning=warning)
