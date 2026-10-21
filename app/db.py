import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings, to_utc
from app.models.academic import ExtractedTask
from app.models.opportunity import OpportunityItem

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or settings.DATABASE_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_items (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    course_or_sender TEXT NOT NULL,
                    title TEXT NOT NULL,
                    deadline TEXT,
                    action_required TEXT,
                    is_urgent INTEGER DEFAULT 0,
                    submission_url TEXT,
                    estimated_hours REAL DEFAULT 1.0,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL,
                    organizer TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    prizes TEXT,
                    tags TEXT,
                    description TEXT NOT NULL,
                    url TEXT NOT NULL,
                    relevance_score INTEGER DEFAULT 5,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS briefings (
                    id TEXT PRIMARY KEY,
                    headline TEXT NOT NULL,
                    script TEXT NOT NULL,
                    audio_hash TEXT,
                    items_covered INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def is_item_seen(self, item_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_items WHERE id = ?", (item_id,))
            return cursor.fetchone() is not None

    def mark_item_seen(self, item_id: str, source_type: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO seen_items (id, source_type, first_seen_at) VALUES (?, ?, ?)",
                (item_id, source_type, now)
            )
            conn.commit()

    def save_tasks(self, tasks: list[ExtractedTask]):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for t in tasks:
                deadline_iso = to_utc(t.deadline).isoformat() if t.deadline else None
                task_id = f"{t.source_type}_{t.source_id}"
                cursor.execute("""
                    INSERT OR REPLACE INTO tasks (
                        id, source_type, source_id, course_or_sender, title,
                        deadline, action_required, is_urgent, submission_url,
                        estimated_hours, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id, t.source_type, t.source_id, t.course_or_sender, t.title,
                    deadline_iso, t.action_required, 1 if t.is_urgent else 0,
                    t.submission_url, t.estimated_hours, t.confidence, now
                ))
                cursor.execute(
                    "INSERT OR IGNORE INTO seen_items (id, source_type, first_seen_at) VALUES (?, ?, ?)",
                    (t.source_id, t.source_type, now)
                )
            conn.commit()

    def get_all_tasks(self) -> list[ExtractedTask]:
        tasks: list[ExtractedTask] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks ORDER BY deadline ASC")
            for row in cursor.fetchall():
                deadline = datetime.fromisoformat(row["deadline"]) if row["deadline"] else None
                tasks.append(ExtractedTask(
                    source_type=row["source_type"],
                    source_id=row["source_id"],
                    course_or_sender=row["course_or_sender"],
                    title=row["title"],
                    deadline=deadline,
                    action_required=row["action_required"] or "",
                    is_urgent=bool(row["is_urgent"]),
                    submission_url=row["submission_url"],
                    estimated_hours=row["estimated_hours"],
                    confidence=row["confidence"]
                ))
        return tasks

    def save_opportunities(self, opportunities: list[OpportunityItem]):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for o in opportunities:
                deadline_iso = to_utc(o.deadline).isoformat()
                tags_json = json.dumps(o.tags)
                cursor.execute("""
                    INSERT OR REPLACE INTO opportunities (
                        id, title, type, organizer, deadline, prizes,
                        tags, description, url, relevance_score, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    o.id, o.title, o.type, o.organizer, deadline_iso, o.prizes,
                    tags_json, o.description, o.url, o.relevance_score, now
                ))
                cursor.execute(
                    "INSERT OR IGNORE INTO seen_items (id, source_type, first_seen_at) VALUES (?, ?, ?)",
                    (o.id, "opportunity", now)
                )
            conn.commit()

    def get_all_opportunities(self) -> list[OpportunityItem]:
        opps: list[OpportunityItem] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM opportunities ORDER BY relevance_score DESC, deadline ASC")
            for row in cursor.fetchall():
                deadline = datetime.fromisoformat(row["deadline"])
                tags = json.loads(row["tags"]) if row["tags"] else []
                opps.append(OpportunityItem(
                    id=row["id"],
                    title=row["title"],
                    type=row["type"],
                    organizer=row["organizer"],
                    deadline=deadline,
                    prizes=row["prizes"],
                    tags=tags,
                    description=row["description"],
                    url=row["url"],
                    relevance_score=row["relevance_score"]
                ))
        return opps

    def save_briefing(self, headline: str, script: str, audio_hash: Optional[str] = None, items_covered: int = 0):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO briefings (id, headline, script, audio_hash, items_covered, created_at)
                VALUES ('latest', ?, ?, ?, ?, ?)
            """, (headline, script, audio_hash, items_covered, now))
            conn.commit()

    def get_latest_briefing(self) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM briefings WHERE id = 'latest'")
            row = cursor.fetchone()
            if row:
                return {
                    "headline": row["headline"],
                    "script": row["script"],
                    "audio_hash": row["audio_hash"],
                    "items_covered": row["items_covered"],
                    "created_at": row["created_at"]
                }
        return None

    def clear_all(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM seen_items")
            cursor.execute("DELETE FROM tasks")
            cursor.execute("DELETE FROM opportunities")
            cursor.execute("DELETE FROM briefings")
            conn.commit()

db = Database()
