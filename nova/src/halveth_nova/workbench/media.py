"""Bounded local media decoding and optional offline speech inference."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from ..jsonutil import sha256_bytes


def decode(data: bytes, *, frame_limit: int = 3, seconds_limit: int = 10) -> dict:
    if len(data) > 8_000_000 or not 1 <= frame_limit <= 8 or not 1 <= seconds_limit <= 30:
        raise ValueError("MEDIA_INPUT_LIMIT")
    try:
        import av
    except ImportError:
        return {"state": "UNAVAILABLE", "reason": "optional av package missing", "frames": []}
    frames, decoded, packet_limit = [], 0, 5000
    with av.open(io.BytesIO(data)) as container:
        streams = [{"index": s.index, "type": s.type, "time_base": str(s.time_base),
                    "duration_ticks": s.duration, "declared_frames": s.frames} for s in container.streams]
        if container.streams.video:
            stream = container.streams.video[0]
            for frame in container.decode(stream):
                decoded += 1
                seconds = float(frame.pts * frame.time_base) if frame.pts is not None and frame.time_base is not None else None
                if seconds is not None and seconds > seconds_limit:
                    break
                if decoded > packet_limit:
                    break
                if seconds is None or seconds >= len(frames):
                    image = frame.to_image(); image.thumbnail((512, 512))
                    target = io.BytesIO(); image.save(target, format="PNG"); raw = target.getvalue()
                    frames.append({"pts": frame.pts, "time_base": str(frame.time_base), "presentation_seconds": seconds,
                                   "sha256": sha256_bytes(raw), "png_base64": base64.b64encode(raw).decode("ascii"),
                                   "width": image.width, "height": image.height, "decoded_frame_ordinal": decoded})
                if len(frames) >= frame_limit:
                    break
    return {"state": "DECODED_WITH_BOUND_COVERAGE", "decoder": "PyAV", "decoder_version": av.__version__,
            "input_digest": sha256_bytes(data), "streams": streams, "frames": frames,
            "coverage": {"decoded_frames": decoded, "sampled_frames": len(frames), "frame_limit": frame_limit,
                         "seconds_limit": seconds_limit, "decode_frame_limit": packet_limit,
                         "operator": "first frame at each integer presentation second, first video stream",
                         "time_basis": "media presentation clock; no UTC or inter-camera calibration"},
            "gaps": ["finite sample; unsampled intervals and streams remain unobserved",
                     "decoded frame pixels are not object recognition or physical motion proof"]}


def transcribe(data: bytes, model_directory: Path, *, language: str | None = None, seconds_limit: int = 30) -> dict:
    if not model_directory.is_dir() or len(data) > 8_000_000 or not 1 <= seconds_limit <= 120:
        raise ValueError("LOCAL_SPEECH_MODEL_OR_MEDIA_LIMIT")
    from faster_whisper import WhisperModel
    import av
    import numpy as np
    files = [{"name": p.name, "sha256": sha256_bytes(p.read_bytes()), "bytes": p.stat().st_size}
             for p in sorted(model_directory.iterdir()) if p.is_file()]
    # A directory and local_files_only avoid model downloads or credential use during analysis.
    model = WhisperModel(str(model_directory), device="cpu", compute_type="int8", local_files_only=True)
    # Decode explicitly: faster-whisper 1.2.1's file decoder calls a removed
    # PyAV 19 keyword. Passing a bound float32 signal uses its supported ndarray API.
    rate, remaining, chunks, decoded = 16000, seconds_limit * 16000, [], 0
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
    with av.open(io.BytesIO(data)) as container:
        if not container.streams.audio:
            raise ValueError("NO_AUDIO_STREAM")
        stream = container.streams.audio[0]
        source_stream = {"index": stream.index, "time_base": str(stream.time_base)}
        for frame in container.decode(stream):
            decoded += 1
            if decoded > 10000:
                raise ValueError("AUDIO_DECODE_FRAME_LIMIT")
            for output in resampler.resample(frame):
                samples = output.to_ndarray().reshape(-1)[:remaining]
                chunks.append(samples); remaining -= len(samples)
                if not remaining:
                    break
            if not remaining:
                break
        if remaining:
            for output in resampler.resample(None):
                samples = output.to_ndarray().reshape(-1)[:remaining]
                chunks.append(samples); remaining -= len(samples)
    if not chunks:
        raise ValueError("EMPTY_AUDIO_SIGNAL")
    audio = np.concatenate(chunks).astype(np.float32, copy=False)
    segments, info = model.transcribe(audio, language=language, beam_size=1, condition_on_previous_text=False)
    rows = [{"start_seconds": s.start, "end_seconds": s.end, "text": s.text,
             "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob} for s in segments]
    return {"contract": "nova.speech-derivation.v1", "state": "MODEL_INFERRED_TRANSCRIPT",
            "input_digest": sha256_bytes(data), "model_files": files, "language": info.language,
            "segments": rows, "text": "\n".join(row["text"] for row in rows),
            "coverage": {"seconds_limit": seconds_limit, "decoded_frames": decoded,
                         "source_stream": source_stream, "samples": len(audio), "sample_rate": rate,
                         "channels": "resampled mono", "sample_format": "float32",
                         "decoder": "PyAV", "decoder_version": av.__version__,
                         "sample_digest": sha256_bytes(audio.astype("<f4").tobytes()),
                         "time_basis": "inferred segments relative to first decoded/resampled audio sample; no UTC"},
            "authority": "NONE", "network": "NONE_DURING_TRANSCRIPTION"}
