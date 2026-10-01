import sqlite3

from pydantic import ValidationError

from backend.review_models import AnalyzerReview
from backend.storage.cv_repository import timestamp
from backend.storage.database import Database
from backend.storage.models import AnalysisSnapshot, WorkspaceDataError, WorkspaceError


def _snapshot(row) -> AnalysisSnapshot | None:
    if row is None:
        return None
    values = dict(row)
    try:
        values["review"] = AnalyzerReview.model_validate_json(values.pop("analysis_json"))
        return AnalysisSnapshot.model_validate(values)
    except (ValidationError, ValueError, TypeError):
        raise WorkspaceDataError("A saved analysis could not be read. Re-analyze the CV to create a new snapshot.") from None


class AnalysisRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, cv_id: int, review: AnalyzerReview, job_id: int | None = None, *, connection=None) -> AnalysisSnapshot:
        # Revalidate normalized data before persistence, including mutated model instances.
        review = AnalyzerReview.model_validate_json(review.model_dump_json())
        if job_id is not None and review.analysis.mode != "job_match":
            raise WorkspaceError("A job comparison must contain a job-match review.")
        match = review.analysis.overall_score if review.analysis.mode == "job_match" else None
        try:
            with self.database.transaction(connection) as db:
                cursor = db.execute("INSERT INTO analyses (cv_id,job_id,mode,cv_quality_score,job_match_score,analysis_json,created_at) VALUES (?,?,?,?,?,?,?)",
                    (cv_id, job_id, review.analysis.mode, review.cv_quality.overall_score, match, review.model_dump_json(), timestamp()))
                return self.get_by_id(cursor.lastrowid, connection=db)
        except sqlite3.IntegrityError:
            raise WorkspaceError("Select an existing saved CV and job before saving an analysis.") from None

    def get_by_id(self, analysis_id: int, *, connection=None) -> AnalysisSnapshot | None:
        with self.database.transaction(connection) as db:
            return _snapshot(db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone())

    def list_for_cv(self, cv_id: int, limit: int = 50) -> list[AnalysisSnapshot]:
        with self.database.transaction() as db:
            return [_snapshot(row) for row in db.execute("SELECT * FROM analyses WHERE cv_id=? ORDER BY id DESC LIMIT ?", (cv_id, limit))]

    def list_for_pair(self, cv_id: int, job_id: int, limit: int = 50) -> list[AnalysisSnapshot]:
        with self.database.transaction() as db:
            return [_snapshot(row) for row in db.execute("SELECT * FROM analyses WHERE cv_id=? AND job_id=? ORDER BY id DESC LIMIT ?", (cv_id, job_id, limit))]

    def latest_for_cv(self, cv_id: int) -> AnalysisSnapshot | None:
        rows = self.list_for_cv(cv_id, limit=1)
        return rows[0] if rows else None

    def latest_for_pair(self, cv_id: int, job_id: int) -> AnalysisSnapshot | None:
        rows = self.list_for_pair(cv_id, job_id, limit=1)
        return rows[0] if rows else None

    def latest_per_cv(self) -> list[AnalysisSnapshot]:
        with self.database.transaction() as db:
            return [_snapshot(row) for row in db.execute("SELECT * FROM analyses WHERE id IN (SELECT MAX(id) FROM analyses GROUP BY cv_id) ORDER BY id DESC")]

    def latest_per_pair(self, job_id: int | None = None) -> list[AnalysisSnapshot]:
        with self.database.transaction() as db:
            rows = db.execute("SELECT * FROM analyses WHERE id IN (SELECT MAX(id) FROM analyses WHERE job_id IS NOT NULL GROUP BY cv_id,job_id) ORDER BY id DESC")
            return [_snapshot(row) for row in rows if job_id is None or row["job_id"] == job_id]

    def cv_ids_for_job(self, job_id: int, *, connection=None) -> list[int]:
        with self.database.transaction(connection) as db:
            return [row[0] for row in db.execute("SELECT DISTINCT cv_id FROM analyses WHERE job_id=?", (job_id,))]
