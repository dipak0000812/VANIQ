"""VANIQ command line.  python -m src.cli --help"""
from __future__ import annotations

import argparse
import json
import sys

from src.config import load_settings
from src.context import build_context
from src.logging_setup import setup_logging


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vaniq", description="VANIQ Local command line")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve", help="start the web app")
    sv.add_argument("--reload", action="store_true")
    sub.add_parser("seed-demo", help="seed synthetic demo data (VANIQ_MODE=demo only)")
    ing = sub.add_parser("ingest", help="ingest an audio file into the database")
    ing.add_argument("path")
    ing.add_argument("--speaker-id", default="UNKNOWN")
    ing.add_argument("--dialect", default="UNKNOWN")
    ing.add_argument("--permission-status", default="UNKNOWN", choices=["UNKNOWN", "granted", "denied"])
    ing.add_argument("--permitted-usage", default="UNKNOWN",
                     choices=["UNKNOWN", "private_research", "internal_training", "public_release"])
    ing.add_argument("--source-url", default="UNKNOWN")
    tr = sub.add_parser("transcribe", help="transcribe a clip")
    tr.add_argument("clip_id")
    tr.add_argument("--language-code", default="indic-auto")
    ev = sub.add_parser("evaluate", help="print an evaluation report as JSON")
    ev.add_argument("--language-code")
    ex = sub.add_parser("export", help="export a dataset zip")
    ex.add_argument("--visibility", choices=["public", "internal"], default="public")
    ex.add_argument("--include-unknown-internal", action="store_true")
    lx = sub.add_parser("import-lexicon", help="import lexicon entries from a JSON file (list of objects)")
    lx.add_argument("file")
    args = p.parse_args(argv)

    settings = load_settings()
    setup_logging(settings.log_level)

    if args.cmd == "serve":
        import uvicorn
        print(f"VANIQ Local ({settings.mode} mode) on http://{settings.host}:{settings.port}")
        uvicorn.run("src.api.app:get_app", factory=True, host=settings.host, port=settings.port, reload=args.reload)
        return 0

    ctx = build_context(settings)
    from src.services.errors import ServiceError
    try:
        if args.cmd == "seed-demo":
            from src.services.demo import seed_demo
            print(json.dumps(seed_demo(ctx), indent=2))
        elif args.cmd == "ingest":
            from src.services.ingest import ingest_file
            import os
            r = ingest_file(ctx, args.path, os.path.basename(args.path), speaker_id=args.speaker_id,
                            dialect_label=args.dialect, permission_status=args.permission_status,
                            permitted_usage=args.permitted_usage, source_url=args.source_url, actor="cli")
            print(json.dumps({"source_id": r.source["id"], "duplicate": r.duplicate,
                              "segmentation_status": r.segmentation_status,
                              "clips": [c["id"] for c in r.clips]}, indent=2))
        elif args.cmd == "transcribe":
            from src.services.transcribe import transcribe_clip
            t = transcribe_clip(ctx, args.clip_id, args.language_code, actor="cli")
            print(json.dumps({k: t[k] for k in ("id", "provider", "is_synthetic", "detected_language_code",
                                                "transcript_raw")}, ensure_ascii=False, indent=2))
        elif args.cmd == "evaluate":
            from src.services.evaluation_service import run_evaluation
            print(json.dumps(run_evaluation(ctx, language_code=args.language_code), ensure_ascii=False, indent=2))
        elif args.cmd == "export":
            from src.services.export import export_dataset
            print(json.dumps(export_dataset(ctx, args.visibility, args.include_unknown_internal), indent=2))
        elif args.cmd == "import-lexicon":
            with open(args.file, encoding="utf-8") as f:
                entries = json.load(f)
            for e in entries:
                st = e.get("status", "candidate")
                if st == "verified" and not e.get("provenance"):
                    raise ServiceError(f"Verified entry {e.get('source_form')!r} needs provenance.", "provenance_required")
                ctx.repo.add_lexicon_entry({**e, "is_demo": 1 if settings.is_demo else 0}, actor="cli-import")
            print(f"Imported {len(entries)} entries")
    except ServiceError as exc:
        print(f"Error [{exc.code}]: {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
