import io
import wave
from unittest.mock import Mock

from fastapi.testclient import TestClient

from api.app import create_app


def test_reject_empty_and_unsupported_recordings():
    with TestClient(create_app(command_center=Mock())) as client:
        assert client.post('/api/voice/transcribe', content=b'', headers={'content-type': 'audio/webm'}).status_code == 422
        assert client.post('/api/voice/transcribe', content=b'bad', headers={'content-type': 'text/plain'}).status_code == 415


def test_audio_is_passed_to_local_transcriber(monkeypatch):
    worker = Mock(return_value={'text': 'hello Sentinel'})
    monkeypatch.setattr('api.voice.transcribe', worker)
    with TestClient(create_app(command_center=Mock())) as client:
        response = client.post('/api/voice/transcribe', content=b'recording', headers={'content-type': 'audio/webm;codecs=opus'})
        assert response.json() == {'text': 'hello Sentinel'}
        worker.assert_called_once_with(b'recording')


def test_invalid_audio_gives_actionable_error():
    with TestClient(create_app(command_center=Mock())) as client:
        response = client.post('/api/voice/transcribe', content=b'bad', headers={'content-type': 'audio/webm'})
        assert response.status_code == 422
        assert 'decoded' in response.json()['detail']


def test_recording_duration_is_limited_before_inference():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * (62 * 16000))
    with TestClient(create_app(command_center=Mock())) as client:
        response = client.post('/api/voice/transcribe', content=buffer.getvalue(), headers={'content-type': 'audio/wav'})
        assert response.status_code == 413
