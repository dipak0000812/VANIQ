"""Legacy pilot evaluation: score results/config_*.json against references/clip_001.txt.

Fixes vs the original: normalization no longer strips Indic vowel signs, cross-script pairs are not scored
(reported as excluded), and suspiciously high error rates are flagged as a possible reference/audio mismatch.
The web app's Evaluation page is the primary workflow.
"""
import csv
import json
import sys

from src.evaluation.metrics import calculate_cer, calculate_wer, detect_script, normalize_text

CONFIGS = ["results/config_a.json", "results/config_b.json"]


def evaluate(reference_path="references/clip_001.txt", configs=CONFIGS, out_json="results/evaluation.json",
             out_csv="results/evaluation.csv"):
    try:
        with open(reference_path, "r", encoding="utf-8") as f:
            ref_orig = f.read().strip()
    except FileNotFoundError:
        print(f"Reference file not found: {reference_path}", file=sys.stderr)
        return []

    ref_script, ref_norm = detect_script(ref_orig), normalize_text(ref_orig)
    results = []
    for cfg in configs:
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            continue
        api_resp = data.get("api_response", {})
        hyp_orig = api_resp.get("transcript", "")
        hyp_script, hyp_norm = detect_script(hyp_orig), normalize_text(hyp_orig)
        mismatch = ref_script != hyp_script
        notes = ["Single-clip pilot evaluation; not statistically meaningful."]
        wer_raw = cer_raw = wer_norm = cer_norm = None
        if mismatch:
            notes.append("Reference and hypothesis use different scripts: not scored (no transliteration is attempted).")
        else:
            wer_raw, cer_raw = calculate_wer(ref_orig, hyp_orig), calculate_cer(ref_orig, hyp_orig)
            wer_norm, cer_norm = calculate_wer(ref_norm, hyp_norm), calculate_cer(ref_norm, hyp_norm)
            if wer_norm > 1.0:
                notes.append("WER above 100%: verify that the reference transcript matches this audio.")
        rnd = lambda x: None if x is None else round(x, 4)
        results.append({
            "config": data.get("config"), "request_id": api_resp.get("request_id", "unknown"),
            "model": api_resp.get("model", "unknown"),
            "detected_language_code": api_resp.get("detected_language_code", "unknown"),
            "latency_total_s": data.get("latency"), "processing_time_s": api_resp.get("processing_time"),
            "end_to_end_latency_s": api_resp.get("end_to_end_latency"),
            "reference_script": ref_script, "predicted_script": hyp_script, "script_mismatch": mismatch,
            "wer_raw": rnd(wer_raw), "cer_raw": rnd(cer_raw), "wer_norm": rnd(wer_norm), "cer_norm": rnd(cer_norm),
            "reference_transcript": ref_orig, "predicted_transcript": hyp_orig, "notes": " ".join(notes)})

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    if results:
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
    return results


if __name__ == "__main__":
    evaluate()
