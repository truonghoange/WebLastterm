# CVision — CV analysis and job matching

CVision has a UI-independent Python backend and a small Streamlit frontend. Analyze a
CV on its own or against an optional Job Description. Deterministic document checks
always run; Gemini supplies validated semantic judgments when configured and available.
The backend owns scores and the final result contract.

The Analyzer now provides CV Review without a JD and CV ↔ Job Match with a usable JD.
Job mode shows separate CV Quality and Job Match scores, expandable skill evidence,
matched/partial/missing requirements, strengths, improvement areas, bullet review,
three priorities, guided batch rewrite suggestions and a Markdown report. Edit inputs,
Re-analyze and Analyze another CV manage the review without a browser refresh.
See [Analyzer product features and the additive review contract](docs/analyzer-product.md).

## Career Workspace

- **My CVs**: save an Analyzer review, rename/open saved CVs, re-analyze explicitly,
  compare with saved jobs, and retain analysis history.
- **Jobs**: save and edit job descriptions, compare saved CVs, and view prior matches.
- **Applications**: track each job/CV pair through Saved, Applied, Interview, Offer,
  Rejected or Withdrawn, with dates and notes. Duplicate pairs are prevented.
- **Insights**: stored-data averages, missing and partial skills, requested skills,
  recurring improvement areas and application counts. Workspace browsing makes no AI calls.

Storage is local SQLite, initialized automatically without deleting existing records.
The default is `data/cvision.db`; its parent directory is created as needed. Configure
the path in your process environment or project `.env`:

```dotenv
CVISION_DB_PATH=data/cvision.db
```

Relative configured paths are resolved from the project directory. The database contains
extracted CV text, job descriptions, notes and normalized reviews. Treat it as private
application data: it is stored in plain text locally, is ignored by Git, and is never
included in logs. There is no authentication or cloud sync; all users of one app instance
share its workspace. Preserve/back up the database file when moving installations.

Saving a CV updates its existing identity when already saved. Explicit re-analysis and
saved CV/job comparison append snapshots. Insight averages use the latest snapshot per CV
and latest comparison per CV/job pair. Skill counts count distinct jobs. Deletion requires
confirmation; CVs/jobs used in applications cannot be deleted until those applications are
removed. Otherwise, only related analyses are deleted. See
[workspace architecture and data policy](docs/career-workspace.md).

## Interface and theme

The interface uses a light workspace with white cards, readable slate text and an indigo
accent. The navy sidebar highlights the active page. Dashboard summaries, the CV/JD input
workflow, separate result scores, evidence panels and workspace pages share the same design
components. Columns stack on narrow screens; native keyboard focus and widget behavior remain.

Colors and styling live in `frontend/theme.py`; reusable headers, surfaces, badges and evidence
quotes live in `frontend/components.py`. `.streamlit/config.toml` gives native widgets the same
light theme. Start Streamlit from the project directory (or use `run.ps1`) so the native theme
configuration is loaded. See [the design system](docs/ui-design-system.md).

## Setup and run

Python 3.10 or newer is required. Use a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:GEMINI_API_KEY = "your-key"
$env:GEMINI_MODEL = "gemini-2.5-flash"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On Windows, `powershell -ExecutionPolicy Bypass -File .\run.ps1` always starts the app
using this project's `.venv`. Keep that terminal running while using the frontend.
Streamlit is pinned to the verified version so reinstalling requirements does not
silently replace the frontend's hashed JavaScript modules.

If widgets show `Failed to fetch dynamically imported module`, confirm the server is
running and reload the entire tab with **Ctrl+Shift+R**. An open tab can still reference
modules from a previous server/version. If needed, launch `run.ps1 -Port 8502` and open
`http://localhost:8502` to use a fresh browser cache, as described in
[Streamlit's troubleshooting guide](https://docs.streamlit.io/knowledge-base/using-streamlit/sanity-checks).

`GEMINI_API_KEY` is optional: without it, basic checks and conservative matching remain
available. `GEMINI_MODEL` defaults to `gemini-2.5-flash`. For local setup, copy
`.env.example` to `.env` and put your private key after `GEMINI_API_KEY=`. The backend
loads configuration on each new analysis, independent of the terminal's working directory.
Create keys through [Google's API key setup](https://ai.google.dev/gemini-api/docs/api-key).

Configuration precedence is process environment, project `.streamlit/secrets.toml`,
user `~/.streamlit/secrets.toml`, then project `.env`. Streamlit secrets use top-level
`GEMINI_API_KEY = "..."` and optional `GEMINI_MODEL = "..."` entries. `GOOGLE_API_KEY`
is also accepted; within a source `GEMINI_API_KEY` takes precedence. An explicitly empty
environment key disables AI even if a file contains a key. `.env` values are read without
changing the process environment. On hosted deployments use platform secrets. Never commit
a key. Both local credential files are ignored by Git; keys are excluded from settings
representations and are never logged.

If the log says `AI fallback activated (reason=missing_api_key)`, configuration is missing;
it is not a schema failure. The result warning describes how to configure AI. Other safe
reasons distinguish access, quota, timeout, network, model, service and validation errors,
without exposing the provider's error body. Fallback continues to return basic checks.

## Backend structure

```text
backend/
├── __init__.py
├── config.py                    # settings, weights and score mappings
├── models.py                    # Pydantic input, semantic and result contracts
├── ai_response_models.py        # tolerant typed external response models
├── schema_validation.py         # safe model/field validation diagnostics
├── exceptions.py                # safe document and LLM errors
├── normalization.py             # canonical skill names and quote validation
├── parsers/
│   ├── __init__.py
│   ├── file_parser.py           # PDF/DOCX/TXT -> CVDocument
│   ├── cv_parser.py             # CVDocument -> CandidateProfile
│   └── jd_parser.py             # JD text -> typed requirements
├── providers/
│   ├── __init__.py
│   ├── base_llm.py              # replaceable LLMProvider interface
│   ├── gemini_provider.py       # external API transport and JSON validation
│   └── response_schema.py       # simplified outgoing structured-output schema
├── prompts/
│   ├── __init__.py
│   └── cv_analysis_prompt.py    # versioned CV-only and job-match prompts
├── analyzers/
│   ├── __init__.py
│   ├── basic_analyzer.py        # contact, sections, words, bullets, extraction
│   ├── fallback_analyzer.py     # conservative local requirement evaluation
│   ├── gemini_analyzer.py       # prompt selection and semantic contract
│   └── legacy_matcher.py        # optional old-engine comparison adapter
└── services/
    ├── __init__.py
    ├── scoring_service.py       # deterministic, configurable scoring
    └── analysis_service.py      # sole analysis entrypoint and fallback

tests/
├── __init__.py
├── helpers.py                   # synthetic CV/JD and mock provider
├── test_models.py
├── test_ai_response_normalization.py
├── test_file_parser.py
├── test_basic_analyzer.py
├── test_gemini_analyzer.py
├── test_scoring_service.py
└── test_analysis_service.py

examples/
├── __init__.py
└── service_checks.py            # three runnable checks, no real API calls
```

`processor.py`, `matcher.py`, `cv_checker.py`, `constants.py` and their public contracts
remain available. The new parsers/checker reuse legacy heading, bullet, email and
vocabulary helpers. `file_reader.py` preserves its `(text, error)` contract through a
backend adapter. Streamlit calls neither the old engine nor Gemini directly.

## Application contract

```python
from backend.models import CVDocument, CVAnalysisResult
from backend.parsers.file_parser import FileParser
from backend.services.analysis_service import AnalysisService

document = FileParser().parse("candidate.pdf")  # also accepts uploads or bytes + filename
# For pasted text: document = CVDocument(raw_text="...")
service = AnalysisService()
try:
    result: CVAnalysisResult = service.analyze_cv(
        cv_document=document,
        jd_text=None,              # optional; blank means CV-only
        target_position="Data Analyst",
        industry="Data Analyst",
    )
    payload = result.model_dump(mode="json")  # future HTTP API serialization
finally:
    service.close()
```

`CVAnalysisResult` is the stable frontend contract: `mode`, `overall_score`, `scores`,
`candidate_summary`, `detected_skills`, `strengths`, `weaknesses`, `basic_checks`,
`recommendations`, `matched_skills`, `missing_skills`, `partially_matched_skills`,
`requirement_matches`, `warnings`, and `ai_available`. Optional `analysis_metadata`
contains the model, prompt/scoring version, scoring components and effective weights.
Clients should handle it as optional diagnostic information.

`mode` is `cv_only` without a JD and `job_match` with one. CV-only results have empty
matching lists and `scores.job_match = None`. Each requirement match has an exact
requirement label, `matched`/`partial`/`missing`, quotations and an explanation.
No raw Gemini response is exposed to the frontend. Invalid/oversized CV input raises
`InvalidCVError`; file errors raise `DocumentParseError` with a safe message and code.

## Pipeline and replaceable components

```text
FileParser -> CVDocument
                  |
            AnalysisService
                  |
            CVParser + JDParser
                  |
            BasicAnalyzer + GeminiAnalyzer -> LLMProvider
                  |
            grounded semantic signals and requirements
                  |
            ScoringService -> CVAnalysisResult -> UI / future API
```

Extraction, semantic evaluation and scoring are distinct. The service accepts injected
`provider`, `ai_analyzer`, `basic_analyzer`, `scoring_service`, `cv_parser`, `jd_parser`
and `settings`. Another provider implements `LLMProvider.analyze(prompt, schema)` and
returns the requested Pydantic model or a typed LLM error. Changing models uses settings;
changing scoring uses weights/the scoring service; changing prompts uses the prompt
module and `PROMPT_VERSION`. No backend module imports Streamlit.

GeminiProvider lazily creates the `google-genai` client, requests one JSON response
using a simplified `response_schema`, validates it as `AISemanticResponse`, and sets a 30-second HTTP
timeout. SDK retry attempts are set to one; there is no automatic retry loop. A normal
analysis makes one API request. Centralized normalization converts reasonable wire
variations (status aliases, null/omitted lists and optional judgments) into the strict
`AISemanticAnalysis` contract. Extra external fields are discarded; malformed JSON,
invalid types, unsupported labels and failed internal validation still cause fallback.
`AISemanticAnalysis` contains evidence-backed judgments and requirement matches; it
cannot supply a final score. The frontend never consumes the tolerant response model.
See [the schema diagnosis](docs/schema-validation.md) for exact reproduced failures and
normalization rules. The transport follows the [official SDK structured-output interface](https://github.com/googleapis/python-genai#json-response-schema).

## Scoring policy, version 2.0

Weights and mappings live in `backend/config.py` and can be replaced through
`ScoringService(cv_weights=..., job_weights=...)`. Configured weights must sum to 1.0.
Scores use a convex weighted mean rounded once at the end; out-of-range components
are rejected rather than clamped into a plausible score. A model cannot supply the final score.

| CV-only component | Weight |
|---|---:|
| Content quality | 30% |
| Experience | 12.5% |
| Projects | 12.5% |
| Skills | 20% |
| Structure | 15% |
| Education | 10% |

Evidence-backed semantic ratings map `exceptional=92`, `strong=82`, `adequate=70`,
`limited=52`, `weak=35`, `insufficient=15`. Absent or unverifiable evidence uses the
internal `unknown=0` sentinel. Legacy AI labels moderate/medium normalize to adequate;
high normalizes to strong. Exceptional requires unusually compelling evidence; headings,
degree names and skill keywords alone do not warrant strong or exceptional ratings.

All six CV-only categories contribute independently, including missing categories at zero.
The former `max(experience, projects)` rule hid weak experience and has been removed.
The split retains the former combined 25% allocation. Structure uses five binary checks
(email, phone, education, skills, experience **or** projects) and may reach 100 separately
from semantic quality. All exceptional semantic categories plus complete structure produce
93 after rounding. Without AI, content uses the existing bullet action rules capped at 70;
explicit skills, education, experience and projects receive limited presence credit (52).
Fallback proxies do not prove semantic depth or proficiency.

CV-only quality labels are 90–100 Exceptional, 80–89 Strong, 70–79 Solid, 60–69 Fair,
0–59 Needs Improvement. Job-match labels remain separate. The displayed overall is
`CVAnalysisResult.overall_score`, owned exclusively by `ScoringService`.
See [the scoring audit](docs/scoring-audit.md) for the reproduced bug, formulas,
complete ownership path and numeric regression input.

| Job-match component | Weight |
|---|---:|
| Required / hard skills | 35% |
| Experience relevance | 20% |
| Project evidence | 15% |
| Education | 10% |
| Role / title relevance | 10% |
| Soft / other requirements | 10% |

Each requirement belongs to one component. Matched/partial/missing states map to
100/50/0. Preferred items have half the within-component weight of required items.
Duplicate requirements are merged, required wins over preferred, and skills do not
also earn keyword points. Components without JD requirements are excluded and their
weights redistributed proportionally. An empty assessable JD produces zero plus a
warning. Evidence-backed relevance ratings can cap their corresponding component;
they cannot turn a missing concrete requirement into a match. Content/structure values
are additional CV diagnostics in job mode and are not added to the match score.

## Evidence and failure behavior

- Positive AI judgments require quotations actually present in the CV. Unverifiable
  judgments become unknown; matches without valid evidence become missing.
- AI-detected skills are accepted only if they or a canonical alias appear in the CV.
  JD gaps never become candidate skills. PostgreSQL and MySQL remain distinct from SQL.
- An isolated Skills keyword is at most a partial match. Projects can support a skill
  without proving a required duration of professional work. A full duration match
  requires explicit supporting work evidence; date-only inference stays partial.
- Recommendations use backend-owned, conditional actions. AI-generated replacement
  bullets and unsupported accomplishments are never surfaced as editing instructions.
- Missing keys, auth/quota/rate limits, timeouts, network errors, unavailable models and
  invalid responses produce `ai_available=False`, a safe warning, basic checks and
  conservative deterministic results. Provider error bodies/tracebacks are not exposed.
- Empty/unsupported/corrupt documents produce explicit parse errors. Sparse PDF text
  (under 100 characters per page) produces low extraction quality and a review warning.
- Logging records stage events, types and extraction quality, never keys or CV content.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe -m compileall -q backend app.py file_reader.py
.\.venv\Scripts\python.exe -m examples.service_checks
```

All provider tests use mocks; no real Gemini calls are needed. Tests cover PDF/DOCX/TXT,
empty/corrupt/unsupported documents, sparse extraction, email/phone/sections/counts,
CV-only and job modes, all weights, partial credit, relevance, schema failures,
timeout/auth/quota/network failure, fallback, evidence integrity, safe advice and bounds.
The example runs CV-only, CV + JD and a synthetic unavailable-provider scenario with
the synthetic fixtures from `tests/helpers.py`.
The development verification also exercised Streamlit's CV-only and CV + JD flows
with the API key disabled, checked all backend imports, and converted the response
schema through the installed Gemini SDK without contacting the API.

## Remaining limitations and next frontend session

There is no OCR or layout/font/column assessment. File and section extraction remain
heuristic; PDFs with complex reading order and unfamiliar/non-English section labels
may need a professional parser. JD extraction has a fixed skill vocabulary and retains
unknown clauses for AI review. Experience dates are not summed into years. Text evidence
verification proves that a quotation exists, not that every AI interpretation, summary
or strength is true; review generated prose. Scoring policy needs calibration against
reviewed CVs. Live Gemini availability/model behavior has not been integration-tested
by the mocked suite. The score is not an official ATS score or hiring probability.

The product layer wraps `CVAnalysisResult` in `AnalyzerReview` while preserving the
existing analysis contracts. It uses the same grounded semantic response and scoring
service; there are no additional Gemini calls for evidence, reports or rewrite suggestions.
Rewrites are local fact-preserving suggestions with placeholders. Saved review history
is available through the local Career Workspace. PDF reports, an HTTP API,
authentication and job queues remain future work.
#   W e b L a s t t e r m  
 