"""Demo STT provider.

It does NOT listen to audio. It returns fixed placeholder sentences chosen deterministically from the
clip file's content hash so that the demo is reproducible. Every result is flagged `is_synthetic=True`
and shown in the UI as "DEMO PLACEHOLDER - not a transcription of this audio".
The placeholder text is deliberately Latin-script nonsense tokens, not Ahirani or Marathi, so no
linguistic claim is made.
"""
from __future__ import annotations

import hashlib

from src.stt.base import STTProvider, STTResult

DEMO_TRANSCRIPTS = [
    "this is demo sentence one with dform1 token",
    "demo sentence two keeps dform2 unchanged here",
    "demo three has dform1 and also dform3 after alpha",
    "short demo four",
    "demo five mentions dform4 beta twice dform4 beta",
    "demo six  has  extra   spaces and dform1",
]


class DemoProvider(STTProvider):
    name = "demo-mock"

    def transcribe(self, audio_path: str, language_code: str) -> STTResult:
        with open(audio_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        text = DEMO_TRANSCRIPTS[int(digest[:8], 16) % len(DEMO_TRANSCRIPTS)]
        return STTResult(transcript=text, provider=self.name, model="demo-placeholder",
                         language_code_requested=language_code, detected_language_code=None,
                         request_id=f"demo-{digest[:12]}", latency_s=0.0,
                         raw_response={"demo": True, "note": "Placeholder text; not derived from the audio."},
                         is_synthetic=True)
