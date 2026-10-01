# Analyzer product features

The product layer adds a complete review around the existing backend. Scoring weights,
semantic calibration, evidence verification, provider architecture, fallback scoring
and the original models remain unchanged.

## Modes and scores

- Empty or whitespace-only JD: CV Review (`cv_only`).
- A usable JD with at least three words and parsed requirements: CV ↔ Job Match
  (`job_match`). Too-short/heading-only JDs receive a clear error and can be removed.
- CV Review presents the original CV score and six category values.
- Job Match presents a separate CV Quality Score and Job Match Score. They are
  never merged. Both are produced by the existing ScoringService; the UI performs
  no score computation.
- A scoring adapter captures the grounded semantic model already passed by
  AnalysisService to ScoringService. In job mode it runs that same scorer again
  without a JD to get CV quality. It makes no additional Gemini request.

Normal analysis still performs one Gemini request when configured. Expanding evidence,
generating the report, and suggesting rewrites make zero Gemini requests. Re-analyze
explicitly performs another normal analysis.

## Additive contract

`backend/review_models.py` defines `AnalyzerReview`. `CVAnalysisResult`,
`AISemanticAnalysis` and all existing contracts retain their fields and behavior.

| New wrapper field | Purpose |
|---|---|
| analysis | Original, unchanged CVAnalysisResult |
| cv_quality | Separate ScoringOutcome using the existing scoring policy |
| target_role / industry / summary | Presentation context and concise summary |
| skill_evidence | strong_evidence / some_evidence / mention_only, supporting quotations |
| strengths | Up to five existing strengths and evidence-backed explanations |
| improvement_areas | Issue, why it matters, recommended action |
| bullet_reviews | Original bullet, issues, truthful improvement guidance |
| top_recommendations | At most three ordered recommendations |
| requirement_groups | Separate matched / partial / missing requirements |
| display_warnings | Human-readable warnings; technical details remain in debug |

```python
from backend.models import CVDocument
from backend.services.analyzer_review_service import AnalyzerReviewService

service = AnalyzerReviewService()
try:
    review = service.analyze_cv(CVDocument(raw_text="..."), jd_text=None,
                                target_position=None, industry=None)
    original_result = review.analysis
    cv_quality_score = review.cv_quality.overall_score
finally:
    service.close()
```

CV Review uses industry only for presentation; its semantic request receives no
industry context. Job Match can use an explicitly selected industry as context.
Blank industry displays General / Auto. A supplied target role wins; otherwise
the extracted JD title or a CV headline is displayed when available.

## Evidence and bullet review

Skills are classified from verified project/work quotations already in the semantic
response, plus explicit implementation text in the extracted CV. Two distinct
supporting descriptions give strong_evidence, one gives some_evidence, and a mention
without concrete project/work support gives mention_only. Duplicate/subsumed quotes
do not count twice. This describes textual support, not proven proficiency and does
not affect any scoring or requirement status.

Each skill opens to show its quotations and explanation. CV Review uses "Skills with
strong evidence" and "Skills needing stronger evidence", without JD missing-skill
language. Job Match keeps three requirement lists with evidence and explanations.

Bullet review reuses the legacy action/length signals and adds local guidance for
unclear implementation, contribution or outcome. Evaluation/validation wording is
recognized. It does not require every student project to claim business impact.

`rewrite_bullets(bullets, context)` takes one batch of at most 20 selected bullets.
It preserves their existing wording and adds bracketed requests for unknown details.
It never adds numeric metrics, users, revenue or performance claims. No LLM request
is made. These are guided edits rather than fluent AI-generated rewrites; review and
complete or remove placeholders before using them in a CV.

## UX and reports

Results show up to three priorities, strengths, improvement areas, skills evidence,
CV issues and bullet review. A concise summary and AI + Basic / Basic fallback status
appear at the top. Normal warnings omit provider details; a collapsed debug expander
contains existing technical warnings and analysis metadata.

Download Report exports Markdown with scores, strengths, improvement areas, skills
evidence, priorities, bullet guidance and job requirements when applicable. It excludes
provider names, prompt/scoring versions and other internal debug metadata. PDF export
is not implemented.

Edit inputs preserves drafts. Re-analyze repeats the saved inputs. Analyze another CV
clears the document, result, selected bullets, rewrite suggestions and upload signatures.
Failed extraction and input validation show readable messages; a safe error boundary
also prevents unexpected review errors from exposing Python exceptions in the UI.

## Limitations and verification

Evidence classification, title extraction and bullet detection are heuristic. Unusual
headings, complex PDF reading order and unmarked bullet paragraphs may need manual
review. Skill counts are not proof of separate projects or proficiency. Existing AI
strengths and summaries still require user review. Markdown is the current report format.

Tests compare original and product-layer results for CV-only, JD and fallback flows,
exercise all three skill states, role defaults, blank industry, requirement grouping,
safe rewrites and reports, and run actual Streamlit input/edit/reset/re-analysis flows.
The existing scoring suite runs unchanged. Protected backend file hashes are checked
against the baseline recorded before this feature work.
