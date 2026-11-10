"""P0 linguistic-integrity regression tests (see AHIRANI_LINGUISTIC_REQUIREMENTS.md).

Guarantees under test:
* provider-detected language never changes the declared dialect;
* baseline (Marathi / indic-auto) results stay separate from any Ahirani performance claim;
* provider responses are visible/exportable (internal) without leaking credentials;
* references start empty; STT text is opt-in.
"""
import json
import os
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import baseline
from src.api.app import create_app
from src.baseline import sanitize_provider_response
from src.evaluation.report import ahirani_claim_status, evaluate_samples
from src.services import review
from src.services.evaluation_service import run_evaluation
from src.services.export import export_dataset
from src.services.ingest import ingest_file
from src.services.transcribe import import_transcript, transcribe_clip
from src.storage.db import MIGRATIONS_DIR, Database

STATIC = Path(__file__).resolve().parent.parent / "src" / "api" / "static"
SECRET = "test-key"          # value of GNANI_API_KEY in live_ctx_with_key


def _ui_js():
    """All Studio UI modules concatenated (the code moved from app.js into js/ modules)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted((STATIC / "js").glob("*.js")))


def ingest(ctx, path, **kw):
    return ingest_file(ctx, path, os.path.basename(path), **kw)


@pytest.fixture
def mock_gnani(monkeypatch):
    """Patch the HTTP-level client; the provider reports whatever language we say it detected."""
    state = {"detected": "gu-IN", "extra": {}}

    def fake(self, audio_path, model, language_code):
        body = {"success": True, "request_id": "req-1", "transcript": "some baseline text", "model": model,
                "detected_language_code": state["detected"], "processing_time": 0.2, **state["extra"]}
        return {"data": body, "latency": 0.3}
    monkeypatch.setattr("src.gnani.client.GnaniClient.transcribe", fake)
    return state


# ---------------------------------------------------------------- migration
def test_migration_0002_backfills_roles_and_enforces_check(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript((MIGRATIONS_DIR / "0001_init.sql").read_text())
    con.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    con.execute("INSERT INTO schema_migrations VALUES (1, 'x')")
    con.execute("INSERT INTO sources(id,original_name,stored_path,sha256,created_at) VALUES ('s','n','p','h','t')")
    con.execute("INSERT INTO clips(id,source_id,start_s,end_s,duration_s,path,created_at) VALUES ('c','s',0,1,1,'p','t')")
    for prov in ("gnani", "imported", "demo-mock"):
        con.execute("INSERT INTO transcripts(clip_id,provider,transcript_raw,created_at) VALUES ('c',?,'t','t')", (prov,))
    con.commit(); con.close()

    db = Database(path)
    roles = {r["provider"]: r["experiment_role"] for r in db.query("SELECT provider, experiment_role FROM transcripts")}
    assert roles == {"gnani": "baseline", "imported": "human_import", "demo-mock": "baseline"}
    n_migrations = len(list(MIGRATIONS_DIR.glob("*.sql")))
    assert db.one("SELECT COUNT(*) n FROM schema_migrations")["n"] == n_migrations
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO transcripts(clip_id,provider,transcript_raw,created_at,experiment_role) "
                   "VALUES ('c','gnani','t','t','ahirani_performance')")
    Database(path)  # re-opening is idempotent
    assert db.one("SELECT COUNT(*) n FROM schema_migrations")["n"] == n_migrations


def test_repo_rejects_unknown_role(live_ctx, tone_wav):
    clip = ingest(live_ctx, tone_wav).clips[0]
    with pytest.raises(ValueError):
        live_ctx.repo.add_transcript({"clip_id": clip["id"], "provider": "x", "transcript_raw": "t", "experiment_role": "gold"})


# ---------------------------------------------------------------- experiment_role (req 6)
@pytest.mark.parametrize("code", ["mr-IN", "indic-auto", "gu-IN", "hi-IN"])
def test_every_provider_transcript_is_baseline_whatever_the_setting(live_ctx_with_key, tone_wav, mock_gnani, code):
    clip = ingest(live_ctx_with_key, tone_wav).clips[0]
    t = transcribe_clip(live_ctx_with_key, clip["id"], code)
    assert t["experiment_role"] == "baseline"
    assert t["language_code_requested"] == code


def test_imported_and_demo_roles(live_ctx, demo_ctx, tone_wav, make_tone):
    clip = ingest(live_ctx, tone_wav).clips[0]
    assert import_transcript(live_ctx, clip["id"], "text")["experiment_role"] == "human_import"
    dclip = ingest(demo_ctx, make_tone(333)).clips[0]
    assert transcribe_clip(demo_ctx, dclip["id"])["experiment_role"] == "baseline"


def test_candidate_role_is_never_assigned_automatically():
    assert baseline.role_for_transcript("gnani") == "baseline"
    assert baseline.role_for_transcript("demo-mock") == "baseline"
    assert baseline.role_for_transcript("imported") == "human_import"
    assert baseline.NATIVE_AHIRANI_STT_VERIFIED is False


# ---------------------------------------------------------------- detection never changes declared dialect (req 7)
@pytest.mark.parametrize("detected", ["gu-IN", "mr-IN", "hi-IN", "en-IN", None])
@pytest.mark.parametrize("declared", ["Ahirani", "ahirani", "UNKNOWN"])
def test_provider_detection_never_changes_declared_dialect(live_ctx_with_key, tone_wav, mock_gnani, detected, declared):
    ctx = live_ctx_with_key
    r = ingest(ctx, tone_wav, dialect_label=declared)
    before_source = dict(ctx.repo.get_source(r.source["id"]))
    clip = r.clips[0]
    mock_gnani["detected"] = detected
    t = transcribe_clip(ctx, clip["id"], "indic-auto")
    assert t["detected_language_code"] == detected
    assert ctx.repo.get_source(r.source["id"]) == before_source          # entire source row untouched
    assert ctx.repo.get_clip(clip["id"])["dialect_label"] == declared


def test_detection_cannot_reach_source_update_path(live_ctx_with_key, tone_wav, mock_gnani, monkeypatch):
    ctx = live_ctx_with_key
    r = ingest(ctx, tone_wav, dialect_label="Ahirani")

    def boom(*a, **k):
        raise AssertionError("transcription must not update sources")
    monkeypatch.setattr(ctx.repo, "update_source", boom)
    transcribe_clip(ctx, r.clips[0]["id"], "mr-IN")
    import_transcript(ctx, r.clips[0]["id"], "x", language_code="mr-IN")


def test_detection_via_api_leaves_declared_dialect(live_ctx_with_key, tone_wav, mock_gnani):
    c = TestClient(create_app(live_ctx_with_key))
    with open(tone_wav, "rb") as f:
        up = c.post("/api/sources", files={"file": ("a.wav", f, "audio/wav")}, data={"dialect_label": "Ahirani"}).json()
    cid = up["clips"][0]["id"]
    mock_gnani["detected"] = "gu-IN"
    c.post(f"/api/clips/{cid}/transcribe", json={"language_code": "mr-IN"})
    ws = c.get(f"/api/clips/{cid}").json()
    assert ws["clip"]["dialect_label"] == "Ahirani"
    assert ws["transcripts"][0]["detected_language_code"] == "gu-IN"
    assert c.get("/api/sources").json()[0]["dialect_label"] == "Ahirani"


# ---------------------------------------------------------------- baseline separation (req 8)
def _sample(i, role, code, raw, corrected=None):
    return {"clip_id": f"c{i}", "reference": "a b c d", "raw": raw, "corrected": corrected or raw,
            "experiment_role": role, "provider": "gnani", "language_code_requested": code}


def test_baseline_and_imports_are_reported_in_separate_groups():
    r = evaluate_samples([_sample(1, "baseline", "mr-IN", "a x c d"), _sample(2, "baseline", "indic-auto", "a x x d"),
                          _sample(3, "human_import", "", "a b c d")])
    assert set(r["by_role"]) == {"baseline", "human_import"}
    assert r["by_role"]["baseline"]["n_scored"] == 2
    assert r["by_role"]["baseline"]["language_codes_requested"] == ["indic-auto", "mr-IN"]
    assert r["by_role"]["baseline"]["aggregate"]["before"]["wer"] == 0.375      # (1+2)/8, import excluded
    assert r["by_role"]["human_import"]["aggregate"]["before"]["wer"] == 0.0
    assert r["by_role"]["baseline"]["is_ahirani_performance"] is False
    assert "NOT an Ahirani performance figure" in r["aggregate"]["scope"]


def test_ahirani_claim_is_never_allowed_from_baseline_results():
    r = evaluate_samples([_sample(1, "baseline", "mr-IN", "a b c d")])        # perfect baseline, still no claim
    claim = r["claims"]
    assert claim["ahirani_stt_performance_claim_allowed"] is False
    assert claim["ahirani_stt_performance"] is None
    assert "not been independently verified" in claim["statement"]
    assert claim["baseline_scored_samples"] == 1


def test_candidate_results_alone_do_not_unlock_the_claim(monkeypatch):
    rows = [_sample(1, "candidate", "ahr", "a b c d")]
    assert ahirani_claim_status(evaluate_samples(rows)["by_role"])["ahirani_stt_performance_claim_allowed"] is False
    # Only an explicit verification record (flag) plus candidate-role results can unlock it, and baselines never count.
    monkeypatch.setattr("src.evaluation.report.NATIVE_AHIRANI_STT_VERIFIED", True)
    both = evaluate_samples(rows + [_sample(2, "baseline", "mr-IN", "x x x x")])
    claim = both["claims"]
    assert claim["ahirani_stt_performance_claim_allowed"] is True
    assert claim["ahirani_stt_performance"]["before"]["wer"] == 0.0               # candidate only; baseline 100% not mixed in
    only_baseline = evaluate_samples([_sample(3, "baseline", "mr-IN", "a b c d")])
    assert only_baseline["claims"]["ahirani_stt_performance_claim_allowed"] is False


def test_service_level_evaluation_keeps_baselines_separate(live_ctx_with_key, make_tone, mock_gnani):
    ctx = live_ctx_with_key
    clip = ingest(ctx, make_tone(300)).clips[0]
    transcribe_clip(ctx, clip["id"], "mr-IN")
    review.verify_reference(ctx, clip["id"], "some baseline text", "dana", stt_viewed=False)
    r = run_evaluation(ctx)
    assert list(r["by_role"]) == ["baseline"]
    assert r["by_role"]["baseline"]["language_codes_requested"] == ["mr-IN"]
    assert r["claims"]["ahirani_stt_performance_claim_allowed"] is False
    assert r["samples"][0]["experiment_role"] == "baseline"
    assert ctx.repo.list_eval_runs()[0]["results"]["claims"]["ahirani_stt_performance"] is None


def test_api_evaluate_exposes_claims_block(demo_ctx):
    from src.services.demo import seed_demo
    seed_demo(demo_ctx)
    c = TestClient(create_app(demo_ctx))
    ev = c.post("/api/evaluate", json={}).json()
    assert ev["claims"]["ahirani_stt_performance_claim_allowed"] is False
    assert set(ev["by_role"]) == {"baseline"}
    assert ev["warnings"][0].startswith("DEMO DATA")


def test_export_manifest_and_card_carry_the_baseline_statement(live_ctx, tone_wav):
    ingest(live_ctx, tone_wav, permission_status="granted", permitted_usage="private_research")
    out = export_dataset(live_ctx, "internal", require_verified=False)
    assert "not been independently verified" in out["manifest"]["stt_results_note"]
    with zipfile.ZipFile(out["zip_path"]) as z:
        assert "not been independently verified" in z.read("DATASET_CARD.md").decode()


# ---------------------------------------------------------------- workspace exposure (req 3)
def test_workspace_exposes_detected_language_role_and_provider_response(live_ctx_with_key, tone_wav, mock_gnani):
    ctx = live_ctx_with_key
    clip = ingest(ctx, tone_wav, dialect_label="Ahirani").clips[0]
    transcribe_clip(ctx, clip["id"], "mr-IN")
    import_transcript(ctx, clip["id"], "imported text")
    ws = review.clip_workspace(ctx, clip["id"])
    t, imp = ws["transcripts"]
    assert t["detected_language_code"] == "gu-IN" and t["language_code_requested"] == "mr-IN"
    assert t["provider_response"]["detected_language_code"] == "gu-IN" and t["provider_response"]["request_id"] == "req-1"
    assert t["experiment_role"] == "baseline" and "not Ahirani" in t["experiment_role_label"]
    assert "raw_response" not in t
    assert imp["provider_response"] is None and imp["experiment_role"] == "human_import"
    assert ws["clip"]["dialect_label"] == "Ahirani"


def test_about_labels_mr_in_and_indic_auto_as_baseline_settings(live_ctx):
    a = TestClient(create_app(live_ctx)).get("/api/about").json()
    assert set(a["baseline_settings"]) == {"indic-auto", "mr-IN"}
    assert all("baseline" in d.lower() for d in a["baseline_settings"].values())
    assert "not been independently verified" in a["native_support_statement"]


# ---------------------------------------------------------------- sanitiser + export (req 4)
def test_sanitizer_redacts_credentials_and_config():
    body = {"transcript": "ok", "api_key": "abc", "nested": {"Authorization": "Bearer zzz", "headers": {"X-API-Key-ID": "k"},
            "note": f"leaked {SECRET} here"}, "list": [{"token": "t"}, f"{SECRET}"], "request_id": "r"}
    out = sanitize_provider_response(body, [SECRET])
    text = json.dumps(out)
    for leaked in ("abc", "zzz", SECRET, '"k"'):
        assert leaked not in text
    assert out["transcript"] == "ok" and out["request_id"] == "r"
    assert body["api_key"] == "abc"                                           # input not mutated
    assert sanitize_provider_response(json.dumps(body), [SECRET])["api_key"] == "[redacted]"
    assert sanitize_provider_response(None) is None


def test_internal_export_includes_sanitised_provider_response_only(live_ctx_with_key, tone_wav, mock_gnani):
    ctx = live_ctx_with_key
    mock_gnani["extra"] = {"api_key": "hunter2-xyz", "debug": f"auth with {SECRET}", "headers": {"X-API-Key-ID": SECRET}}
    r = ingest(ctx, tone_wav, permission_status="granted", permitted_usage="public_release")
    clip = r.clips[0]
    transcribe_clip(ctx, clip["id"], "indic-auto")
    review.verify_reference(ctx, clip["id"], "ref text", "dana")

    internal = export_dataset(ctx, "internal")
    public = export_dataset(ctx, "public")
    with zipfile.ZipFile(internal["zip_path"]) as z:
        rec = json.loads(z.read("metadata.jsonl").decode().splitlines()[0])
        tr = rec["transcripts"][0]
        assert tr["experiment_role"] == "baseline"
        assert tr["provider_response"]["detected_language_code"] == "gu-IN"
        assert tr["provider_response"]["request_id"] == "req-1"
        everything = b"".join(z.read(n) for n in z.namelist() if not n.endswith(".wav")).decode()
        for leaked in (SECRET, "hunter2-xyz", "X-API-Key-ID", "GNANI_API_KEY"):
            assert leaked not in everything
        assert internal["manifest"]["provider_responses_included"] is True
    with zipfile.ZipFile(public["zip_path"]) as z:
        rec = json.loads(z.read("metadata.jsonl").decode().splitlines()[0])
        assert "provider_response" not in rec["transcripts"][0]
        assert rec["transcripts"][0]["experiment_role"] == "baseline"
        assert public["manifest"]["provider_responses_included"] is False


def test_export_permission_controls_unchanged_with_provider_responses(live_ctx_with_key, make_tone, mock_gnani):
    ctx = live_ctx_with_key
    for freq, perm, use in [(300, "UNKNOWN", "UNKNOWN"), (350, "denied", "UNKNOWN"), (400, "granted", "private_research")]:
        clip = ingest(ctx, make_tone(freq), permission_status=perm, permitted_usage=use).clips[0]
        if perm != "denied":
            transcribe_clip(ctx, clip["id"], "mr-IN")
        review.verify_reference(ctx, clip["id"], "ref", "dana")
    internal = export_dataset(ctx, "internal")
    assert internal["manifest"]["clip_count"] == 1                            # unknown and denied still excluded
    assert export_dataset(ctx, "public")["manifest"]["clip_count"] == 0       # not public_release
    with pytest.raises(Exception):
        export_dataset(ctx, "public", include_unknown_internal=True)


# ---------------------------------------------------------------- references (req 2) and UI source (req 1, 5)
def test_verify_records_whether_stt_was_viewed_without_schema_change(live_ctx, tone_wav):
    clip = ingest(live_ctx, tone_wav).clips[0]
    review.verify_reference(live_ctx, clip["id"], "independent text", "dana", stt_viewed=False)
    review.verify_reference(live_ctx, clip["id"], "copied text", "dana", stt_viewed=True)
    details = [json.loads(a["detail"]) for a in live_ctx.repo.list_audit() if a["action"] == "verify_reference"]
    assert [d["stt_viewed"] for d in reversed(details)] == [False, True]


def test_verify_api_accepts_stt_viewed_and_remains_backward_compatible(live_ctx, tone_wav):
    c = TestClient(create_app(live_ctx))
    cid = ingest(live_ctx, tone_wav).clips[0]["id"]
    assert c.post(f"/api/clips/{cid}/verify", json={"reference": "r", "reviewer": "x"}).status_code == 200   # old payload
    assert c.post(f"/api/clips/{cid}/verify", json={"reference": "r2", "reviewer": "x", "stt_viewed": True}).status_code == 200


def test_ui_has_no_hardcoded_marathi_language_tag():
    js = _ui_js()
    html = (STATIC / "app.html").read_text(encoding="utf-8")
    assert not re.search(r"lang\s*[:=]\s*[\"']mr", js)
    assert not re.search(r"lang\s*[:=]\s*[\"'](mr|gu|hi)", html.replace('<html lang="en">', ""))
    assert '<html lang="en">' in html                                          # UI chrome language only


def test_ui_reference_box_is_empty_by_default_with_explicit_stt_opt_in():
    js = _ui_js()
    ref = js[js.index("function referenceCard"):js.index("// ---------- lexicon")]
    assert 'clip.reference_transcript || ""' in ref                             # empty unless a human already verified one
    assert "last.corrected_text :" not in ref and "pre-filled" not in ref
    assert "Show STT transcript (optional)" in ref and "stt_viewed: sttViewed" in ref
    assert "Copy original STT into the box" in ref                              # explicit opt-in copy


def test_ui_labels_language_codes_as_baseline_experiment_settings():
    js = _ui_js()
    assert "STT baseline experiment setting" in js
    assert "baseline experiment settings, not Ahirani" in js
    assert "Run STT baseline" in js
    assert "Transcribe with Gnani Prisma" not in js
    assert '"gu-IN", "hi-IN"' not in js                                         # no longer offered as suggestions
    assert "Ahirani performance claim: not allowed" in js
