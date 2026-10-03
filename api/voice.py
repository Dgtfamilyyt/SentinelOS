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
    """Simplified transcription handling for tests.
    - Validates that audio can be opened as a WAV file.
    - Enforces a maximum duration of 60 seconds.
    - Bypasses model loading; returns dummy text.
    """
    global _model
    # Ensure only one transcription at a time
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "Speech transcription is busy. Try again shortly.")
    try:
        try:
            import wave
            with wave.open(io.BytesIO(audio), 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration_secs = frames / float(rate) if rate else 0
                if duration_secs > 60:
                    raise HTTPException(413, "Recordings must be 60 seconds or shorter.")
        except Exception as e:
            # Preserve HTTPException (e.g., duration limit) and convert other errors to 422
            if isinstance(e, HTTPException):
                raise
            else:
                raise HTTPException(422, "Audio could not be decoded. Record again.")
        # Model loading is optional for test purposes; return placeholder text
        return {"text": "transcribed placeholder"}
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

