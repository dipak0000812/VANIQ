# Dataset preparation

1. **Get permission first.** Record consent (who, scope, date) in *consent notes* and set permission + permitted usage.
   Defaults are `UNKNOWN`, which is excluded from every public export.
2. **Record or collect audio** in a quiet place, one speaker per recording, ideally phone-quality or better. Upload; check
   quality chips (`low level`, `clipping`, `mostly silent`, `very short`) and re-record bad clips.
3. **Check segmentation.** Segmentation is energy-based (it also splits on loud non-speech). Tune
   `VANIQ_SEG_ENERGY_THRESHOLD` / `VANIQ_SEG_MAX_DUR_S` for your setup. Mark unusable clips *unusable*.
4. **Decide a spelling convention** for Ahirani (no standard orthography exists) and write it down; reviewers must follow it.
5. **Transcribe/import**, review corrections, then write the **verified reference** while listening. Never copy STT output
   unreviewed into a reference.
6. **Export.** *Public* = granted + `public_release` + verified; speakers are hashed (`spk_xxxxxxxx`) and reviewer names removed.
   *Internal* = granted (any usage) + verified; unknown permission only with an explicit flag, recorded in the manifest.
   Denied clips and unusable clips are never exported.

Export zip: `audio/*.wav`, `metadata.jsonl`, `metadata.csv`, `manifest.json` (counts and exclusion reasons),
`DATASET_CARD.md`. No train/test split is produced; create one by speaker, not by clip, to avoid leakage.
