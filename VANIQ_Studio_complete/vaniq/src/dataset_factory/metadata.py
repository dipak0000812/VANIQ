import csv
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

METADATA_FIELDS = [
    "clip_id",
    "source_id",
    "source_path",
    "source_url",
    "speaker_id",
    "dialect",
    "start_time",
    "end_time",
    "duration_s",
    "rms_dbfs",
    "peak_dbfs",
    "clipping_count",
    "silence_ratio",
    "permission_status",
    "permitted_usage",
    "review_status",
    "is_verified",
    "auto_transcript",
    "manual_transcript",
    "detected_language",
    "processing_timestamp"
]

UNKNOWN = "UNKNOWN"

class MetadataManager:
    def __init__(self, metadata_path: str):
        self.metadata_path = metadata_path
        self.records = []
        if os.path.exists(metadata_path):
            self._load()

    def _load(self):
        try:
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.records = list(reader)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to load metadata: %s", e)

    def add_or_update_record(self, clip_info: Dict[str, Any], quality: Dict[str, Any], 
                             source_id: str, source_url: str = UNKNOWN, 
                             speaker_id: str = UNKNOWN, dialect: str = UNKNOWN,
                             permission_status: str = UNKNOWN, 
                             permitted_usage: str = UNKNOWN,
                             review_status: str = UNKNOWN,
                             verified: bool = False, 
                             auto_transcript: str = "", 
                             manual_transcript: str = "", 
                             detected_language: str = "") -> None:
        """
        Idempotently add or update a record using clip_id as the unique key.
        Unknown fields remain explicitly UNKNOWN.
        """
        clip_id = clip_info["clip_id"]
        
        # Check if record already exists
        existing_idx = None
        for idx, rec in enumerate(self.records):
            if rec.get("clip_id") == clip_id:
                existing_idx = idx
                break
        
        record = {
            "clip_id": clip_id,
            "source_id": source_id,
            "source_path": clip_info.get("source_path", ""),
            "source_url": source_url,
            "speaker_id": speaker_id,
            "dialect": dialect,
            "start_time": clip_info["start_time"],
            "end_time": clip_info["end_time"],
            "duration_s": clip_info["duration"],
            "rms_dbfs": quality["rms_dbfs"],
            "peak_dbfs": quality["peak_dbfs"],
            "clipping_count": quality["clipping_count"],
            "silence_ratio": quality["silence_ratio"],
            "permission_status": permission_status,
            "permitted_usage": permitted_usage,
            "review_status": review_status,
            "is_verified": "True" if verified else "False",
            "auto_transcript": auto_transcript,
            "manual_transcript": manual_transcript,
            "detected_language": detected_language,
            "processing_timestamp": datetime.now().isoformat()
        }
        
        if existing_idx is not None:
            # Re-ingesting must never destroy human work: keep manual transcript,
            # verification state and review status that a person already set.
            old = self.records[existing_idx]
            if old.get("is_verified") == "True" or old.get("manual_transcript"):
                record["manual_transcript"] = old.get("manual_transcript", "")
                record["is_verified"] = old.get("is_verified", "False")
                record["review_status"] = old.get("review_status", record["review_status"])
            if not record["auto_transcript"] and old.get("auto_transcript"):
                record["auto_transcript"] = old["auto_transcript"]
                record["detected_language"] = old.get("detected_language", "")
            self.records[existing_idx] = record
        else:
            self.records.append(record)

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.metadata_path)), exist_ok=True)
        with open(self.metadata_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=METADATA_FIELDS)
            writer.writeheader()
            writer.writerows(self.records)
