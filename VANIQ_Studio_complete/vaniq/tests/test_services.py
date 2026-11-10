import os

import pytest

from src.services import review
from src.services.errors import ServiceError
from src.services.evaluation_service import run_evaluation
from src.services.export import export_dataset
from src.services.ingest import ingest_file
from src.services.transcribe import import_transcript, propose_corrections, transcribe_clip
from src.stt import STTNotConfigured


def ingest(ctx, path, **kw):
    return ingest_file(ctx, path, os.path.basename(path), **kw)


def add_lex(ctx, s, t, **kw):
    return ctx.repo.add_lexicon_entry({"source_form": s, "target_form": t, **kw})


def test_ingest_creates_clips_with_unknown_provenance(live_ctx, tone_wav):
    r = ingest(live_ctx, tone_wav)
    assert r.segmentation_status == "success" and len(r.clips) == 2
    assert r.source["permission_status"] == "UNKNOWN" and r.source["speaker_id"] == "UNKNOWN"
    assert all(os.path.isfile(c["path"]) for c in r.clips)
    assert r.clips[0]["review_status"] == "needs_review"


def test_ingest_is_idempotent(live_ctx, tone_wav):
    a, b = ingest(live_ctx, tone_wav), ingest(live_ctx, tone_wav)
    assert b.duplicate and len(live_ctx.repo.list_clips()) == len(a.clips)


def test_ingest_rejects_bad_inputs(live_ctx, tmp_path):
    bad = tmp_path / "x.txt"; bad.write_text("hi")
    with pytest.raises(ServiceError) as e:
        ingest(live_ctx, str(bad)); assert e.value.code == "unsupported_type"
    garbage = tmp_path / "g.wav"; garbage.write_bytes(b"not audio at all" * 10)
    with pytest.raises(ServiceError) as e2:
        ingest(live_ctx, str(garbage))
    assert e2.value.code == "bad_audio"
    empty = tmp_path / "e.wav"; empty.write_bytes(b"")
    with pytest.raises(ServiceError) as e3:
        ingest(live_ctx, str(empty))
    assert e3.value.code == "empty_file"


def test_ingest_rejects_inconsistent_permission(live_ctx, tone_wav):
    with pytest.raises(ServiceError):
        ingest(live_ctx, tone_wav, permission_status="UNKNOWN", permitted_usage="public_release")
    with pytest.raises(ServiceError):
        ingest(live_ctx, tone_wav, permission_status="maybe")


def test_silent_audio_creates_no_clips(live_ctx, tmp_path):
    import numpy as np
    from scipy.io import wavfile
    p = tmp_path / "silence.wav"; wavfile.write(p, 16000, np.zeros(16000, dtype=np.int16))
    r = ingest(live_ctx, str(p))
    assert r.segmentation_status == "no_speech" and r.clips == []


def test_live_mode_without_key_never_fakes_transcription(live_ctx, tone_wav):
    clip = ingest(live_ctx, tone_wav).clips[0]
    with pytest.raises(ServiceError) as e:
        transcribe_clip(live_ctx, clip["id"])
    assert e.value.code == "stt_not_configured" and e.value.status == 503
    assert live_ctx.repo.list_transcripts(clip["id"]) == []


def test_live_transcription_with_mocked_gnani(live_ctx_with_key, tone_wav, monkeypatch):
    ctx = live_ctx_with_key
    clip = ingest(ctx, tone_wav).clips[0]
    payload = {"success": True, "request_id": "r1", "transcript": "dform1 text", "model": "prisma-v3.0",
               "detected_language_code": "mr-IN"}
    monkeypatch.setattr("src.gnani.client.GnaniClient.transcribe", lambda self, p, model, language_code: {"data": payload, "latency": 0.5})
    add_lex(ctx, "dform1", "sform1", status="candidate")
    t = transcribe_clip(ctx, clip["id"], "mr-IN")
    assert t["provider"] == "gnani" and not t["is_synthetic"] and t["transcript_raw"] == "dform1 text"
    assert t["detected_language_code"] == "mr-IN" and t["request_id"] == "r1"
    assert len(ctx.repo.list_suggestions(t["id"])) == 1


def test_denied_permission_blocks_stt(live_ctx_with_key, tone_wav):
    clip = ingest(live_ctx_with_key, tone_wav, permission_status="denied").clips[0]
    with pytest.raises(ServiceError) as e:
        transcribe_clip(live_ctx_with_key, clip["id"])
    assert e.value.code == "permission_denied"


def test_bad_language_code_rejected(demo_ctx, tone_wav):
    clip = ingest(demo_ctx, tone_wav).clips[0]
    with pytest.raises(ServiceError):
        transcribe_clip(demo_ctx, clip["id"], "../evil")


def test_demo_transcript_is_flagged_synthetic(demo_ctx, tone_wav):
    clip = ingest(demo_ctx, tone_wav).clips[0]
    t = transcribe_clip(demo_ctx, clip["id"])
    assert t["is_synthetic"] == 1 and t["provider"] == "demo-mock"


def test_import_transcript_verbatim_and_labelled(live_ctx, tone_wav):
    clip = ingest(live_ctx, tone_wav).clips[0]
    t = import_transcript(live_ctx, clip["id"], "  raw  text  ", label="pilot")
    assert t["provider"] == "imported" and t["provider_label"] == "pilot" and t["transcript_raw"] == "raw  text"
    with pytest.raises(ServiceError):
        import_transcript(live_ctx, clip["id"], "   ")


def test_review_flow_raw_never_changes_and_decisions_recorded(live_ctx, tone_wav):
    ctx = live_ctx
    clip = ingest(ctx, tone_wav).clips[0]
    add_lex(ctx, "dform1", "sform1", status="candidate")
    t = import_transcript(ctx, clip["id"], "a dform1 b")
    s = ctx.repo.list_suggestions(t["id"])[0]
    ws = review.clip_workspace(ctx, clip["id"])["transcripts"][0]
    assert ws["corrected_text"] == "a dform1 b" and ws["preview_if_all_accepted"] == "a sform1 b"
    review.decide(ctx, s["id"], "accepted", "alice")
    ws = review.clip_workspace(ctx, clip["id"])["transcripts"][0]
    assert ws["corrected_text"] == "a sform1 b" and ws["transcript_raw"] == "a dform1 b"
    assert ctx.repo.get_clip(clip["id"])["review_status"] == "in_review"
    review.decide(ctx, s["id"], "modified", "alice", "custom")
    assert review.clip_workspace(ctx, clip["id"])["transcripts"][0]["corrected_text"] == "a custom b"
    with pytest.raises(ServiceError):
        review.decide(ctx, s["id"], "modified", "alice", "")
    assert any(a["actor"] == "alice" for a in ctx.repo.list_audit())


def test_rerun_suggestions_preserves_human_decisions(live_ctx, tone_wav):
    ctx = live_ctx
    clip = ingest(ctx, tone_wav).clips[0]
    add_lex(ctx, "dform1", "sform1")
    t = import_transcript(ctx, clip["id"], "dform1")
    review.decide(ctx, ctx.repo.list_suggestions(t["id"])[0]["id"], "rejected", "bob")
    propose_corrections(ctx, t["id"])
    sugg = ctx.repo.list_suggestions(t["id"])
    assert len(sugg) == 1 and sugg[0]["status"] == "rejected"


def test_manual_correction_and_span_checks(live_ctx, tone_wav):
    ctx = live_ctx
    clip = ingest(ctx, tone_wav).clips[0]
    t = import_transcript(ctx, clip["id"], "hello world")
    s = review.add_manual_correction(ctx, t["id"], 6, 11, "there", "carol", expected_original="world")
    assert s["status"] == "accepted" and s["backend"] == "human"
    assert review.clip_workspace(ctx, clip["id"])["transcripts"][0]["corrected_text"] == "hello there"
    for args in [(0, 99, "x"), (5, 5, "x"), (0, 2, " ")]:
        with pytest.raises(ServiceError):
            review.add_manual_correction(ctx, t["id"], *args, "carol")
    with pytest.raises(ServiceError) as e:
        review.add_manual_correction(ctx, t["id"], 7, 9, "x", "carol")
    assert e.value.code == "overlap"
    with pytest.raises(ServiceError) as e2:
        review.add_manual_correction(ctx, t["id"], 0, 5, "x", "carol", expected_original="nope")
    assert e2.value.code == "span_mismatch"


def test_verify_requires_reviewer_and_text(live_ctx, tone_wav):
    clip = ingest(live_ctx, tone_wav).clips[0]
    with pytest.raises(ServiceError) as e:
        review.verify_reference(live_ctx, clip["id"], "text", "")
    assert e.value.code == "reviewer_required"
    with pytest.raises(ServiceError):
        review.verify_reference(live_ctx, clip["id"], " ", "dana")
    c = review.verify_reference(live_ctx, clip["id"], "ground truth", "dana")
    assert c["review_status"] == "verified" and c["reference_by"] == "dana"
    assert review.unverify(live_ctx, clip["id"], "dana")["reference_transcript"] is None


def test_promote_creates_candidate_only(live_ctx, tone_wav):
    ctx = live_ctx
    clip = ingest(ctx, tone_wav).clips[0]
    t = import_transcript(ctx, clip["id"], "hello world")
    s = review.add_manual_correction(ctx, t["id"], 0, 5, "HELLO", "erin")
    entry = review.promote_to_lexicon(ctx, s["id"], "erin")
    assert entry["status"] == "candidate" and entry["source_form"] == "hello"
    pending = ctx.repo.list_suggestions(import_transcript(ctx, clip["id"], "x  y")["id"])
    with pytest.raises(ServiceError):
        review.promote_to_lexicon(ctx, pending[0]["id"], "erin")


def _verified_clip(ctx, path, perm="UNKNOWN", usage="UNKNOWN", ref="ground truth", speaker="UNKNOWN"):
    r = ingest(ctx, path, permission_status=perm, permitted_usage=usage, speaker_id=speaker)
    clip = r.clips[0]
    import_transcript(ctx, clip["id"], "ground trut")
    review.verify_reference(ctx, clip["id"], ref, "dana")
    return clip


def test_public_export_excludes_unknown_denied_and_nonpublic(live_ctx, make_tone):
    ctx = live_ctx
    _verified_clip(ctx, make_tone(300), "granted", "public_release", speaker="Real Name")
    _verified_clip(ctx, make_tone(350), "UNKNOWN", "UNKNOWN")
    _verified_clip(ctx, make_tone(400), "denied", "UNKNOWN")
    _verified_clip(ctx, make_tone(450), "granted", "private_research")
    out = export_dataset(ctx, "public")
    m = out["manifest"]
    assert m["clip_count"] == 1
    assert m["excluded_counts"]["permission_unknown"] == 2
    assert m["excluded_counts"]["permission_denied"] >= 1 and m["excluded_counts"]["usage_not_public"] >= 1
    import json, zipfile
    with zipfile.ZipFile(out["zip_path"]) as z:
        rec = json.loads(z.read("metadata.jsonl").decode().splitlines()[0])
        assert rec["speaker_id"].startswith("spk_") and "Real Name" not in json.dumps(rec)
        assert rec["reference_verified_by"] is None
        assert any(n.endswith(".wav") for n in z.namelist()) and "DATASET_CARD.md" in z.namelist()


def test_internal_export_never_includes_denied_unknown_only_by_flag(live_ctx, make_tone):
    ctx = live_ctx
    _verified_clip(ctx, make_tone(300), "granted", "private_research")
    _verified_clip(ctx, make_tone(350), "UNKNOWN", "UNKNOWN")
    _verified_clip(ctx, make_tone(400), "denied", "UNKNOWN")
    assert export_dataset(ctx, "internal")["manifest"]["clip_count"] == 1
    assert export_dataset(ctx, "internal", include_unknown_internal=True)["manifest"]["clip_count"] == 2
    with pytest.raises(ServiceError):
        export_dataset(ctx, "public", include_unknown_internal=True)


def test_export_requires_verification_by_default(live_ctx, tone_wav):
    ingest(live_ctx, tone_wav, permission_status="granted", permitted_usage="public_release")
    assert export_dataset(live_ctx, "public")["manifest"]["clip_count"] == 0
    assert export_dataset(live_ctx, "public", require_verified=False)["manifest"]["clip_count"] == 2


def test_evaluation_uses_only_verified_refs_and_accepted_corrections(live_ctx, make_tone):
    ctx = live_ctx
    add_lex(ctx, "dform", "sform", status="candidate")
    c1 = ingest(ctx, make_tone(300)).clips[0]
    t = import_transcript(ctx, c1["id"], "this dform ok")
    unverified = ingest(ctx, make_tone(500)).clips[0]
    import_transcript(ctx, unverified["id"], "other")
    review.verify_reference(ctx, c1["id"], "this sform ok", "dana")
    r = run_evaluation(ctx)
    assert r["sample_count_scored"] == 1 and r["aggregate"]["delta_wer"] == 0.0   # nothing accepted yet
    review.decide(ctx, ctx.repo.list_suggestions(t["id"])[0]["id"], "accepted", "dana")
    r = run_evaluation(ctx)
    assert r["aggregate"]["before"]["wer"] > 0 and r["aggregate"]["after"]["wer"] == 0
    assert ctx.repo.list_eval_runs()


def test_evaluation_excludes_synthetic_in_live_mode(live_ctx, tone_wav):
    ctx = live_ctx
    clip = ingest(ctx, tone_wav).clips[0]
    ctx.repo.add_transcript({"clip_id": clip["id"], "provider": "demo-mock", "is_synthetic": 1, "transcript_raw": "x y"})
    review.verify_reference(ctx, clip["id"], "x y", "dana")
    r = run_evaluation(ctx)
    assert r["sample_count_total"] == 0 and r["pre_scoring_skipped"]["synthetic_excluded"] == 1


def test_seed_demo_only_in_demo_mode_and_idempotent(live_ctx, demo_ctx):
    from src.services.demo import seed_demo
    with pytest.raises(ServiceError):
        seed_demo(live_ctx)
    first = seed_demo(demo_ctx)
    assert first["seeded"] and first["clips"] == 12 and first["verified_clips"] == 8
    assert seed_demo(demo_ctx)["seeded"] is False
    r = run_evaluation(demo_ctx)
    assert r["warnings"][0].startswith("DEMO DATA")
    assert r["aggregate"]["after"]["wer"] < r["aggregate"]["before"]["wer"]


@pytest.mark.parametrize("ext,codec", [("webm", "libopus"), ("mp3", "libmp3lame"), ("m4a", "aac"), ("ogg", "libvorbis")])
def test_ingest_browser_and_compressed_formats(live_ctx, tone_wav, tmp_path, ext, codec):
    import subprocess
    out = tmp_path / f"rec.{ext}"
    r = subprocess.run(["ffmpeg", "-y", "-i", tone_wav, "-c:a", codec, str(out)], capture_output=True)
    if r.returncode != 0:
        pytest.skip(f"ffmpeg build lacks {codec}")
    res = ingest(live_ctx, str(out))
    assert res.segmentation_status == "success" and len(res.clips) >= 1
