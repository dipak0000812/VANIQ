import numpy as np

def measure_quality(data, sr):
    """
    Measure audio quality: RMS, Peak, Clipping, and Silence.
    Handles edge cases: empty arrays, short recordings, invalid sample rates.
    """
    # Validate sample rate
    if not isinstance(sr, (int, float)) or sr <= 0:
        return {
            "rms_dbfs": -100.0,
            "peak_dbfs": -100.0,
            "clipping_count": 0,
            "silence_ratio": 1.0
        }
    
    # Handle empty array
    if data is None or len(data) == 0:
        return {
            "rms_dbfs": -100.0,
            "peak_dbfs": -100.0,
            "clipping_count": 0,
            "silence_ratio": 1.0
        }
    
    # Convert to float32 if needed
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    elif data.dtype != np.float32 and data.dtype != np.float64:
        data = data.astype(np.float32)
    
    # Peak Level
    peak = float(np.max(np.abs(data)))
    peak_dbfs = 20 * np.log10(peak) if peak > 0 else -100.0

    # RMS Level
    rms = float(np.sqrt(np.mean(data**2)))
    rms_dbfs = 20 * np.log10(rms) if rms > 0 else -100.0

    # Clipping Count (absolute values >= 0.999)
    clipping_count = int(np.sum(np.abs(data) >= 0.999))

    # Silence Ratio (frames below -60dBFS)
    frame_size = int(0.02 * sr)  # 20ms
    if frame_size <= 0:
        # Invalid sample rate or frame size
        silence_ratio = 1.0 if rms < 0.001 else 0.0
    else:
        # Handle recordings shorter than one frame
        if len(data) < frame_size:
            # Treat entire recording as a single partial frame
            f_rms = float(np.sqrt(np.mean(data**2)))
            silence_ratio = 1.0 if f_rms < 0.001 else 0.0
        else:
            # Process full frames and handle trailing partial frame
            num_full_frames = len(data) // frame_size
            silent_frames = 0
            for i in range(num_full_frames):
                frame = data[i*frame_size : (i+1)*frame_size]
                f_rms = float(np.sqrt(np.mean(frame**2)))
                if f_rms < 0.001:  # -60dB
                    silent_frames += 1
            
            # Handle trailing partial frame (incomplete)
            trailing_start = num_full_frames * frame_size
            if trailing_start < len(data):
                trailing_frame = data[trailing_start:]
                f_rms = float(np.sqrt(np.mean(trailing_frame**2)))
                if f_rms < 0.001:
                    silent_frames += 1
            
            total_frames = num_full_frames + (1 if trailing_start < len(data) else 0)
            silence_ratio = silent_frames / total_frames if total_frames > 0 else 0.0

    return {
        "rms_dbfs": round(rms_dbfs, 2),
        "peak_dbfs": round(peak_dbfs, 2),
        "clipping_count": clipping_count,
        "silence_ratio": round(silence_ratio, 3)
    }
