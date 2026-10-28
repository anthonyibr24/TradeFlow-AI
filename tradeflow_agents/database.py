"""SQLite database for agent approval tracking and audit trail.

Stores transfer recommendations, approval decisions, and agent communication logs.
Survives restarts so approval decisions persist across sessions.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional


DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tradeflow_agents.db",
)


class AgentDatabase:
    """Lightweight SQLite persistent storage for the agent system."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def close(self):
        """Close any pooled connections (SQLite opens per-call, so this is a no-op)."""
        pass

    def _init_schema(self):
        conn = self._get_conn()
        try:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS recommendations (
                recommendation_id   TEXT PRIMARY KEY,
                scenario            TEXT NOT NULL,
                sku                 TEXT NOT NULL,
                source_warehouse    TEXT NOT NULL,
                destination_warehouse TEXT NOT NULL,
                transfer_quantity   INTEGER NOT NULL,
                lead_time_days      INTEGER NOT NULL,
                transfer_cost_aed   REAL NOT NULL,
                expected_unmet_avoided REAL NOT NULL,
                estimated_net_benefit_aed REAL NOT NULL,
                explanation         TEXT,
                approval_status     TEXT NOT NULL DEFAULT 'Pending',
                decision_timestamp  TEXT,
                decided_by          TEXT,
                decision_note       TEXT,
                created_timestamp   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                action      TEXT NOT NULL,
                entity_type TEXT,
                entity_id   TEXT,
                details     TEXT,
                status      TEXT NOT NULL DEFAULT 'success'
            );

            CREATE TABLE IF NOT EXISTS agent_messages (
                message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                agent_name  TEXT NOT NULL,
                task        TEXT NOT NULL,
                inputs      TEXT,
                outputs     TEXT,
                status      TEXT NOT NULL DEFAULT 'success',
                error       TEXT
            );
            """)
            conn.commit()
        finally:
            conn.close()

    # -- Recommendation operations --

    def save_recommendation(self, rec: dict) -> str:
        """Insert or replace a recommendation. Returns the recommendation_id.

        If the recommendation already exists, preserves existing approval status,
        decision timestamp, decided_by, and decision_note.
        """
        rec_id = rec["recommendation_id"]
        conn = self._get_conn()
        try:
            # Check if record already exists (preserve approval state)
            existing = conn.execute(
                "SELECT approval_status, decision_timestamp, decided_by, decision_note "
                "FROM recommendations WHERE recommendation_id = ?",
                (rec_id,),
            ).fetchone()

            if existing:
                # Preserve existing approval decision
                approval_status = existing["approval_status"]
                decision_timestamp = existing["decision_timestamp"]
                decided_by = existing["decided_by"]
                decision_note = existing["decision_note"]
            else:
                approval_status = rec.get("approval_status", "Pending")
                decision_timestamp = None
                decided_by = None
                decision_note = None

            conn.execute("""
                INSERT OR REPLACE INTO recommendations
                    (recommendation_id, scenario, sku, source_warehouse,
                     destination_warehouse, transfer_quantity, lead_time_days,
                     transfer_cost_aed, expected_unmet_avoided,
                     estimated_net_benefit_aed, explanation, approval_status,
                     decision_timestamp, decided_by, decision_note,
                     created_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                rec["scenario"],
                rec["sku"],
                rec["source_warehouse"],
                rec["destination_warehouse"],
                int(rec["transfer_quantity"]),
                int(rec["lead_time_days"]),
                float(rec["transfer_cost_aed"]),
                float(rec["expected_unmet_avoided"]),
                float(rec["estimated_net_benefit_aed"]),
                rec.get("explanation", ""),
                approval_status,
                decision_timestamp,
                decided_by,
                decision_note,
                datetime.now().isoformat(),
            ))
            conn.commit()
        finally:
            conn.close()
        self._audit("ApprovalAgent", "save_recommendation", "recommendation", rec_id,
                     f"Saved recommendation for {rec['sku']}: {rec['source_warehouse']} -> {rec['destination_warehouse']}")
        return rec_id

    def update_approval_status(self, rec_id: str, status: str,
                               decided_by: str = "user",
                               note: str = "") -> bool:
        """Update approval status. Returns True if updated, False if not found."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT approval_status FROM recommendations WHERE recommendation_id = ?",
                (rec_id,),
            ).fetchone()
            if row is None:
                return False

            old_status = row["approval_status"]

            # Prevent duplicate approvals/rejections
            if old_status == status:
                return False  # Already in this state

            if old_status in ("Approved", "Rejected") and status in ("Approved", "Rejected"):
                # Changing from one final state to another is not allowed
                return False

            ts = datetime.now().isoformat()
            conn.execute("""
                UPDATE recommendations
                SET approval_status = ?,
                    decision_timestamp = ?,
                    decided_by = ?,
                    decision_note = ?
                WHERE recommendation_id = ?
            """, (status, ts, decided_by, note, rec_id))
            conn.commit()
        finally:
            conn.close()

        self._audit(
            "ApprovalAgent", "update_approval",
            "recommendation", rec_id,
            f"Status changed: {old_status} -> {status}" + (f" (note: {note})" if note else ""),
        )
        return True

    def get_recommendation(self, rec_id: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM recommendations WHERE recommendation_id = ?",
                (rec_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_recommendations(self, scenario: Optional[str] = None,
                                status: Optional[str] = None) -> list:
        query = "SELECT * FROM recommendations WHERE 1=1"
        params = []
        if scenario:
            query += " AND scenario = ?"
            params.append(scenario)
        if status:
            query += " AND approval_status = ?"
            params.append(status)
        query += " ORDER BY estimated_net_benefit_aed DESC"
        conn = self._get_conn()
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def clear_recommendations(self, scenario: Optional[str] = None):
        """Clear recommendations (optionally for a specific scenario)."""
        conn = self._get_conn()
        try:
            if scenario:
                conn.execute(
                    "DELETE FROM recommendations WHERE scenario = ?",
                    (scenario,),
                )
            else:
                conn.execute("DELETE FROM recommendations")
            conn.commit()
        finally:
            conn.close()

    # -- Audit log --

    def _audit(self, agent_name: str, action: str,
               entity_type: str = None, entity_id: str = None,
               details: str = "", status: str = "success"):
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO audit_log (timestamp, agent_name, action, entity_type,
                                       entity_id, details, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                agent_name, action, entity_type, entity_id, details, status,
            ))
            conn.commit()
        finally:
            conn.close()

    def get_audit_log(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY log_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # -- Agent message log --

    def log_agent_message(self, agent_name: str, task: str,
                          inputs: dict, outputs: dict,
                          status: str = "success", error: str = None):
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO agent_messages (timestamp, agent_name, task, inputs,
                                            outputs, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                agent_name, task,
                json.dumps(inputs, default=str),
                json.dumps(outputs, default=str),
                status, error,
            ))
            conn.commit()
        finally:
            conn.close()

    def get_agent_messages(self, limit: int = 100) -> list:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM agent_messages ORDER BY message_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def export_agent_log(self, csv_path: str):
        """Export agent message log to CSV."""
        import csv
        messages = self.get_agent_messages(limit=10000)
        if not messages:
            # Write empty CSV with headers
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["message_id", "timestamp", "agent_name", "task",
                                 "inputs", "outputs", "status", "error"])
            return
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "message_id", "timestamp", "agent_name", "task",
                "inputs", "outputs", "status", "error",
            ])
            writer.writeheader()
            for msg in messages:
                writer.writerow(msg)
