# Career Workspace

The MVP stores CVs, jobs, applications and normalized review history in SQLite.
It introduces no authentication, cloud database, background tasks or new AI analysis logic.
Scoring, semantic calibration, prompts, provider, evidence verification, fallback,
AnalysisService and AnalyzerReviewService remain unchanged.

## Dependency direction

```text
app.py / frontend.workspace_ui / frontend.review_ui
                       |
                WorkspaceService
                       |
     CV / Job / Application / Analysis repositories
                       |
                  Database / SQLite
```

The frontend never executes SQL or accesses repositories directly. Repositories return
validated Pydantic models, not SQLite rows. Analysis snapshots serialize an existing
`AnalyzerReview` using `model_dump_json()` and validate it on reading, including mode and
score consistency. Raw Gemini responses and request payloads are not stored.

## Initialization and configuration

```python
from backend.storage import initialize_database
from backend.services.workspace_service import WorkspaceService

database = initialize_database()  # safe repeatedly; never drops tables
workspace = WorkspaceService()   # initializes lazily when a workspace action needs it
```

`CVISION_DB_PATH` uses the process environment, then project `.env`, then the default
`data/cvision.db`. Relative configured paths resolve from the project root. Parent
directories are created. Repositories use short-lived connections, bound values,
transactions, foreign keys and a ten-second SQLite lock timeout.

Tests use temporary file databases. A pytest fixture redirects the environment for every
test, including UI regressions, so tests never use the user's `data/cvision.db`.

## Tables and relations

| Table | Stored data | Relations |
|---|---|---|
| `cvs` | Display name, extracted text, file/source metadata, target/headline, timestamps, latest quality | Parent of analyses/applications |
| `jobs` | Title, company, JD, location, URL, notes, timestamps | Parent of comparisons/applications |
| `analyses` | CV/job IDs, mode, quality/match scores, normalized review JSON, timestamp | CV required; job optional |
| `applications` | CV/job IDs, status, date applied, notes, timestamps | CV and job required; unique pair |

Application statuses are constrained in Pydantic and SQLite:
`saved`, `applied`, `interview`, `offer`, `rejected`, `withdrawn`.
Indexes support CV history, job comparisons, application relations and status.

CV/Job deletion is blocked if any application refers to it. Delete those applications
first. Once unreferenced, deleting a CV or job cascades only its analyses; other CVs/jobs
and unrelated histories remain. Deleting an application preserves its CV, job and history.
Job deletion refreshes affected CV score caches from the remaining history.
The UI requires a separate confirmation click for all deletions.

## Analysis and saves

- Analyze an uploaded/pasted CV with the existing Analyzer, then use **Save CV**.
- New CVs request a display name; saved CVs use **Update saved CV** and retain their ID.
- Repeatedly saving the same displayed snapshot does not append duplicate history.
- An explicit re-analysis of a saved CV appends a new snapshot and refreshes latest quality.
- Compare a saved CV and job through `WorkspaceService.compare_cv_to_job()`; it calls the
  existing AnalyzerReviewService exactly once and saves a snapshot automatically.
- The existing result UI displays separate CV Quality and Job Match scores.
- Opening a CV, job, application or historical snapshot performs no analysis.
- Rewrites continue to use the existing local suggestion implementation.

A CV saved from a comparison against an unsaved JD retains the normalized job-mode review
with `job_id=None`. It contributes to that CV's latest quality, but is excluded from pair
averages and job-based skills aggregation until an explicit comparison with a saved job
creates a linked snapshot. The original JD is not persisted by Save CV; save jobs through
Jobs. No job is created silently.

## Insights policy

- Average CV Quality: latest snapshot for each analyzed CV, including the separate quality
  from job-mode reviews. Unanalyzed CVs are excluded.
- Average Job Match: latest comparison per saved CV/job pair. Historical reruns and
  comparisons with unsaved jobs are excluded.
- Missing skills: only `missing_skills` from latest linked comparisons; partial skills
  are shown separately. Counts use distinct jobs, so multiple CVs for one job do not
  inflate the job count. Different CVs may demonstrate different states for the same job.
- Requested skills: existing JDParser's normalized skill requirements across saved jobs,
  one occurrence per job. No new parser or Gemini call.
- Recurring improvement areas: exact normalized issue text from each CV's latest review,
  once per CV. Differently worded issues are not grouped by an LLM.
- Active applications: Saved, Applied, Interview and Offer. Rejected/Withdrawn are excluded.
- Pipeline: all six statuses, with zero counts displayed.
- History deltas say **Score change**, without claiming improvement or hiring probability.

## Privacy and limitations

CV text, JD text, contact information, keys and provider response bodies are never logged.
Error logs record only the exception type; users see safe, actionable messages.
The local database is plain text and not encrypted. Protect the file and backups. No
tracking or analytics is added. Workspace pages show metadata, verified evidence and
requested JD text rather than printing full CV text; Analyzer inputs remain editable.

This is a single shared local workspace. It has no account isolation, cloud sync,
scraping or automated notifications. SQLite initialization is additive with `CREATE IF
NOT EXISTS`; future incompatible schema changes will need an explicit migration.
Editing a CV/job preserves previous snapshots rather than rewriting their history;
past comparisons therefore refer to the inputs analyzed at that time. Snapshots retain
normalized evidence/results rather than full historical copies of documents.
The CV detail shows up to 50 recent snapshots, while insight queries consider all records.
Insight vocabularies and evidence limitations are inherited from the existing analyzer.
