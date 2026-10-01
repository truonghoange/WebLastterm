from datetime import datetime, timezone
import sqlite3

from backend.storage.database import Database
from backend.storage.models import CVWrite, SavedCV, WorkspaceError


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class CVRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, data: CVWrite, *, connection=None) -> SavedCV:
        values = data.model_dump()
        values.update(created_at=timestamp(), updated_at=timestamp())
        columns = ",".join(values)
        with self.database.transaction(connection) as db:
            cursor = db.execute(f"INSERT INTO cvs ({columns}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
            return self.get_by_id(cursor.lastrowid, connection=db)

    def get_by_id(self, cv_id: int, *, connection=None) -> SavedCV | None:
        with self.database.transaction(connection) as db:
            row = db.execute("SELECT * FROM cvs WHERE id=?", (cv_id,)).fetchone()
            return SavedCV.model_validate(dict(row)) if row else None

    def list_all(self) -> list[SavedCV]:
        with self.database.transaction() as db:
            return [SavedCV.model_validate(dict(row)) for row in db.execute("SELECT * FROM cvs ORDER BY updated_at DESC, id DESC")]

    def update(self, cv_id: int, data: CVWrite, *, connection=None) -> SavedCV:
        values = data.model_dump()
        values["updated_at"] = timestamp()
        with self.database.transaction(connection) as db:
            cursor = db.execute(f"UPDATE cvs SET {','.join(name+'=?' for name in values)} WHERE id=?", (*values.values(), cv_id))
            if not cursor.rowcount:
                raise WorkspaceError("This CV no longer exists.")
            return self.get_by_id(cv_id, connection=db)

    def mark_analyzed(self, cv_id: int, score: int, analyzed_at: str, *, connection=None):
        with self.database.transaction(connection) as db:
            db.execute("UPDATE cvs SET latest_cv_score=?,last_analyzed_at=?,updated_at=? WHERE id=?", (score, analyzed_at, timestamp(), cv_id))

    def delete(self, cv_id: int):
        try:
            with self.database.transaction() as db:
                if not db.execute("DELETE FROM cvs WHERE id=?", (cv_id,)).rowcount:
                    raise WorkspaceError("This CV no longer exists.")
        except sqlite3.IntegrityError:
            raise WorkspaceError("Cannot delete this CV because it is used in applications. Delete those applications first.") from None

    def refresh_analysis_metadata(self, cv_id: int, *, connection=None):
        with self.database.transaction(connection) as db:
            db.execute("""UPDATE cvs SET
                latest_cv_score=(SELECT cv_quality_score FROM analyses WHERE cv_id=? ORDER BY id DESC LIMIT 1),
                last_analyzed_at=(SELECT created_at FROM analyses WHERE cv_id=? ORDER BY id DESC LIMIT 1)
                WHERE id=?""", (cv_id, cv_id, cv_id))
