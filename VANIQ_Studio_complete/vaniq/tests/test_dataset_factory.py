import os
import sys
import pytest
import numpy as np
from scipy.io import wavfile

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.dataset_factory.audio import normalize_audio, load_audio
from src.dataset_factory.quality import measure_quality
from src.dataset_factory.segmentation import (
    detect_audio_activity_segments, generate_source_id, generate_clip_id,
    AudioSegmentationError
)
from src.dataset_factory.ingestion import process_source
from src.dataset_factory.metadata import MetadataManager, METADATA_FIELDS, UNKNOWN

def test_normalize_audio(tmp_path):
    sr = 44100
    t = np.linspace(0, 1, sr, endpoint=False)
    data = (np.sin(2*np.pi*440*t) * 0.5 * 32767).astype(np.int16)
    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "output.wav"
    wavfile.write(input_path, sr, data)
    
    assert normalize_audio(str(input_path), str(output_path)) is True
    assert output_path.exists()
    
    out_sr, out_data = wavfile.read(output_path)
    assert out_sr == 16000
    assert out_data.dtype == np.int16

def test_load_audio(tmp_path):
    sr = 16000
    data = np.zeros(sr, dtype=np.int16)
    path = tmp_path / "test.wav"
    wavfile.write(path, sr, data)
    loaded_data, loaded_sr = load_audio(str(path))
    assert loaded_sr == 16000
    assert len(loaded_data) == sr

def test_measure_quality_silence():
    data = np.zeros(1600, dtype=np.float32)
    q = measure_quality(data, 16000)
    assert q["rms_dbfs"] == -100.0
    assert q["peak_dbfs"] == -100.0
    assert q["clipping_count"] == 0
    assert q["silence_ratio"] == 1.0

def test_measure_quality_tone():
    sr = 16000
    t = np.linspace(0, 1, sr, endpoint=False)
    data = (np.sin(2*np.pi*440*t) * 0.5).astype(np.float32)
    q = measure_quality(data, sr)
    assert q["rms_dbfs"] > -10.0
    assert q["peak_dbfs"] > -10.0
    assert q["clipping_count"] == 0
    assert q["silence_ratio"] == 0.0

def test_measure_quality_empty_array():
    q = measure_quality(np.array([], dtype=np.float32), 16000)
    assert q["rms_dbfs"] == -100.0
    assert q["silence_ratio"] == 1.0

def test_measure_quality_short_recording():
    data = np.zeros(100, dtype=np.float32)
    q = measure_quality(data, 16000)
    assert q["silence_ratio"] == 1.0

def test_measure_quality_invalid_sr():
    data = np.zeros(1000, dtype=np.float32)
    q = measure_quality(data, -100)
    assert q["rms_dbfs"] == -100.0

def test_generate_clips_id_stability(tmp_path):
    """Test clip ID generation stability with a real file."""
    sr = 16000
    tone = (np.sin(2*np.pi*440*np.linspace(0, 1, sr)) * 0.5 * 32767).astype(np.int16)
    path1 = tmp_path / "audio1.wav"
    path2 = tmp_path / "audio2.wav"
    wavfile.write(path1, sr, tone)
    wavfile.write(path2, sr, tone)
    
    id1 = generate_clip_id(str(path1), 0.0, 1.0)
    id2 = generate_clip_id(str(path2), 0.0, 1.0)
    assert id1 == id2
    assert len(id1) == 16

def test_generate_source_id_content_based(tmp_path):
    path1 = tmp_path / "source.wav"
    path2 = tmp_path / "copy.wav"
    sr = 16000
    data = np.zeros(sr, dtype=np.int16)
    wavfile.write(path1, sr, data)
    wavfile.write(path2, sr, data)
    
    id1 = generate_source_id(str(path1))
    id2 = generate_source_id(str(path2))
    assert id1 == id2

def test_process_source_no_speech(tmp_path):
    sr = 16000
    data = np.zeros(sr * 2, dtype=np.int16)
    source_path = tmp_path / "silent.wav"
    wavfile.write(source_path, sr, data)
    
    output_root = tmp_path / "output"
    metadata_path = process_source(str(source_path), str(output_root))
    
    assert os.path.exists(metadata_path)
    import csv
    with open(metadata_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["review_status"] == "needs_review"
        assert rows[0]["is_verified"] == "False"

def test_process_source_idempotent(tmp_path):
    sr = 16000
    t = np.linspace(0, 2, sr*2, endpoint=False)
    data = np.zeros(sr*2, dtype=np.int16)
    data[sr:] = (np.random.randn(sr) * 0.1 * 32767).astype(np.int16)
    
    source_path = tmp_path / "source.wav"
    wavfile.write(source_path, sr, data)
    
    output_root = tmp_path / "output"
    
    process_source(str(source_path), str(output_root))
    metadata_path = process_source(str(source_path), str(output_root))
    
    import csv
    with open(metadata_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1

def test_process_source_unknown_fields(tmp_path):
    sr = 16000
    data = np.zeros(sr, dtype=np.int16)
    source_path = tmp_path / "source.wav"
    wavfile.write(source_path, sr, data)
    
    output_root = tmp_path / "output"
    process_source(str(source_path), str(output_root))
    
    import csv
    metadata_path = os.path.join(str(output_root), "metadata.csv")
    with open(metadata_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert rows[0]["source_url"] == UNKNOWN
        assert rows[0]["speaker_id"] == UNKNOWN

def test_metadata_manager_idempotent():
    manager = MetadataManager("/tmp/test_metadata.csv")
    clip_info = {
        "clip_id": "test123",
        "start_time": 0.0,
        "end_time": 1.0,
        "duration": 1.0,
        "source_path": "test.wav"
    }
    quality = {"rms_dbfs": -20.0, "peak_dbfs": -5.0, "clipping_count": 0, "silence_ratio": 0.1}
    
    manager.add_or_update_record(clip_info, quality, "src1")
    manager.add_or_update_record(clip_info, quality, "src1")
    
    assert len(manager.records) == 1

# --- Audio Activity Detection Tests ---

def test_detect_audio_activity_speech_like(tmp_path):
    """Test audio activity detection with synthetic speech-like audio."""
    sr = 16000
    t1 = np.linspace(0, 1, sr, endpoint=False)
    tone1 = (np.sin(2*np.pi*440*t1) * 0.5 * 32767).astype(np.int16)
    silence = np.zeros(int(sr * 0.5), dtype=np.int16)
    t2 = np.linspace(0, 1, sr, endpoint=False)
    tone2 = (np.sin(2*np.pi*440*t2) * 0.5 * 32767).astype(np.int16)
    
    data = np.concatenate([tone1, silence, tone2])
    path = tmp_path / "speech_like.wav"
    wavfile.write(path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(path))
    assert status == "success"
    assert len(segments) >= 1

def test_detect_audio_activity_silent_audio(tmp_path):
    """Test with completely silent audio."""
    sr = 16000
    data = np.zeros(sr * 2, dtype=np.int16)
    path = tmp_path / "silent.wav"
    wavfile.write(path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(path))
    assert status == "no_speech"
    assert len(segments) == 0

def test_detect_audio_activity_noise_only(tmp_path):
    """Test with low-amplitude noise-only audio."""
    sr = 16000
    np.random.seed(42)
    data = (np.random.randn(sr * 2) * 0.001 * 32767).astype(np.int16)
    path = tmp_path / "noise.wav"
    wavfile.write(path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(path))
    assert status in ("no_speech", "success")

def test_detect_audio_activity_invalid_input():
    """Test with non-existent file."""
    segments, status = detect_audio_activity_segments("/nonexistent/file.wav")
    assert status == "error"
    assert len(segments) == 0

def test_detect_audio_activity_multiple_regions(tmp_path):
    """Test with multiple distinct activity regions."""
    sr = 16000
    tone = (np.sin(2*np.pi*440*np.linspace(0, 0.8, int(sr*0.8))) * 0.5 * 32767).astype(np.int16)
    silence = np.zeros(int(sr * 0.4), dtype=np.int16)
    
    data = np.concatenate([tone, silence, tone, silence, tone])
    path = tmp_path / "multi_activity.wav"
    wavfile.write(path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(path))
    assert status == "success"
    assert len(segments) >= 1
    for i in range(len(segments) - 1):
        assert segments[i][1] <= segments[i+1][0]

def test_detect_audio_activity_with_leading_silence(tmp_path):
    """Test with leading/trailing silence."""
    sr = 16000
    silence = np.zeros(int(sr * 0.5), dtype=np.int16)
    t = np.linspace(0, 1, sr, endpoint=False)
    tone = (np.sin(2*np.pi*440*t) * 0.5 * 32767).astype(np.int16)
    silence2 = np.zeros(int(sr * 0.5), dtype=np.int16)
    
    data = np.concatenate([silence, tone, silence2])
    path = tmp_path / "activity_with_boundary_silence.wav"
    wavfile.write(path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(path))
    assert status == "success"
    if len(segments) > 0:
        for start, end in segments:
            assert 0.0 <= start < end <= 2.5

def test_detect_audio_activity_with_trailing_silence(tmp_path):
    """Test with trailing silence."""
    sr = 16000
    t = np.linspace(0, 1, sr, endpoint=False)
    tone = (np.sin(2*np.pi*440*t) * 0.5 * 32767).astype(np.int16)
    silence = np.zeros(int(sr * 0.5), dtype=np.int16)
    
    data = np.concatenate([tone, silence])
    path = tmp_path / "tone_with_trailing_silence.wav"
    wavfile.write(path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(path))
    assert status == "success"
    if len(segments) > 0:
        for start, end in segments:
            assert 0.0 <= start < end <= 1.5

def test_file_content_hash_raises_on_invalid():
    """Test that _file_content_hash raises explicit error for unreadable files."""
    from src.dataset_factory.segmentation import _file_content_hash
    
    with pytest.raises(AudioSegmentationError):
        _file_content_hash("/nonexistent/unreadable_file.wav")

def test_process_source_invalid_file_raises(tmp_path):
    """Test that ingestion raises RuntimeError for invalid file."""
    with pytest.raises(RuntimeError, match="Source file does not exist"):
        process_source("/nonexistent/file.wav", str(tmp_path / "output"))

def test_process_source_integration(tmp_path):
    sr = 16000
    t = np.linspace(0, 2, sr*2, endpoint=False)
    data = np.zeros(sr*2, dtype=np.int16)
    data[sr:] = (np.random.randn(sr) * 0.1 * 32767).astype(np.int16)
    
    source_path = tmp_path / "source.wav"
    wavfile.write(source_path, sr, data)
    
    output_root = tmp_path / "output"
    metadata_path = process_source(str(source_path), str(output_root))
    
    assert os.path.exists(metadata_path)
    import csv
    with open(metadata_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) > 0
        assert "clip_id" in rows[0]
        assert "rms_dbfs" in rows[0]
        assert "review_status" in rows[0]

def test_extracted_clip_has_correct_format(tmp_path):
    """Verify extracted clip is 16kHz mono PCM S16 LE."""
    from src.dataset_factory.segmentation import split_and_save_clips
    
    sr = 16000
    t = np.linspace(0, 2, sr*2, endpoint=False)
    data = (np.sin(2*np.pi*440*t) * 0.5 * 32767).astype(np.int16)
    source_path = tmp_path / "source.wav"
    wavfile.write(source_path, sr, data)
    
    segments, status = detect_audio_activity_segments(str(source_path))
    assert status == "success"
    
    clips = split_and_save_clips(str(source_path), segments, str(tmp_path / "clips"))
    assert len(clips) > 0
    
    for clip in clips:
        clip_path = clip["file_path"]
        assert os.path.exists(clip_path)
        
        clip_sr, clip_data = wavfile.read(clip_path)
        assert clip_sr == 16000
        assert clip_data.ndim == 1
        assert clip_data.dtype == np.int16
        
        expected_duration = clip["duration"]
        actual_duration = len(clip_data) / clip_sr
        assert abs(actual_duration - expected_duration) < expected_duration * 0.05


def test_reingest_preserves_human_verification(tmp_path):
    """Regression: re-running ingestion used to wipe manual transcripts and verification."""
    from src.dataset_factory.metadata import MetadataManager
    mp = str(tmp_path / "metadata.csv")
    m = MetadataManager(mp)
    clip = {"clip_id": "c1", "start_time": 0, "end_time": 1, "duration": 1, "source_path": "x"}
    q = {"rms_dbfs": -20, "peak_dbfs": -3, "clipping_count": 0, "silence_ratio": 0.1}
    m.add_or_update_record(clip, q, "s1", verified=True, manual_transcript="human text", review_status="verified")
    m.add_or_update_record(clip, q, "s1", review_status="needs_review")
    rec = m.records[0]
    assert rec["manual_transcript"] == "human text" and rec["is_verified"] == "True" and rec["review_status"] == "verified"
