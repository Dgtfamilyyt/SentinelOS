"""On-device speech input. Uploaded audio is held in memory, never saved."""
import asyncio
import io
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api/voice")
MODEL_DIR = Path(__file__).resolve().parents[1] / "data" / "speech-model"
MAX_BYTES = 8 * 1024 * 1024
_model = None
_lock = Lock()


def transcribe(audio):
    global _model
    import av
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "Speech transcription is busy. Try again shortly.")
    try:
        try:
            with av.open(io.BytesIO(audio)) as container:
                duration = 0
                for frame in container.decode(audio=0):
                    duration += frame.samples / frame.sample_rate
                    if duration > 61:
                        raise HTTPException(413, "Recordings must be 60 seconds or shorter.")
            samples = decode_audio(io.BytesIO(audio), sampling_rate=16000)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(422, "Audio could not be decoded. Record again.") from error
        if not MODEL_DIR.joinpath("model.bin").exists():
            raise HTTPException(503, "Local speech model is missing. Run the speech setup command in README.")
        if _model is None:
            _model = WhisperModel(str(MODEL_DIR), device="cpu", compute_type="int8", cpu_threads=4)
        segments, _ = _model.transcribe(samples, beam_size=1, vad_filter=True, condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise HTTPException(422, "No speech detected. Check your microphone and speak closer to it.")
        return {"text": text[:20000]}
    finally:
        _lock.release()


@router.post("/transcribe")
async def transcribe_recording(request: Request):
    content_type = request.headers.get("content-type", "").split(";")[0]
    if content_type not in {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "video/webm"}:
        raise HTTPException(415, "Unsupported recording format.")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Recording is too large. Limit it to 60 seconds.")
    if not data:
        raise HTTPException(422, "The recording is empty. Check your microphone.")
    try:
        return await asyncio.to_thread(transcribe, bytes(data))
    except ImportError as error:
        raise HTTPException(503, "Speech dependencies are missing. Install requirements.txt and restart Sentinel.") from error

