import sqlite3

from backend.storage.cv_repository import timestamp
from backend.storage.database import Database
from backend.storage.models import JobWrite, SavedJob, WorkspaceError


class JobRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, data: JobWrite, *, connection=None) -> SavedJob:
        values = data.model_dump()
        values.update(created_at=timestamp(), updated_at=timestamp())
        with self.database.transaction(connection) as db:
            cursor = db.execute(f"INSERT INTO jobs ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
            return self.get_by_id(cursor.lastrowid, connection=db)

    def get_by_id(self, job_id: int, *, connection=None) -> SavedJob | None:
        with self.database.transaction(connection) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return SavedJob.model_validate(dict(row)) if row else None

    def list_all(self) -> list[SavedJob]:
        with self.database.transaction() as db:
            return [SavedJob.model_validate(dict(row)) for row in db.execute("SELECT * FROM jobs ORDER BY updated_at DESC, id DESC")]

    def update(self, job_id: int, data: JobWrite) -> SavedJob:
        values = data.model_dump()
        values["updated_at"] = timestamp()
        with self.database.transaction() as db:
            cursor = db.execute(f"UPDATE jobs SET {','.join(name+'=?' for name in values)} WHERE id=?", (*values.values(), job_id))
            if not cursor.rowcount:
                raise WorkspaceError("This job no longer exists.")
            return self.get_by_id(job_id, connection=db)

    def delete(self, job_id: int, *, connection=None):
        try:
            with self.database.transaction(connection) as db:
                if not db.execute("DELETE FROM jobs WHERE id=?", (job_id,)).rowcount:
                    raise WorkspaceError("This job no longer exists.")
        except sqlite3.IntegrityError:
            raise WorkspaceError("Cannot delete this job because it is used in applications. Delete those applications first.") from None
