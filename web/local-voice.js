"use strict";

// SpeechRecognition-shaped adapter using browser recording and local Whisper.
class LocalSpeechRecognition {
    constructor() { this.sequence = 0; this.processing = false; }
    async start() {
        const sequence = ++this.sequence;
        this.onrequest?.();
        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}});
            if (sequence !== this.sequence) { stream.getTracks().forEach(track => track.stop()); return; }
            this.stream = stream;
            const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(type => MediaRecorder.isTypeSupported(type));
            const recorder = new MediaRecorder(stream, mimeType ? {mimeType} : undefined);
            this.recorder = recorder;
            const chunks = [];
            recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
            recorder.onerror = () => {
                if (sequence !== this.sequence) return;
                this.onerror?.({error: "audio-capture"});
                this.abort();
            };
            recorder.onstop = async () => {
                clearTimeout(this.timer);
                stream.getTracks().forEach(track => track.stop());
                if (sequence !== this.sequence) return;
                this.processing = true;
                this.onprocessing?.();
                this.controller = new AbortController();
                try {
                    const blob = new Blob(chunks, {type: recorder.mimeType || "audio/webm"});
                    const response = await fetch("/api/voice/transcribe", {method: "POST", body: blob,
                        headers: {"Content-Type": blob.type}, signal: this.controller.signal});
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || "Transcription failed. Try again.");
                    if (sequence !== this.sequence) return;
                    const result = [{transcript: data.text}];
                    result.isFinal = true;
                    this.onresult?.({results: [result]});
                } catch (error) {
                    if (sequence === this.sequence && error.name !== "AbortError") this.onerror?.({error: "transcription", message: error.message});
                } finally {
                    if (sequence === this.sequence) { this.processing = false; this.onend?.(); }
                }
            };
            recorder.start(250);
            this.timer = setTimeout(() => this.stop(), 60000);
            this.onstart?.();
        } catch (error) {
            if (sequence !== this.sequence) return;
            this.stream?.getTracks().forEach(track => track.stop());
            this.onerror?.({error: error.name === "NotAllowedError" ? "not-allowed" : error.name === "NotFoundError" ? "no-device" : "audio-capture"});
            this.onend?.();
        }
    }
    stop() { if (this.recorder?.state === "recording") this.recorder.stop(); }
    abort() {
        ++this.sequence;
        clearTimeout(this.timer);
        this.controller?.abort();
        this.stop();
        this.stream?.getTracks().forEach(track => track.stop());
        this.processing = false;
        this.onend?.();
    }
}
