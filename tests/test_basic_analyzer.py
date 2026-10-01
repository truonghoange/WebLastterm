import unittest

from backend.analyzers.basic_analyzer import BasicAnalyzer
from backend.parsers.cv_parser import CVParser
from backend.parsers.jd_parser import JDParser
from tests.helpers import CV, document


class BasicAnalyzerTests(unittest.TestCase):
    def analyze(self, text=CV):
        doc = document(text)
        return BasicAnalyzer().analyze(doc, CVParser().parse(doc))

    def test_email_phone_sections_count(self):
        checks = self.analyze()
        self.assertTrue(checks.has_email)
        self.assertTrue(checks.has_phone)
        self.assertIn("education", checks.sections_detected)
        self.assertIn("projects", checks.sections_detected)
        self.assertEqual(checks.word_count, len(CV.split()))
        self.assertEqual(checks.bullet_count, 3)
        self.assertEqual(checks.missing_sections, [])

    def test_missing_sections_and_contact(self):
        checks = self.analyze("Student interested in data analysis.")
        self.assertFalse(checks.has_email)
        self.assertFalse(checks.has_phone)
        self.assertEqual(set(checks.missing_sections), {"education", "skills", "experience_or_projects"})

    def test_dates_not_phone(self):
        self.assertFalse(self.analyze("Education\nUniversity 2020-2024").has_phone)

    def test_student_projects_satisfy_experience_structure(self):
        checks = self.analyze("Education\nUniversity\nSkills: Python\nProjects\n• Built a Python dashboard.")
        self.assertNotIn("experience_or_projects", checks.missing_sections)

    def test_extraction_warning(self):
        doc = document()
        doc.extraction_quality = "low"
        checks = BasicAnalyzer().analyze(doc, CVParser().parse(doc))
        self.assertIn("OCR", checks.extraction_warning)

    def test_repeated_and_inline_sections(self):
        profile = CVParser().parse(document("Skills: Python3, PowerBI\nProjects\nBuilt Python\nProjects\nBuilt Power BI"))
        self.assertIn("Python", profile.skills)
        self.assertIn("Power BI", profile.skills)
        self.assertEqual(len(profile.projects), 2)

    def test_jd_headings_not_skills(self):
        jd = JDParser().parse("Job description\nAbout the role\nResponsibilities:\nRequirements:\nPython\nQualifications:\nPreferred:\nPower BI")
        self.assertEqual([r.requirement for r in jd.requirements], ["Python", "Power BI"])

    def test_mixed_required_preferred_and_no_duplicates(self):
        jd = JDParser().parse("Requirements:\nPython required and Power BI preferred\nPython required\nPreferred:\nSQL required")
        mapping = {r.requirement: r.preferred for r in jd.requirements}
        self.assertEqual(mapping, {"Python": False, "Power BI": True, "SQL": False})

    def test_experience_and_education_not_skills(self):
        jd = JDParser().parse("2 years Power BI experience\nBachelor degree in Computer Science")
        self.assertEqual([r.category for r in jd.requirements], ["experience", "education"])

    def test_inline_preferred_heading_applies_to_whole_list(self):
        jd = JDParser().parse("Preferred skills: Python, SQL\nRequired skills: Power BI")
        self.assertEqual({r.requirement: r.preferred for r in jd.requirements}, {"Python": True, "SQL": True, "Power BI": False})
