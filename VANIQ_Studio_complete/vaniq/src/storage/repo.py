"""Data-access layer. All SQL lives here; services never touch the connection directly."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.baseline import EXPERIMENT_ROLES
from src.storage.db import Database

PERMISSION_STATUSES = ("UNKNOWN", "granted", "denied")
PERMITTED_USAGES = ("UNKNOWN", "private_research", "internal_training", "public_release")
REVIEW_STATUSES = ("needs_review", "in_review", "verified", "rejected")
SUGGESTION_STATUSES = ("pending", "accepted", "rejected", "modified")
LEXICON_STATUSES = ("demo", "candidate", "verified")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ---- audit -------------------------------------------------------------------------
    def audit(self, actor: str, action: str, entity: str, entity_id: Any, detail: Optional[dict] = None) -> None:
        self.db.execute(
            "INSERT INTO audit_log(ts, actor, action, entity, entity_id, detail) VALUES (?,?,?,?,?,?)",
            (now(), actor or "unknown", action, entity, str(entity_id), json.dumps(detail or {}, ensure_ascii=False)))

    def list_audit(self, limit: int = 100) -> list[dict]:
        return self.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

    # ---- sources -----------------------------------------------------------------------
    def upsert_source(self, rec: dict) -> dict:
        existing = self.get_source(rec["id"])
        if existing:
            return existing
        cols = ["id", "original_name", "stored_path", "normalized_path", "sha256", "source_url", "speaker_id",
                "dialect_label", "permission_status", "permitted_usage", "consent_notes", "duration_s",
                "segmentation_status", "is_demo", "created_at"]
        rec = {**rec, "created_at": rec.get("created_at") or now()}
        self.db.execute(f"INSERT INTO sources({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        tuple(rec.get(c) for c in cols))
        return self.get_source(rec["id"])

    def get_source(self, source_id: str) -> Optional[dict]:
        return self.db.one("SELECT * FROM sources WHERE id=?", (source_id,))

    def list_sources(self) -> list[dict]:
        return self.db.query(
            "SELECT s.*, (SELECT COUNT(*) FROM clips c WHERE c.source_id=s.id) AS clip_count "
            "FROM sources s ORDER BY s.created_at DESC")

    def update_source(self, source_id: str, fields: dict, actor: str = "system") -> Optional[dict]:
        allowed = {"source_url", "speaker_id", "dialect_label", "permission_status", "permitted_usage",
                   "consent_notes", "segmentation_status", "duration_s", "normalized_path"}
        fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not fields:
            return self.get_source(source_id)
        sets = ",".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE sources SET {sets} WHERE id=?", (*fields.values(), source_id))
        self.audit(actor, "update_source", "source", source_id, fields)
        return self.get_source(source_id)

    # ---- clips -------------------------------------------------------------------------
    def upsert_clip(self, rec: dict) -> dict:
        existing = self.get_clip(rec["id"])
        if existing:
            return existing
        cols = ["id", "source_id", "start_s", "end_s", "duration_s", "path", "rms_dbfs", "peak_dbfs",
                "clipping_count", "silence_ratio", "quality_flags", "review_status", "created_at"]
        rec = {"review_status": "needs_review", **rec, "created_at": rec.get("created_at") or now()}
        rec["quality_flags"] = json.dumps(rec.get("quality_flags") or [])
        self.db.execute(f"INSERT INTO clips({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        tuple(rec.get(c) for c in cols))
        return self.get_clip(rec["id"])

    _CLIP_SELECT = (
        "SELECT c.*, s.speaker_id, s.dialect_label, s.permission_status, s.permitted_usage, s.is_demo, "
        "s.original_name AS source_name, s.consent_notes, "
        "(SELECT COUNT(*) FROM transcripts t WHERE t.clip_id=c.id) AS transcript_count "
        "FROM clips c JOIN sources s ON s.id=c.source_id ")

    def get_clip(self, clip_id: str) -> Optional[dict]:
        row = self.db.one(self._CLIP_SELECT + "WHERE c.id=?", (clip_id,))
        return _decode_clip(row)

    def list_clips(self, review_status: Optional[str] = None, source_id: Optional[str] = None) -> list[dict]:
        sql, params, where = self._CLIP_SELECT, [], []
        if review_status:
            where.append("c.review_status=?"); params.append(review_status)
        if source_id:
            where.append("c.source_id=?"); params.append(source_id)
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY c.created_at DESC, c.start_s ASC"
        return [_decode_clip(r) for r in self.db.query(sql, tuple(params))]

    def set_review_status(self, clip_id: str, status: str, actor: str) -> None:
        if status not in REVIEW_STATUSES:
            raise ValueError(f"Invalid review status: {status}")
        self.db.execute("UPDATE clips SET review_status=? WHERE id=?", (status, clip_id))
        self.audit(actor, "set_review_status", "clip", clip_id, {"status": status})

    def set_reference(self, clip_id: str, text: str, script: str, actor: str, stt_viewed: Optional[bool] = None) -> None:
        self.db.execute(
            "UPDATE clips SET reference_transcript=?, reference_script=?, reference_by=?, reference_at=?, "
            "review_status='verified' WHERE id=?", (text, script, actor, now(), clip_id))
        self.audit(actor, "verify_reference", "clip", clip_id, {"reference": text, "stt_viewed": stt_viewed})

    def clear_reference(self, clip_id: str, actor: str) -> None:
        self.db.execute(
            "UPDATE clips SET reference_transcript=NULL, reference_script=NULL, reference_by=NULL, "
            "reference_at=NULL, review_status='in_review' WHERE id=?", (clip_id,))
        self.audit(actor, "clear_reference", "clip", clip_id)

    def set_clip_notes(self, clip_id: str, notes: str) -> None:
        self.db.execute("UPDATE clips SET notes=? WHERE id=?", (notes, clip_id))

    # ---- transcripts -------------------------------------------------------------------
    def add_transcript(self, rec: dict) -> dict:
        cols = ["clip_id", "provider", "provider_label", "is_synthetic", "model", "language_code_requested",
                "detected_language_code", "request_id", "transcript_raw", "script", "latency_s", "raw_response",
                "experiment_role", "created_at"]
        rec = {"provider_label": "", "is_synthetic": 0, "experiment_role": "baseline", **rec, "created_at": now()}
        if rec["experiment_role"] not in EXPERIMENT_ROLES:
            raise ValueError(f"Invalid experiment_role: {rec['experiment_role']}")
        if isinstance(rec.get("raw_response"), (dict, list)):
            rec["raw_response"] = json.dumps(rec["raw_response"], ensure_ascii=False)
        tid = self.db.execute(f"INSERT INTO transcripts({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                              tuple(rec.get(c) for c in cols))
        return self.get_transcript(tid)

    def get_transcript(self, transcript_id: int) -> Optional[dict]:
        return self.db.one("SELECT * FROM transcripts WHERE id=?", (transcript_id,))

    def list_transcripts(self, clip_id: str) -> list[dict]:
        return self.db.query("SELECT * FROM transcripts WHERE clip_id=? ORDER BY id", (clip_id,))

    # ---- suggestions -------------------------------------------------------------------
    def add_suggestions(self, transcript_id: int, suggestions: list[dict]) -> list[int]:
        ids = []
        for s in suggestions:
            ids.append(self.db.execute(
                "INSERT INTO suggestions(transcript_id,start_char,end_char,original,replacement,kind,backend,"
                "rule_id,confidence,confidence_basis,explanation,uncertain,status,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (transcript_id, s["start_char"], s["end_char"], s["original"], s["replacement"], s["kind"],
                 s["backend"], s.get("rule_id"), s.get("confidence"), s.get("confidence_basis", ""),
                 s.get("explanation", ""), 1 if s.get("uncertain", True) else 0, s.get("status", "pending"), now())))
        return ids

    def clear_pending_suggestions(self, transcript_id: int) -> None:
        self.db.execute("DELETE FROM suggestions WHERE transcript_id=? AND status='pending' AND backend!='human'",
                        (transcript_id,))

    def list_suggestions(self, transcript_id: int) -> list[dict]:
        return self.db.query("SELECT * FROM suggestions WHERE transcript_id=? ORDER BY start_char, id",
                             (transcript_id,))

    def get_suggestion(self, suggestion_id: int) -> Optional[dict]:
        return self.db.one("SELECT * FROM suggestions WHERE id=?", (suggestion_id,))

    def decide_suggestion(self, suggestion_id: int, status: str, actor: str,
                          final_replacement: Optional[str] = None) -> dict:
        if status not in SUGGESTION_STATUSES:
            raise ValueError(f"Invalid suggestion status: {status}")
        self.db.execute(
            "UPDATE suggestions SET status=?, final_replacement=?, decided_by=?, decided_at=? WHERE id=?",
            (status, final_replacement, actor if status != "pending" else None,
             now() if status != "pending" else None, suggestion_id))
        self.audit(actor, f"suggestion_{status}", "suggestion", suggestion_id, {"final": final_replacement})
        return self.get_suggestion(suggestion_id)

    def delete_suggestion(self, suggestion_id: int) -> None:
        self.db.execute("DELETE FROM suggestions WHERE id=?", (suggestion_id,))

    def suggestion_stats_by_rule(self) -> dict[str, dict]:
        rows = self.db.query(
            "SELECT rule_id, status, COUNT(*) AS n FROM suggestions "
            "WHERE rule_id IS NOT NULL AND status!='pending' GROUP BY rule_id, status")
        out: dict[str, dict] = {}
        for r in rows:
            d = out.setdefault(r["rule_id"], {"accepted": 0, "rejected": 0, "modified": 0})
            d[r["status"]] = r["n"]
        return out

    # ---- lexicon -----------------------------------------------------------------------
    def add_lexicon_entry(self, rec: dict, actor: str = "system") -> dict:
        rec = {"kind": "lexical", "context_prev": "", "context_next": "", "status": "candidate",
               "provenance": "", "notes": "", "enabled": 1, "is_demo": 0, **rec, "created_at": now()}
        lid = self.db.execute(
            "INSERT INTO lexicon_entries(source_form,target_form,kind,context_prev,context_next,status,provenance,"
            "notes,enabled,is_demo,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["source_form"], rec["target_form"], rec["kind"], rec["context_prev"], rec["context_next"],
             rec["status"], rec["provenance"], rec["notes"], rec["enabled"], rec["is_demo"], actor, rec["created_at"]))
        self.audit(actor, "add_lexicon_entry", "lexicon", lid, {"source": rec["source_form"], "target": rec["target_form"],
                                                              "status": rec["status"]})
        return self.get_lexicon_entry(lid)

    def get_lexicon_entry(self, lid: int) -> Optional[dict]:
        return self.db.one("SELECT * FROM lexicon_entries WHERE id=?", (lid,))

    def list_lexicon(self, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM lexicon_entries"
        if enabled_only:
            sql += " WHERE enabled=1"
        return self.db.query(sql + " ORDER BY id")

    def update_lexicon_entry(self, lid: int, fields: dict, actor: str) -> Optional[dict]:
        allowed = {"source_form", "target_form", "kind", "context_prev", "context_next", "status", "provenance",
                   "notes", "enabled"}
        fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self.db.execute(f"UPDATE lexicon_entries SET {sets} WHERE id=?", (*fields.values(), lid))
            self.audit(actor, "update_lexicon_entry", "lexicon", lid, fields)
        return self.get_lexicon_entry(lid)

    def delete_lexicon_entry(self, lid: int, actor: str) -> None:
        self.db.execute("DELETE FROM lexicon_entries WHERE id=?", (lid,))
        self.audit(actor, "delete_lexicon_entry", "lexicon", lid)

    # ---- eval --------------------------------------------------------------------------
    def save_eval_run(self, params: dict, results: dict) -> int:
        return self.db.execute("INSERT INTO eval_runs(created_at, params, results) VALUES (?,?,?)",
                               (now(), json.dumps(params), json.dumps(results, ensure_ascii=False)))

    def list_eval_runs(self, limit: int = 20) -> list[dict]:
        rows = self.db.query("SELECT * FROM eval_runs ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["params"] = json.loads(r["params"]); r["results"] = json.loads(r["results"])
        return rows

    # ---- dashboard ---------------------------------------------------------------------
    def counts(self) -> dict:
        q = self.db.one
        return {
            "sources": q("SELECT COUNT(*) n FROM sources")["n"],
            "clips": q("SELECT COUNT(*) n FROM clips")["n"],
            "transcripts": q("SELECT COUNT(*) n FROM transcripts WHERE is_synthetic=0")["n"],
            "synthetic_transcripts": q("SELECT COUNT(*) n FROM transcripts WHERE is_synthetic=1")["n"],
            "verified_clips": q("SELECT COUNT(*) n FROM clips WHERE review_status='verified'")["n"],
            "pending_suggestions": q("SELECT COUNT(*) n FROM suggestions WHERE status='pending'")["n"],
            "decided_suggestions": q("SELECT COUNT(*) n FROM suggestions WHERE status!='pending'")["n"],
            "lexicon_entries": q("SELECT COUNT(*) n FROM lexicon_entries WHERE enabled=1")["n"],
            "unknown_permission_clips": q(
                "SELECT COUNT(*) n FROM clips c JOIN sources s ON s.id=c.source_id "
                "WHERE s.permission_status!='granted' OR s.permitted_usage='UNKNOWN'")["n"],
            "review_status": {r["review_status"]: r["n"] for r in self.db.query(
                "SELECT review_status, COUNT(*) n FROM clips GROUP BY review_status")},
        }


    # ---- agent runs ------------------------------------------------------------------
    def create_agent_run(self, actor: str, message: str, mode: str, status: str, context: dict, steps: list, note: str = "") -> dict:
        rid = uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT INTO agent_runs(id,created_at,actor,message,mode,status,context,steps,note) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, now(), actor, message[:2000], mode, status, json.dumps(context), json.dumps(steps, ensure_ascii=False), note))
        return self.get_agent_run(rid)

    def get_agent_run(self, rid: str) -> Optional[dict]:
        row = self.db.one("SELECT * FROM agent_runs WHERE id=?", (rid,))
        return _decode_json(row, ("context", "steps"))

    def list_agent_runs(self, limit: int = 30) -> list[dict]:
        rows = self.db.query("SELECT * FROM agent_runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
        return [_decode_json(r, ("context", "steps")) for r in rows]

    def update_agent_run(self, rid: str, **fields) -> None:
        allowed = {"status", "steps", "note", "approved_by", "approved_at", "finished_at"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(k)
            sets.append(f"{k}=?"); vals.append(json.dumps(v, ensure_ascii=False) if k == "steps" else v)
        self.db.execute(f"UPDATE agent_runs SET {','.join(sets)} WHERE id=?", (*vals, rid))

    def transition_run(self, table: str, rid: str, expected: str, new: str) -> bool:
        """Atomic status change; returns False if the run was not in the expected state (prevents double execution)."""
        if table not in ("agent_runs", "workflow_runs"):
            raise ValueError(table)
        with self.db._lock:
            cur = self.db._conn.execute(f"UPDATE {table} SET status=? WHERE id=? AND status=?", (new, rid, expected))
            return cur.rowcount == 1

    # ---- workflows -------------------------------------------------------------------
    def save_workflow(self, wid: Optional[str], name: str, category: str, description: str, graph: dict, is_template: bool = False) -> dict:
        t = now()
        if wid and self.get_workflow(wid):
            self.db.execute("UPDATE workflows SET name=?,category=?,description=?,graph=?,updated_at=? WHERE id=?",
                            (name, category, description, json.dumps(graph), t, wid))
        else:
            wid = wid or uuid.uuid4().hex[:10]
            self.db.execute(
                "INSERT INTO workflows(id,name,category,description,graph,is_template,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (wid, name, category, description, json.dumps(graph), 1 if is_template else 0, t, t))
        return self.get_workflow(wid)

    def get_workflow(self, wid: str) -> Optional[dict]:
        return _decode_json(self.db.one("SELECT * FROM workflows WHERE id=?", (wid,)), ("graph",))

    def list_workflows(self) -> list[dict]:
        return [_decode_json(r, ("graph",)) for r in self.db.query("SELECT * FROM workflows ORDER BY is_template DESC, updated_at DESC")]

    def delete_workflow(self, wid: str) -> None:
        self.db.execute("DELETE FROM workflows WHERE id=? AND is_template=0", (wid,))

    def create_workflow_run(self, wid: str, actor: str, status: str, graph: dict) -> dict:
        rid = uuid.uuid4().hex[:12]
        states = {n["id"]: {"status": "pending"} for n in graph["nodes"]}
        self.db.execute("INSERT INTO workflow_runs(id,workflow_id,created_at,actor,status,graph,node_states) VALUES (?,?,?,?,?,?,?)",
                        (rid, wid, now(), actor, status, json.dumps(graph), json.dumps(states)))
        return self.get_workflow_run(rid)

    def get_workflow_run(self, rid: str) -> Optional[dict]:
        return _decode_json(self.db.one("SELECT * FROM workflow_runs WHERE id=?", (rid,)), ("graph", "node_states"))

    def list_workflow_runs(self, wid: Optional[str] = None, limit: int = 30) -> list[dict]:
        sql, params = "SELECT * FROM workflow_runs", []
        if wid:
            sql += " WHERE workflow_id=?"; params.append(wid)
        rows = self.db.query(sql + " ORDER BY created_at DESC, rowid DESC LIMIT ?", (*params, limit))
        return [_decode_json(r, ("graph", "node_states")) for r in rows]

    def update_workflow_run(self, rid: str, **fields) -> None:
        allowed = {"status", "node_states", "approved_by", "approved_at", "finished_at", "error"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(k)
            sets.append(f"{k}=?"); vals.append(json.dumps(v, ensure_ascii=False) if k == "node_states" else v)
        self.db.execute(f"UPDATE workflow_runs SET {','.join(sets)} WHERE id=?", (*vals, rid))

    # ---- knowledge -------------------------------------------------------------------
    def add_knowledge(self, title: str, kind: str, body: str, provenance: str, actor: str) -> dict:
        t = now()
        kid = self.db.execute(
            "INSERT INTO knowledge_items(title,kind,body,status,provenance,version,created_by,updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (title, kind, body, "draft", provenance, 1, actor, t, t))
        self.db.execute("INSERT INTO knowledge_versions(item_id,version,title,body,edited_by,edited_at) VALUES (?,?,?,?,?,?)",
                        (kid, 1, title, body, actor, t))
        self.audit(actor, "knowledge_create", "knowledge", kid, {"title": title})
        return self.get_knowledge(kid)

    def get_knowledge(self, kid: int) -> Optional[dict]:
        return self.db.one("SELECT * FROM knowledge_items WHERE id=?", (kid,))

    def list_knowledge(self, status: Optional[str] = None) -> list[dict]:
        if status:
            return self.db.query("SELECT * FROM knowledge_items WHERE status=? ORDER BY updated_at DESC", (status,))
        return self.db.query("SELECT * FROM knowledge_items ORDER BY updated_at DESC")

    def edit_knowledge(self, kid: int, title: str, body: str, actor: str) -> dict:
        cur = self.get_knowledge(kid)
        v, t = cur["version"] + 1, now()
        # Editing always returns the item to draft: approved text is never silently changed.
        self.db.execute("UPDATE knowledge_items SET title=?,body=?,version=?,status='draft',approved_by=NULL,approved_at=NULL,updated_at=? WHERE id=?",
                        (title, body, v, t, kid))
        self.db.execute("INSERT INTO knowledge_versions(item_id,version,title,body,edited_by,edited_at) VALUES (?,?,?,?,?,?)",
                        (kid, v, title, body, actor, t))
        self.audit(actor, "knowledge_edit", "knowledge", kid, {"version": v})
        return self.get_knowledge(kid)

    def approve_knowledge(self, kid: int, actor: str) -> dict:
        self.db.execute("UPDATE knowledge_items SET status='approved', approved_by=?, approved_at=? WHERE id=?", (actor, now(), kid))
        self.audit(actor, "knowledge_approve", "knowledge", kid)
        return self.get_knowledge(kid)

    def knowledge_versions(self, kid: int) -> list[dict]:
        return self.db.query("SELECT * FROM knowledge_versions WHERE item_id=? ORDER BY version DESC", (kid,))

    def delete_knowledge(self, kid: int, actor: str) -> None:
        self.db.execute("DELETE FROM knowledge_items WHERE id=?", (kid,))
        self.audit(actor, "knowledge_delete", "knowledge", kid)


def _decode_json(row: Optional[dict], keys: tuple) -> Optional[dict]:
    if row is None:
        return None
    for k in keys:
        try:
            row[k] = json.loads(row[k]) if isinstance(row.get(k), str) else row.get(k)
        except ValueError:
            row[k] = None
    return row


def _decode_clip(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    try:
        row["quality_flags"] = json.loads(row.get("quality_flags") or "[]")
    except (TypeError, ValueError):
        row["quality_flags"] = []
    return row
