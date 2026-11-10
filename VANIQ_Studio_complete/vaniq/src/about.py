"""Single source of truth for what is real, what is demo, and what is not implemented."""

PRODUCT = {"name": "VANIQ", "tagline": "Voice intelligence for every language.", "edition": "VANIQ Local",
           "version": "1.0.0", "target_language": "Ahirani (Khandeshi dialect)"}

CAPABILITIES = [
    {"feature": "Audio upload, validation, FFmpeg normalization (16 kHz mono PCM)", "status": "implemented",
     "note": "Works on real audio. Formats: wav, mp3, m4a, flac, ogg, opus, webm, aac, mp4, wma."},
    {"feature": "Energy-based activity segmentation (Auditok)", "status": "implemented",
     "note": "Detects audible regions, not speech specifically; threshold needs calibration per recording setup."},
    {"feature": "Audio quality metrics (RMS, peak, clipping, silence ratio)", "status": "implemented", "note": ""},
    {"feature": "Gnani Prisma STT transcription", "status": "implemented-needs-credentials",
     "note": "Requires GNANI_API_KEY. Prisma documents Marathi support; native Ahirani support is NOT established."},
    {"feature": "Demo STT provider", "status": "demo-only",
     "note": "Returns labelled placeholder text unrelated to the audio. Only active when VANIQ_MODE=demo."},
    {"feature": "Import transcripts from other tools", "status": "implemented", "note": "Stored as provider 'imported'."},
    {"feature": "Dialect-aware correction: lexicon + context rules", "status": "implemented",
     "note": "Rule-based lookup, NOT a trained model. Ships with no Ahirani vocabulary; entries are user-supplied."},
    {"feature": "Trained dialect correction model", "status": "not-implemented",
     "note": "Pluggable via CorrectionBackend once verified data exists."},
    {"feature": "Dialect identification", "status": "not-implemented",
     "note": "STT language codes are language detection. Dialect labels are human-assigned."},
    {"feature": "Human review, verification, audit log", "status": "implemented",
     "note": "Reviewer names are self-declared; there is no authentication."},
    {"feature": "Dataset export with permission gating", "status": "implemented",
     "note": "Public export excludes unknown/denied permissions and anonymizes speaker IDs."},
    {"feature": "WER/CER evaluation with script-mismatch exclusion", "status": "implemented",
     "note": "No cross-script transliteration is attempted."},
    {"feature": "Authentication / multi-user access control", "status": "not-implemented",
     "note": "Local single-user tool; binds to 127.0.0.1 by default."},
]

LIMITATIONS = [
    "No claim is made that Gnani Prisma natively supports Ahirani. Pilot outputs came from a Marathi model and a "
    "language auto-detect mode.",
    "No accuracy figure for Ahirani STT or for the correction engine exists yet; any shown in demo mode is synthetic.",
    "The correction engine is a lexicon lookup, not machine learning. It is only as good as the verified entries.",
    "Ahirani lacks a standardised orthography; references must follow a documented spelling convention.",
    "Language detection reported by an STT provider is not dialect identification.",
    "Small datasets cannot support claims of broad language coverage.",
    "Energy-based segmentation can split or merge speech incorrectly and detects non-speech sounds.",
    "No authentication: do not expose this server to untrusted networks.",
]
