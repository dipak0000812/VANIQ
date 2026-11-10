import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture
def demo_client(demo_ctx):
    return TestClient(create_app(demo_ctx))


@pytest.fixture
def live_client(live_ctx):
    return TestClient(create_app(live_ctx))


def upload(client, path, **fields):
    with open(path, "rb") as f:
        return client.post("/api/sources", files={"file": (path.split("/")[-1], f, "audio/wav")}, data=fields)


def test_health_and_static_index(live_client):
    h = live_client.get("/api/health").json()
    assert h["mode"] == "live" and h["stt_configured"] is False and h["ffmpeg"] is True
    r = live_client.get("/")
    assert r.status_code == 200 and "VANIQ" in r.text


def test_about_is_honest_about_capabilities(live_client):
    a = live_client.get("/api/about").json()
    status = {c["feature"]: c["status"] for c in a["capabilities"]}
    assert status["Trained dialect correction model"] == "not-implemented"
    assert status["Demo STT provider"] == "demo-only"
    assert a["stt"]["active_provider"] == "none"


def test_full_demo_workflow_through_api(demo_client, tone_wav):
    c = demo_client
    assert c.post("/api/demo/seed").json()["seeded"] is True
    dash = c.get("/api/dashboard").json()
    assert dash["mode"] == "demo" and dash["counts"]["clips"] == 12
    clips = c.get("/api/clips?review_status=needs_review").json()
    cid = clips[0]["id"]
    ws = c.get(f"/api/clips/{cid}").json()
    t = ws["transcripts"][0]
    assert ws["clip"]["is_demo"] == 1 and t["is_synthetic"] == 1
    sugs = t["suggestions"]
    if sugs:
        d = c.post(f"/api/suggestions/{sugs[0]['id']}/decision", json={"decision": "accepted", "reviewer": "tester"})
        assert d.status_code == 200 and d.json()["status"] == "accepted"
    v = c.post(f"/api/clips/{cid}/verify", json={"reference": "ref text", "reviewer": "tester"})
    assert v.json()["review_status"] == "verified"
    ev = c.post("/api/evaluate", json={}).json()
    assert ev["sample_count_scored"] >= 9 and "limitations" in ev
    ex = c.post("/api/exports", json={"visibility": "public"}).json()
    assert ex["manifest"]["clip_count"] >= 1
    z = c.get(ex["download"])
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert c.get(f"/api/clips/{cid}/audio").headers["content-type"] == "audio/wav"


def test_upload_validation_errors(live_client, tmp_path):
    bad = tmp_path / "bad.wav"; bad.write_bytes(b"junk" * 50)
    r = upload(live_client, str(bad))
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_audio"
    txt = tmp_path / "n.txt"; txt.write_text("x")
    with open(txt, "rb") as f:
        r = live_client.post("/api/sources", files={"file": ("n.txt", f, "text/plain")})
    assert r.status_code == 415
    r = live_client.post("/api/sources")
    assert r.status_code == 422


def test_upload_size_limit(live_ctx, tone_wav, monkeypatch):
    from dataclasses import replace
    live_ctx.settings = replace(live_ctx.settings, max_upload_mb=0)
    r = upload(TestClient(create_app(live_ctx)), tone_wav)
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_live_transcribe_without_key_returns_503(live_client, tone_wav):
    res = upload(live_client, tone_wav).json()
    cid = res["clips"][0]["id"]
    r = live_client.post(f"/api/clips/{cid}/transcribe", json={"language_code": "mr-IN"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "stt_not_configured"


def test_permission_patch_and_consistency(live_client, tone_wav):
    res = upload(live_client, tone_wav).json()
    sid = res["source"]["id"]
    assert live_client.patch(f"/api/sources/{sid}", json={"permitted_usage": "public_release"}).status_code == 422
    ok = live_client.patch(f"/api/sources/{sid}", json={"permission_status": "granted", "permitted_usage": "public_release", "reviewer": "x"})
    assert ok.status_code == 200 and ok.json()["permission_status"] == "granted"
    assert live_client.patch("/api/sources/nope", json={}).status_code == 404


def test_lexicon_rules(live_client):
    c = live_client
    r = c.post("/api/lexicon", json={"source_form": "a", "target_form": "b", "status": "verified"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "provenance_required"
    assert c.post("/api/lexicon", json={"source_form": "a", "target_form": "b", "status": "demo"}).status_code == 422
    ok = c.post("/api/lexicon", json={"source_form": "a", "target_form": "b", "status": "verified", "provenance": "linguist Y", "reviewer": "z"})
    lid = ok.json()["id"]
    assert c.patch(f"/api/lexicon/{lid}", json={"enabled": False}).json()["enabled"] == 0
    assert c.get("/api/lexicon").json()[0]["review_stats"]["accepted"] == 0
    assert c.delete(f"/api/lexicon/{lid}").status_code == 200
    assert c.delete(f"/api/lexicon/{lid}").status_code == 404


def test_export_download_path_traversal_blocked(live_client):
    assert live_client.get("/api/exports/download/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert live_client.get("/api/exports/download/nothing.zip").status_code == 404
    assert live_client.post("/api/exports", json={"visibility": "weird"}).status_code == 422


def test_unknown_ids_return_404(live_client):
    assert live_client.get("/api/clips/nope").status_code == 404
    assert live_client.post("/api/suggestions/999/decision", json={"decision": "accepted", "reviewer": "x"}).status_code == 404


def test_transcript_with_markup_is_stored_verbatim(live_client, tone_wav):
    cid = upload(live_client, tone_wav).json()["clips"][0]["id"]
    payload = "<img src=x onerror=alert(1)> text"
    live_client.post(f"/api/clips/{cid}/transcripts/import", json={"text": payload})
    assert live_client.get(f"/api/clips/{cid}").json()["transcripts"][0]["transcript_raw"] == payload


def test_seed_refused_in_live_mode(live_client):
    assert live_client.post("/api/demo/seed").status_code == 409
