"""Legacy pilot runner: send one local audio file to Gnani with several language settings and save raw responses.

Kept for reproducing the original Marathi-vs-auto-detect pilot. The web app (python -m src.cli serve) is the
primary workflow. Requires GNANI_API_KEY.
"""
import argparse
import json
import os
import sys

from src.gnani.client import GnaniClient, GnaniError

DEFAULT_AUDIO = "audio/clip_001_16k.wav"


def run_experiment(config_name, model, language_code, output_file, audio_path=DEFAULT_AUDIO):
    client = GnaniClient()
    print(f"Running experiment {config_name}...")
    result = client.transcribe(audio_path, model=model, language_code=language_code)

    output = {
        "config": config_name,
        "latency": result["latency"],
        "api_response": result["data"],
    }
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Saved to {output_file}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", default=DEFAULT_AUDIO)
    args = ap.parse_args(argv)
    try:
        run_experiment("A", "prisma-v3.0", "indic-auto", "results/config_a.json", args.audio)
        run_experiment("B", "prisma-v3.0", "mr-IN", "results/config_b.json", args.audio)
    except (GnaniError, FileNotFoundError, ValueError) as exc:
        print(f"Experiment failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
