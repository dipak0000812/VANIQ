import argparse
import sys
import os
from src.dataset_factory.ingestion import process_source

def main():
    parser = argparse.ArgumentParser(
        description="VANIQ Dataset Factory: Ingest and process local media files."
    )
    parser.add_argument(
        "command",
        choices=["ingest"],
        help="Action to perform (e.g., ingest)"
    )
    parser.add_argument(
        "source",
        help="Path to the source media file or directory."
    )
    parser.add_argument(
        "--output-root",
        default="dataset/output",
        help="Root directory for processed clips and metadata."
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Optionally trigger Gnani transcription for generated clips."
    )
    parser.add_argument(
        "--source-url",
        default="UNKNOWN",
        help="Source URL or provenance (default: UNKNOWN)."
    )
    parser.add_argument(
        "--speaker-id",
        default="UNKNOWN",
        help="Speaker identifier (default: UNKNOWN)."
    )
    parser.add_argument(
        "--dialect",
        default="UNKNOWN",
        help="Dialect or language variant (default: UNKNOWN)."
    )
    parser.add_argument(
        "--permission-status",
        default="UNKNOWN",
        help="Permission status (default: UNKNOWN)."
    )
    parser.add_argument(
        "--permitted-usage",
        default="UNKNOWN",
        help="Permitted usage scope (default: UNKNOWN)."
    )
    
    args = parser.parse_args()
    
    if args.command == "ingest":
        source_path = args.source
        if not os.path.exists(source_path):
            print(f"Error: Source path does not exist: {source_path}")
            sys.exit(1)
            
        if os.path.isdir(source_path):
            files = [os.path.join(source_path, f) for f in os.listdir(source_path) if not f.startswith('.')]
            for f in files:
                if os.path.isfile(f):
                    print(f"Processing file: {f}")
                    process_source(
                        f, args.output_root, transcribe=args.transcribe,
                        source_url=args.source_url, speaker_id=args.speaker_id,
                        dialect=args.dialect, permission_status=args.permission_status,
                        permitted_usage=args.permitted_usage
                    )
        else:
            process_source(
                source_path, args.output_root, transcribe=args.transcribe,
                source_url=args.source_url, speaker_id=args.speaker_id,
                dialect=args.dialect, permission_status=args.permission_status,
                permitted_usage=args.permitted_usage
            )

if __name__ == "__main__":
    main()
