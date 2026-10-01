# ==============================================================================
# CONSTANTS.PY — CVision Shared Constants & Configuration
# ==============================================================================
# Tất cả dữ liệu tĩnh, keyword, synonym, rule đều nằm ở đây.
# Không hard-code ở các module khác.
# ==============================================================================

# ------------------------------------------------------------------------------
# SCORE WEIGHTS — Trọng số cho Overall Match Score
# ------------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "required": 0.50,
    "keywords": 0.25,
    "preferred": 0.15,
    "qualification": 0.10,
}

# ------------------------------------------------------------------------------
# MATCH SCORE LABELS — Nhãn dựa trên ngưỡng cố định
# ------------------------------------------------------------------------------
MATCH_SCORE_LABELS = [
    (0, 39, "Low Match", "🔴"),
    (40, 69, "Moderate Match", "🟡"),
    (70, 84, "Strong Match", "🟢"),
    (85, 100, "Very Strong Match", "🟢"),
]

CV_SCORE_LABELS = [
    (0, 59, "Needs Improvement", "🔴"),
    (60, 69, "Fair", "🟡"),
    (70, 79, "Solid", "🟢"),
    (80, 89, "Strong", "🟢"),
    (90, 100, "Exceptional", "🟢"),
]

# ------------------------------------------------------------------------------
# INDUSTRY LIST — Danh sách ngành cho dropdown
# ------------------------------------------------------------------------------
INDUSTRIES = [
    "Finance",
    "Banking",
    "Audit",
    "Marketing",
    "Data Analyst",
    "Consulting",
    "Human Resources",
    "Other",
]

# ------------------------------------------------------------------------------
# INDUSTRY KEYWORDS — Từ khóa theo ngành
# Chỉ keyword liên quan JD mới được dùng để chấm điểm.
# Library này hỗ trợ extraction, không phải tất cả đều dùng để score.
# ------------------------------------------------------------------------------
INDUSTRY_KEYWORDS = {
    "finance": [
        "excel", "financial analysis", "financial modeling", "valuation",
        "forecasting", "budgeting", "powerpoint", "bloomberg", "accounting",
        "financial statements", "cash flow", "revenue", "profit and loss",
        "balance sheet", "investment", "portfolio", "risk management",
        "corporate finance", "equity", "debt", "capital markets",
        "financial reporting", "audit", "tax", "compliance",
    ],
    "banking": [
        "credit analysis", "risk management", "loan", "deposit",
        "treasury", "compliance", "aml", "kyc", "basel",
        "interest rate", "foreign exchange", "trade finance",
        "retail banking", "corporate banking", "investment banking",
        "financial statements", "excel", "bloomberg", "credit scoring",
        "portfolio management", "asset management",
    ],
    "audit": [
        "audit", "internal audit", "external audit", "compliance",
        "risk assessment", "sox", "gaap", "ifrs", "financial statements",
        "internal controls", "audit planning", "audit report",
        "substantive testing", "analytical procedures", "sampling",
        "fraud detection", "excel", "data analytics", "cpa",
    ],
    "marketing": [
        "marketing", "digital marketing", "social media", "seo", "sem",
        "content marketing", "brand management", "market research",
        "google analytics", "facebook ads", "google ads", "email marketing",
        "copywriting", "campaign management", "crm", "hubspot",
        "marketing strategy", "lead generation", "conversion rate",
        "a/b testing", "kpi", "roi",
    ],
    "data analyst": [
        "sql", "python", "excel", "power bi", "tableau",
        "statistics", "data visualization", "data cleaning",
        "dashboard", "machine learning", "r", "pandas", "numpy",
        "data modeling", "etl", "database", "reporting",
        "statistical analysis", "regression", "hypothesis testing",
        "data mining", "big data", "spark", "hadoop",
    ],
    "consulting": [
        "consulting", "strategy", "problem solving", "presentation",
        "powerpoint", "excel", "stakeholder management", "project management",
        "business analysis", "market sizing", "case study",
        "client management", "research", "analytical thinking",
        "communication", "teamwork", "leadership",
    ],
    "human resources": [
        "recruitment", "talent acquisition", "onboarding", "training",
        "employee relations", "performance management", "compensation",
        "benefits", "hris", "labor law", "organizational development",
        "succession planning", "employer branding", "hr analytics",
        "payroll", "workforce planning", "diversity",
    ],
    "other": [],
}

# ------------------------------------------------------------------------------
# SKILL SYNONYMS — Chuẩn hóa tên skill
# key: biến thể → value: tên chuẩn
# ------------------------------------------------------------------------------
SKILL_SYNONYMS = {
    # Excel
    "microsoft excel": "excel",
    "ms excel": "excel",
    "ms. excel": "excel",
    "advanced excel": "excel",
    # PowerPoint
    "microsoft powerpoint": "powerpoint",
    "ms powerpoint": "powerpoint",
    "ms. powerpoint": "powerpoint",
    "ppt": "powerpoint",
    # Power BI
    "powerbi": "power bi",
    "microsoft power bi": "power bi",
    "ms power bi": "power bi",
    # Word
    "microsoft word": "word",
    "ms word": "word",
    "ms. word": "word",
    # Python
    "python 3": "python",
    "python3": "python",
    # Financial modeling
    "financial modelling": "financial modeling",
    "fin modeling": "financial modeling",
    "fin modelling": "financial modeling",
    # Financial analysis
    "financial analytics": "financial analysis",
    # Communication
    "communication skills": "communication",
    "english communication": "communication",
    "verbal communication": "communication",
    "written communication": "communication",
    # Teamwork
    "team work": "teamwork",
    "team player": "teamwork",
    "team-work": "teamwork",
    # Leadership
    "leadership skills": "leadership",
    "team leadership": "leadership",
    # SQL
    "mysql": "sql",
    "postgresql": "sql",
    "ms sql": "sql",
    "sql server": "sql",
    # Data visualization
    "data viz": "data visualization",
    "data visualisation": "data visualization",
    # Project management
    "project mgmt": "project management",
    # CPA
    "certified public accountant": "cpa",
    # CFA
    "chartered financial analyst": "cfa",
    "cfa candidate": "cfa",
    "cfa level 1": "cfa",
    "cfa level 2": "cfa",
    "cfa level 3": "cfa",
}

# ------------------------------------------------------------------------------
# SECTION NAMES — Pattern để detect section trong CV
# key: tên chuẩn → value: list các heading có thể gặp
# ------------------------------------------------------------------------------
SECTION_NAMES = {
    "education": [
        "education", "academic background", "academic qualification",
        "qualifications", "educational background",
    ],
    "experience": [
        "experience", "work experience", "professional experience",
        "employment", "internship experience", "internship",
        "work history", "employment history", "relevant experience",
    ],
    "skills": [
        "skills", "technical skills", "core skills", "key skills",
        "competencies", "core competencies", "professional skills",
        "it skills", "computer skills",
    ],
    "projects": [
        "projects", "academic projects", "personal projects",
        "key projects", "relevant projects", "project experience",
    ],
    "certifications": [
        "certifications", "certificates", "professional certifications",
        "licenses", "licenses and certifications",
        "certifications and licenses",
    ],
    "activities": [
        "activities", "extracurricular activities", "leadership",
        "volunteer", "volunteering", "community service",
        "extracurricular", "organizations",
    ],
}

# ------------------------------------------------------------------------------
# REQUIRED SIGNAL WORDS — Từ chỉ yêu cầu bắt buộc trong JD
# ------------------------------------------------------------------------------
REQUIRED_SIGNAL_WORDS = [
    "required", "must", "requirement", "requirements",
    "should have", "minimum", "essential", "mandatory",
    "necessary", "need", "needs", "expected",
]

# ------------------------------------------------------------------------------
# PREFERRED SIGNAL WORDS — Từ chỉ yêu cầu ưu tiên/bonus
# ------------------------------------------------------------------------------
PREFERRED_SIGNAL_WORDS = [
    "preferred", "plus", "advantage", "nice to have",
    "bonus", "ideally", "desired", "desirable",
    "a plus", "is a plus", "an advantage", "would be a plus",
    "good to have",
]

# ------------------------------------------------------------------------------
# WEAK VERBS — Các opening phrase mô tả nhiệm vụ (task-based)
# ------------------------------------------------------------------------------
WEAK_VERBS = [
    "responsible for",
    "helped",
    "assisted",
    "worked on",
    "supported",
    "participated in",
    "involved in",
    "tasked with",
    "in charge of",
    "duties included",
    "handled",
]

# ------------------------------------------------------------------------------
# IMPACT VERBS — Các action verb thể hiện đóng góp/kết quả
# ------------------------------------------------------------------------------
IMPACT_VERBS = [
    "increased", "decreased", "reduced", "improved",
    "generated", "saved", "achieved", "grew",
    "optimized", "streamlined", "identified",
    "developed", "implemented", "created", "designed",
    "launched", "led", "managed", "delivered",
    "exceeded", "accelerated", "expanded", "transformed",
    "automated", "consolidated", "established",
    "negotiated", "resolved", "spearheaded",
    "analyzed", "built", "coordinated",
]

# ------------------------------------------------------------------------------
# SOFT SKILLS LIST — Danh sách soft skills phổ biến
# ------------------------------------------------------------------------------
SOFT_SKILLS = [
    "communication", "teamwork", "leadership", "problem solving",
    "critical thinking", "analytical thinking", "time management",
    "adaptability", "creativity", "attention to detail",
    "interpersonal skills", "presentation", "negotiation",
    "conflict resolution", "decision making", "multitasking",
    "organizational skills", "work ethic", "collaboration",
    "initiative", "flexibility", "self-motivated",
]

# ------------------------------------------------------------------------------
# QUALIFICATION KEYWORDS — Từ khóa liên quan trình độ học vấn
# ------------------------------------------------------------------------------
QUALIFICATION_LEVELS = {
    "bachelor": ["bachelor", "ba", "bs", "bsc", "b.a.", "b.s.", "bba", "undergraduate"],
    "master": ["master", "ma", "ms", "msc", "m.a.", "m.s.", "mba", "graduate"],
    "phd": ["phd", "ph.d.", "doctorate", "doctoral"],
    "diploma": ["diploma", "associate", "certificate"],
}
