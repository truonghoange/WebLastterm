from datetime import date
import sqlite3

from backend.storage.cv_repository import timestamp
from backend.storage.database import Database
from backend.storage.models import ApplicationStatus, ApplicationWrite, SavedApplication, WorkspaceError


class ApplicationRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, data: ApplicationWrite) -> SavedApplication:
        values = data.model_dump(mode="json")
        values.update(created_at=timestamp(), updated_at=timestamp())
        try:
            with self.database.transaction() as db:
                cursor = db.execute(f"INSERT INTO applications ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
                return self.get_by_id(cursor.lastrowid, connection=db)
        except sqlite3.IntegrityError:
            if self.get_for_pair(data.cv_id, data.job_id):
                raise WorkspaceError("Application already exists for this job and CV.") from None
            raise WorkspaceError("Select an existing saved CV and job.") from None

    def get_by_id(self, application_id: int, *, connection=None) -> SavedApplication | None:
        with self.database.transaction(connection) as db:
            row = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
            return SavedApplication.model_validate(dict(row)) if row else None

    def get_for_pair(self, cv_id: int, job_id: int) -> SavedApplication | None:
        with self.database.transaction() as db:
            row = db.execute("SELECT * FROM applications WHERE cv_id=? AND job_id=?", (cv_id, job_id)).fetchone()
            return SavedApplication.model_validate(dict(row)) if row else None

    def list_all(self) -> list[SavedApplication]:
        with self.database.transaction() as db:
            return [SavedApplication.model_validate(dict(row)) for row in db.execute("SELECT * FROM applications ORDER BY updated_at DESC, id DESC")]

    def update(self, application_id: int, status: ApplicationStatus, date_applied: date | None, notes: str) -> SavedApplication:
        # Validate even callers that pass a runtime string to this typed interface.
        try:
            status = ApplicationStatus(status)
        except (ValueError, TypeError):
            raise WorkspaceError("Select a valid application status.") from None
        with self.database.transaction() as db:
            cursor = db.execute("UPDATE applications SET status=?,date_applied=?,notes=?,updated_at=? WHERE id=?",
                (status.value, date_applied.isoformat() if date_applied else None, notes, timestamp(), application_id))
            if not cursor.rowcount:
                raise WorkspaceError("This application no longer exists.")
            return self.get_by_id(application_id, connection=db)

    def delete(self, application_id: int):
        with self.database.transaction() as db:
            if not db.execute("DELETE FROM applications WHERE id=?", (application_id,)).rowcount:
                raise WorkspaceError("This application no longer exists.")
