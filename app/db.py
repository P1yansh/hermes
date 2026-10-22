import json
import sqlite3
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings, to_utc
from app.models.academic import ExtractedTask
from app.models.opportunity import OpportunityItem

def slugify(text: str) -> str:
    """Generate a clean canonical slug for deduplicating opportunities and tasks."""
    text = (text or "").lower()
    text = re.sub(r"\[.*?\]|\(.*?\)", "", text) # Remove brackets
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    # Strip common noise prefixes
    for prefix in ["2-days-left-why-early-submitters-win-", "you-re-registered-", "reminder-", "announcing-"]:
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text[:80]

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
                    account_source TEXT DEFAULT 'default',
                    has_explicit_deadline INTEGER DEFAULT 1,
                    thread_id TEXT,
                    canonical_slug TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL,
                    organizer TEXT NOT NULL,
                    deadline TEXT,
                    prizes TEXT,
                    tags TEXT,
                    description TEXT NOT NULL,
                    url TEXT NOT NULL,
                    relevance_score INTEGER DEFAULT 5,
                    mode TEXT DEFAULT 'online',
                    city TEXT,
                    country TEXT DEFAULT 'India',
                    eligible INTEGER DEFAULT 1,
                    eligibility_reason TEXT,
                    source_inbox TEXT,
                    match_score INTEGER,
                    has_explicit_deadline INTEGER DEFAULT 1,
                    thread_id TEXT,
                    canonical_slug TEXT,
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_ledger (
                    account_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    thread_id TEXT,
                    internal_date INTEGER,
                    subject TEXT,
                    sender TEXT,
                    is_read INTEGER DEFAULT 0,
                    classification TEXT NOT NULL,
                    extracted_entity_id TEXT,
                    llm_tokens_spent INTEGER DEFAULT 0,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, message_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_thread ON email_ledger(account_id, thread_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_entity ON email_ledger(extracted_entity_id)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS deadline_search_cache (
                    event_key TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    resolved_deadline_iso TEXT,
                    searched_at TEXT NOT NULL
                )
            """)

            # Migration checks for existing columns
            for col, col_type in [
                ("account_source", "TEXT DEFAULT 'default'"),
                ("has_explicit_deadline", "INTEGER DEFAULT 1"),
                ("thread_id", "TEXT"),
                ("canonical_slug", "TEXT")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            for col, col_type in [
                ("mode", "TEXT DEFAULT 'online'"),
                ("city", "TEXT"),
                ("country", "TEXT DEFAULT 'India'"),
                ("eligible", "INTEGER DEFAULT 1"),
                ("eligibility_reason", "TEXT"),
                ("source_inbox", "TEXT"),
                ("match_score", "INTEGER"),
                ("has_explicit_deadline", "INTEGER DEFAULT 1"),
                ("thread_id", "TEXT"),
                ("canonical_slug", "TEXT")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE opportunities ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            conn.commit()

    # --- EMAIL LEDGER METHODS ---

    def record_email_ledger(
        self,
        account_id: str,
        message_id: str,
        classification: str,
        thread_id: Optional[str] = None,
        internal_date: Optional[int] = None,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        is_read: int = 0,
        extracted_entity_id: Optional[str] = None,
        llm_tokens_spent: int = 0
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO email_ledger (
                    account_id, message_id, thread_id, internal_date,
                    subject, sender, is_read, classification,
                    extracted_entity_id, llm_tokens_spent, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                account_id, message_id, thread_id, internal_date,
                subject, sender, is_read, classification,
                extracted_entity_id, llm_tokens_spent, now
            ))
            # Also register in seen_items for quick deduplication checks
            cursor.execute(
                "INSERT OR IGNORE INTO seen_items (id, source_type, first_seen_at) VALUES (?, ?, ?)",
                (f"{account_id}:{message_id}", "email", now)
            )
            conn.commit()

    def is_email_in_ledger(self, account_id: str, message_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM email_ledger WHERE account_id = ? AND message_id = ?",
                (account_id, message_id)
            )
            return cursor.fetchone() is not None

    def get_ledger_entry(self, account_id: str, message_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM email_ledger WHERE account_id = ? AND message_id = ?",
                (account_id, message_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # --- DEADLINE SEARCH CACHE ---

    def get_cached_deadline(self, event_key: str) -> tuple[bool, Optional[str]]:
        """
        Returns (is_cached: bool, resolved_deadline_iso: Optional[str]).
        If cached with null deadline, returns (True, None).
        If never searched, returns (False, None).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT resolved_deadline_iso FROM deadline_search_cache WHERE event_key = ?",
                (event_key,)
            )
            row = cursor.fetchone()
            if row:
                return True, row["resolved_deadline_iso"]
            return False, None

    def save_cached_deadline(self, event_key: str, query: str, deadline_iso: Optional[str]):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO deadline_search_cache (
                    event_key, query, resolved_deadline_iso, searched_at
                ) VALUES (?, ?, ?, ?)
            """, (event_key, query, deadline_iso, now))
            conn.commit()

    # --- ENTITY LOOKUP FOR THREAD & SLUG MERGING ---

    def find_task_by_thread_or_slug(self, thread_id: Optional[str], slug: Optional[str]) -> Optional[ExtractedTask]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = None
            if thread_id:
                cursor.execute("SELECT * FROM tasks WHERE thread_id = ? LIMIT 1", (thread_id,))
                row = cursor.fetchone()
            if not row and slug:
                cursor.execute("SELECT * FROM tasks WHERE canonical_slug = ? LIMIT 1", (slug,))
                row = cursor.fetchone()
            if row:
                deadline = datetime.fromisoformat(row["deadline"]) if row["deadline"] else None
                keys = row.keys()
                return ExtractedTask(
                    source_type=row["source_type"],
                    source_id=row["source_id"],
                    course_or_sender=row["course_or_sender"],
                    title=row["title"],
                    deadline=deadline,
                    action_required=row["action_required"] or "",
                    is_urgent=bool(row["is_urgent"]),
                    submission_url=row["submission_url"],
                    estimated_hours=row["estimated_hours"],
                    confidence=row["confidence"],
                    account_source=row["account_source"] if "account_source" in keys else "default",
                    has_explicit_deadline=bool(row["has_explicit_deadline"]) if "has_explicit_deadline" in keys else (deadline is not None),
                    thread_id=row["thread_id"] if "thread_id" in keys else None,
                    canonical_slug=row["canonical_slug"] if "canonical_slug" in keys else None
                )
        return None

    def find_opportunity_by_thread_or_slug(self, thread_id: Optional[str], slug: Optional[str]) -> Optional[OpportunityItem]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            row = None
            if thread_id:
                cursor.execute("SELECT * FROM opportunities WHERE thread_id = ? LIMIT 1", (thread_id,))
                row = cursor.fetchone()
            if not row and slug:
                cursor.execute("SELECT * FROM opportunities WHERE canonical_slug = ? LIMIT 1", (slug,))
                row = cursor.fetchone()
            if row:
                deadline = datetime.fromisoformat(row["deadline"]) if row["deadline"] else None
                tags = json.loads(row["tags"]) if row["tags"] else []
                keys = row.keys()
                return OpportunityItem(
                    id=row["id"],
                    title=row["title"],
                    type=row["type"],
                    organizer=row["organizer"],
                    deadline=deadline,
                    prizes=row["prizes"],
                    tags=tags,
                    description=row["description"],
                    url=row["url"],
                    relevance_score=row["relevance_score"],
                    mode=row["mode"] if "mode" in keys and row["mode"] else "online",
                    city=row["city"] if "city" in keys else None,
                    country=row["country"] if "country" in keys and row["country"] else "India",
                    eligible=bool(row["eligible"]) if "eligible" in keys else True,
                    eligibility_reason=row["eligibility_reason"] if "eligibility_reason" in keys else None,
                    source_inbox=row["source_inbox"] if "source_inbox" in keys else None,
                    match_score=row["match_score"] if "match_score" in keys else None,
                    has_explicit_deadline=bool(row["has_explicit_deadline"]) if "has_explicit_deadline" in keys else (deadline is not None),
                    thread_id=row["thread_id"] if "thread_id" in keys else None,
                    canonical_slug=row["canonical_slug"] if "canonical_slug" in keys else None
                )
        return None

    # --- TASKS & OPPORTUNITIES CRUD ---

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
                slug = t.canonical_slug or slugify(t.title)
                cursor.execute("""
                    INSERT OR REPLACE INTO tasks (
                        id, source_type, source_id, course_or_sender, title,
                        deadline, action_required, is_urgent, submission_url,
                        estimated_hours, confidence, account_source,
                        has_explicit_deadline, thread_id, canonical_slug, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id, t.source_type, t.source_id, t.course_or_sender, t.title,
                    deadline_iso, t.action_required, 1 if t.is_urgent else 0,
                    t.submission_url, t.estimated_hours, t.confidence,
                    t.account_source or "default",
                    1 if (t.has_explicit_deadline and deadline_iso) else 0,
                    t.thread_id, slug, now
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
                keys = row.keys()
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
                    confidence=row["confidence"],
                    account_source=row["account_source"] if "account_source" in keys else "default",
                    has_explicit_deadline=bool(row["has_explicit_deadline"]) if "has_explicit_deadline" in keys else (deadline is not None),
                    thread_id=row["thread_id"] if "thread_id" in keys else None,
                    canonical_slug=row["canonical_slug"] if "canonical_slug" in keys else None
                ))
        return tasks

    def save_opportunities(self, opportunities: list[OpportunityItem]):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for o in opportunities:
                deadline_iso = to_utc(o.deadline).isoformat() if o.deadline else None
                tags_json = json.dumps(o.tags)
                slug = o.canonical_slug or slugify(o.title)
                cursor.execute("""
                    INSERT OR REPLACE INTO opportunities (
                        id, title, type, organizer, deadline, prizes,
                        tags, description, url, relevance_score,
                        mode, city, country, eligible, eligibility_reason,
                        source_inbox, match_score, has_explicit_deadline,
                        thread_id, canonical_slug, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    o.id, o.title, o.type, o.organizer, deadline_iso, o.prizes,
                    tags_json, o.description, o.url, o.relevance_score,
                    o.mode or "online", o.city, o.country or "India",
                    1 if o.eligible else 0, o.eligibility_reason,
                    o.source_inbox, o.match_score,
                    1 if (o.has_explicit_deadline and deadline_iso) else 0,
                    o.thread_id, slug, now
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
                deadline = datetime.fromisoformat(row["deadline"]) if row["deadline"] else None
                tags = json.loads(row["tags"]) if row["tags"] else []
                keys = row.keys()
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
                    relevance_score=row["relevance_score"],
                    mode=row["mode"] if "mode" in keys and row["mode"] else "online",
                    city=row["city"] if "city" in keys else None,
                    country=row["country"] if "country" in keys and row["country"] else "India",
                    eligible=bool(row["eligible"]) if "eligible" in keys else True,
                    eligibility_reason=row["eligibility_reason"] if "eligibility_reason" in keys else None,
                    source_inbox=row["source_inbox"] if "source_inbox" in keys else None,
                    match_score=row["match_score"] if "match_score" in keys else None,
                    has_explicit_deadline=bool(row["has_explicit_deadline"]) if "has_explicit_deadline" in keys else (deadline is not None),
                    thread_id=row["thread_id"] if "thread_id" in keys else None,
                    canonical_slug=row["canonical_slug"] if "canonical_slug" in keys else None
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
            cursor.execute("DELETE FROM email_ledger")
            cursor.execute("DELETE FROM deadline_search_cache")
            conn.commit()

db = Database()
