from backend.models import AISemanticAnalysis, CVDocument
from backend.parsers.jd_parser import JDParser
from backend.providers.base_llm import LLMProvider

CV = """Student Name
student@example.test | +84 912 345 678
Summary
Computer Science student with data analytics projects.
Education
Bachelor degree in Computer Science
Experience
Data Intern
• Built SQL data cleaning pipeline.
Projects
• Built data analysis project using Python.
• Created Power BI dashboard for university project.
Skills
Python3, SQL, Pandas, PowerBI, PostgreSQL
"""
JD = """Data Analyst
Requirements:
Python required; SQL required; Power BI preferred.
2 years Power BI experience required.
Bachelor degree in Computer Science required.
Communication required.
"""
PYTHON_QUOTE = "Built data analysis project using Python."
SQL_QUOTE = "Built SQL data cleaning pipeline."
POWERBI_QUOTE = "Created Power BI dashboard for university project."
EDUCATION_QUOTE = "Bachelor degree in Computer Science"


def document(text=CV):
    return CVDocument(raw_text=text, source_type="text", extraction_quality="good")


def semantic_payload(jd_text=JD):
    def judgment(quote, quality="strong"):
        return {"quality": quality, "evidence": [quote] if quote else []}
    requirements = []
    for requirement in JDParser().parse(jd_text).requirements if jd_text else []:
        if requirement.category == "education":
            status, quotes = "matched", [EDUCATION_QUOTE]
        elif requirement.category == "experience":
            status, quotes = "partial", [POWERBI_QUOTE]
        elif requirement.requirement == "Python":
            status, quotes = "matched", [PYTHON_QUOTE]
        elif requirement.requirement == "SQL":
            status, quotes = "matched", [SQL_QUOTE]
        elif requirement.requirement == "Power BI":
            status, quotes = "matched", [POWERBI_QUOTE]
        else:
            status, quotes = "missing", []
        requirements.append({"requirement": requirement.requirement, "status": status, "evidence": quotes})
    return {
        "candidate_summary": "Computer Science student with data analytics project experience.",
        "detected_skills": ["Python", "SQL", "Pandas", "PowerBI"],
        "strengths": ["Relevant technical projects", "Clear programming foundation"],
        "weaknesses": ["Professional duration is not demonstrated"],
        "content_quality": judgment(PYTHON_QUOTE),
        "experience_quality": judgment(SQL_QUOTE, "adequate"),
        "project_quality": judgment(PYTHON_QUOTE),
        "education_quality": judgment(EDUCATION_QUOTE),
        "skill_quality": judgment(PYTHON_QUOTE),
        "experience_relevance": judgment(POWERBI_QUOTE, "adequate") if jd_text else None,
        "education_relevance": judgment(EDUCATION_QUOTE) if jd_text else None,
        "requirements": requirements,
        "recommendations": [],
    }


class MockProvider(LLMProvider):
    model_name = "mock-model"

    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else semantic_payload()
        self.error = error
        self.calls = []

    def analyze(self, prompt, schema):
        self.calls.append((prompt, schema))
        if self.error:
            raise self.error
        return schema.model_validate(self.payload)
