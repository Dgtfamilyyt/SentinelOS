"use strict";

const $ = (id) => document.getElementById(id);
const transcript = $("transcript");
const messageInput = $("messageInput");
const coreOrbit = $("coreOrbit");
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const saved = {
    get(key) { try { return localStorage.getItem(`sentinel-${key}`); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(`sentinel-${key}`, value); } catch { /* Storage may be blocked. */ } },
};
const state = {
    busy: false, controller: null, session: null, requestCount: 0,
    voice: saved.get("voice-conversation") === "enabled", recognition: null,
    listening: false, speaking: false, voiceAborted: false, finalVoice: "",
    phase: "CONNECTING", started: 0, timer: null, operation: false, modelsRefreshing: false,
};
const sessionStartedAt = Date.now();
const phases = {routing: "ROUTING", starting: "STARTING OLLAMA", loading: "LOADING MODEL", thinking: "MODEL THINKING", generating: "GENERATING RESPONSE", tool: "RUNNING TOOL"};

async function api(path, options = {}) {
    const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
    const data = await response.json();
    if (!response.ok) throw Object.assign(new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || data.message || "Request could not be completed."), {code: data.detail?.code || data.code});
    return data;
}

function resizeInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
    $("characterCount").textContent = `${messageInput.value.length.toLocaleString()} / 20,000`;
}

function scrollTranscript(force = false) {
    if (force || transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 140) transcript.scrollTop = transcript.scrollHeight;
}

function announce(text) { $("streamAnnouncement").textContent = text; }

function createMessage(role, content, options = {}) {
    const article = document.createElement("article");
    article.className = `message message-${role === "user" ? "user" : "sentinel"}`;
    article.classList.toggle("message-tool", options.kind === "tool");
    article.classList.toggle("message-error", Boolean(options.error));
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const speaker = document.createElement("span");
    speaker.className = "speaker";
    speaker.textContent = role === "user" ? "OPERATOR" : "SENTINEL";
    const status = document.createElement("span");
    status.className = "message-status";
    status.textContent = options.status && options.status !== "complete" ? options.status : "";
    meta.append(speaker, status);
    const body = document.createElement("div");
    body.className = "message-body";
    const text = document.createElement("p");
    text.textContent = content;
    body.append(text);
    if (role !== "user") {
        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = "copy-message";
        copy.textContent = "COPY";
        copy.setAttribute("aria-label", "Copy Sentinel response");
        copy.addEventListener("click", async () => {
            try { await navigator.clipboard.writeText(text.textContent); copy.textContent = "COPIED"; }
            catch { copy.textContent = "FAILED"; }
            setTimeout(() => { copy.textContent = "COPY"; }, 1200);
        });
        body.append(copy);
    }
    article.append(meta, body);
    transcript.append(article);
    scrollTranscript();
    return {article, text, status, body};
}

function syncVoiceVisual() {
    coreOrbit.classList.toggle("listening", state.listening);
    coreOrbit.classList.toggle("speaking", state.speaking);
    $("voiceStatus").textContent = state.listening ? "Listening" : state.speaking ? "Speaking" : SpeechRecognition ? "Ready" : "Unavailable";
    updateControls();
}

function setConnection(kind, detail) {
    $("coreStatus").classList.remove("online", "offline", "standby");
    $("coreStatus").classList.add(kind === "busy" ? "online" : kind);
    $("coreStatus").lastChild.textContent = ` CORE ${kind === "busy" ? "ACTIVE" : kind.toUpperCase()}`;
    coreOrbit.classList.toggle("active", kind === "busy");
    coreOrbit.classList.toggle("error", kind === "offline");
    $("linkState").textContent = kind === "busy" ? state.phase : kind === "offline" ? "LINK ERROR" : "LINK READY";
    $("connectionCopy").textContent = detail;
}

function updateControls() {
    const locked = state.busy || state.operation || !state.session;
    for (const id of ["sendButton", "clearButton", "newChatButton", "sessionSelect", "modelSelect", "refreshModels"]) $(id).disabled = locked;
    $("modelSelect").disabled = $("refreshModels").disabled = locked || state.modelsRefreshing || state.listening || state.speaking;
    document.querySelectorAll("[data-prompt]").forEach((button) => { button.disabled = locked; });
    $("stopButton").hidden = !state.busy && !state.speaking && !state.listening;
}

function setBusy(busy) {
    state.busy = busy;
    $("thinkingIndicator").hidden = !busy;
    updateControls();
    clearInterval(state.timer);
    if (busy) {
        state.started = performance.now();
        state.phase = "CONNECTING";
        const tick = () => { $("thinkingCopy").textContent = `${state.phase} // ${((performance.now() - state.started) / 1000).toFixed(1)}S`; };
        tick();
        state.timer = setInterval(tick, 100);
        setConnection("busy", "Connecting to Sentinel.");
    }
}

function stopSpeech() {
    state.speaking = false;
    window.speechSynthesis?.cancel();
    syncVoiceVisual();
}

function stopAll() {
    state.voiceAborted = true;
    state.finalVoice = "";
    state.recognition?.abort();
    state.controller?.abort();
    stopSpeech();
}

function speak(text) {
    if (!state.voice || !window.speechSynthesis || !text) return;
    stopSpeech();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onstart = () => { state.speaking = true; syncVoiceVisual(); };
    utterance.onend = utterance.onerror = () => { state.speaking = false; syncVoiceVisual(); };
    window.speechSynthesis.speak(utterance);
}

function recoveryActions(message, rawMessage, code) {
    const actions = document.createElement("div");
    actions.className = "recovery-actions";
    function action(label, callback) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "quiet-button";
        button.textContent = label;
        button.addEventListener("click", async () => {
            if (state.busy) return;
            button.disabled = true;
            try { await callback(); }
            catch (error) { announce(error.message); message.status.textContent = error.message; }
            finally { button.disabled = false; }
        });
        actions.append(button);
    }
    action("Retry", () => sendMessage(rawMessage));
    if (code === "model_missing") {
        const hint = document.createElement("p");
        hint.className = "control-note";
        hint.textContent = "Choose an installed model, or install the missing model with Ollama, then refresh the list.";
        message.body.append(hint);
        action("Refresh models", refreshModels);
    }
    if (["ollama_unavailable", "runtime_unavailable", "startup_failed", "runtime_missing"].includes(code)) {
        action("Start Ollama", async () => {
            await api("/api/runtime/start", {method: "POST"});
            await refreshModels();
            await checkHealth();
            message.status.textContent = "Ollama started. Retry your message.";
        });
    }
    message.body.append(actions);
}

// A single decoder preserves UTF-8 characters split between network chunks.
async function readEvents(response, onEvent) {
    if (!response.body) throw new Error("Streaming is unavailable in this browser.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    try {
        while (true) {
            const {value, done} = await reader.read();
            pending += done ? decoder.decode() : decoder.decode(value, {stream: true});
            let boundary;
            while ((boundary = pending.indexOf("\n")) !== -1) {
                const line = pending.slice(0, boundary).trim();
                pending = pending.slice(boundary + 1);
                if (line) onEvent(JSON.parse(line));
            }
            if (done) break;
        }
        if (pending.trim()) onEvent(JSON.parse(pending));
    } catch (error) {
        try { await reader.cancel(); } catch { /* The request may already be aborted. */ }
        throw error;
    } finally { reader.releaseLock(); }
}

async function sendMessage(rawMessage) {
    const message = rawMessage.trim();
    if (!message || state.busy || state.operation || !state.session) return;
    stopSpeech();
    state.voiceAborted = true;
    state.recognition?.abort();
    createMessage("user", message);
    const answer = createMessage("assistant", "", {status: "Receiving"});
    answer.article.setAttribute("aria-busy", "true");
    scrollTranscript(true);
    messageInput.value = "";
    resizeInput();
    state.controller = new AbortController();
    setBusy(true);
    state.requestCount += 1;
    $("requestCounter").textContent = `REQUESTS ${String(state.requestCount).padStart(3, "0")}`;
    let completed = false;
    let resultReceived = false;
    let successful = false;
    let metrics = {};
    try {
        const response = await fetch("/api/chat/stream", {
            method: "POST", headers: {"Content-Type": "application/json"},
            signal: state.controller.signal,
            body: JSON.stringify({message, session_id: state.session, model: $("modelSelect").value || null}),
        });
        if (!response.ok) {
            const error = await response.json();
            throw Object.assign(new Error(typeof error.detail === "string" ? error.detail : error.detail?.message || error.message || "Request failed."), {code: error.detail?.code || error.code});
        }
        await readEvents(response, (event) => {
            if (event.type === "status") {
                state.phase = phases[event.stage] || "PROCESSING";
                setConnection("busy", event.model ? `${state.phase.toLowerCase()} · ${event.model}` : state.phase.toLowerCase());
                announce(state.phase);
            } else if (event.type === "delta") {
                answer.text.textContent += event.text;
                scrollTranscript();
            } else if (event.type === "result") {
                answer.text.textContent = event.reply;
                answer.article.classList.toggle("message-tool", event.kind === "tool");
                resultReceived = true;
            } else if (event.type === "error") {
                throw Object.assign(new Error(event.message), {code: event.code});
            } else if (event.type === "done") {
                completed = true;
                metrics = event.metrics || {};
                if (event.session_id) { state.session = event.session_id; saved.set("session", state.session); }
            }
        });
        if (!completed || !resultReceived) throw new Error("The connection ended before the response completed. You can retry.");
        const elapsed = `${((performance.now() - state.started) / 1000).toFixed(1)}s`;
        answer.status.textContent = metrics.finish_reason === "length" ? `${elapsed} · Reply limit reached` : elapsed;
        if (Number.isFinite(metrics.input_tokens) && Number.isFinite(metrics.output_tokens)) {
            const usage = document.createElement("p");
            usage.className = "usage-note";
            usage.textContent = `${metrics.input_tokens.toLocaleString()} input · ${metrics.output_tokens.toLocaleString()} output tokens · ${metrics.model_calls ?? 0} model calls${metrics.model ? ` · ${metrics.model}` : ""}`;
            answer.body.append(usage);
        }
        announce("Response complete.");
        successful = true;
    } catch (error) {
        if (error.name === "AbortError") {
            answer.status.textContent = "Stopped · partial response";
            if (!answer.text.textContent) answer.text.textContent = "Response stopped.";
            announce("Response stopped.");
        } else {
            answer.article.classList.add("message-error");
            answer.status.textContent = "Failed";
            answer.text.textContent += `${answer.text.textContent ? "\n\n" : ""}${error.message}`;
            recoveryActions(answer, message, error.code);
            announce(error.message);
        }
    } finally {
        state.controller = null;
        answer.article.setAttribute("aria-busy", "false");
        setBusy(false);
        if (successful) speak(answer.text.textContent);
        await Promise.allSettled([refreshSessions(), checkHealth(), refreshModels()]);
    }
}

async function refreshSessions() {
    const data = await api("/api/sessions");
    const select = $("sessionSelect");
    select.replaceChildren();
    for (const session of data.sessions) {
        const option = document.createElement("option");
        option.value = session.id;
        option.textContent = session.title || "New conversation";
        select.append(option);
        if (session.id === state.session) $("conversationTitle").textContent = session.title || "New conversation";
    }
    select.value = state.session || "";
    return data.sessions;
}

async function loadSession(id) {
    stopAll();
    const session = await api(`/api/sessions/${encodeURIComponent(id)}`);
    state.session = session.id;
    saved.set("session", session.id);
    transcript.replaceChildren();
    for (const message of session.messages) createMessage(message.role, message.content, {kind: message.kind, status: message.status, error: message.status === "error"});
    if (!session.messages.length) createMessage("assistant", "Ready when you are. Ask a question, give a directive, or tap the microphone.");
    $("conversationTitle").textContent = session.title || "New conversation";
    $("sessionSelect").value = session.id;
    scrollTranscript(true);
}

async function newSession() {
    const session = await api("/api/sessions", {method: "POST", body: "{}"});
    await loadSession(session.id);
    await refreshSessions();
}

async function sessionOperation(operation) {
    if (state.busy || state.operation) return;
    state.operation = true;
    updateControls();
    try { await operation(); }
    catch (error) { createMessage("assistant", error.message, {error: true}); }
    finally { state.operation = false; updateControls(); }
}

async function refreshModels() {
    if (state.modelsRefreshing) return;
    state.modelsRefreshing = true;
    updateControls();
    try {
    const previous = $("modelSelect").value || saved.get("model") || "";
    const data = await api("/api/models");
    const select = $("modelSelect");
    select.replaceChildren(new Option("Automatic routing", ""));
    for (const model of data.models) {
        if (model.installed) select.append(new Option(model.name, model.name));
    }
    select.value = Array.from(select.options).some((option) => option.value === previous) ? previous : "";
    saved.set("model", select.value);
    $("modelNote").textContent = data.online ? "Installed models shown. Automatic chooses by task." : "Ollama is on standby. Models refresh after startup.";
    } finally { state.modelsRefreshing = false; updateControls(); }
}

async function refreshMemories() {
    const data = await api("/api/memories");
    $("memoryList").replaceChildren();
    for (const memory of data.memories) {
        const item = document.createElement("li");
        const text = document.createElement("span");
        text.textContent = memory.content;
        const forget = document.createElement("button");
        forget.type = "button";
        forget.className = "quiet-button";
        forget.textContent = "Forget";
        forget.setAttribute("aria-label", `Forget: ${memory.content}`);
        forget.addEventListener("click", async () => {
            forget.disabled = true;
            try { await api(`/api/memories/${encodeURIComponent(memory.id)}`, {method: "DELETE"}); await refreshMemories(); $("memoryFeedback").textContent = "Memory forgotten."; }
            catch (error) { $("memoryFeedback").textContent = error.message; forget.disabled = false; }
        });
        item.append(text, forget);
        $("memoryList").append(item);
    }
}

async function checkHealth() {
    try {
        const health = await api("/api/health");
        $("versionValue").textContent = `v${health.version}`;
        $("toolCount").textContent = String(health.tools.length).padStart(2, "0");
        $("ollamaStatus").textContent = health.ollama === "online" ? "Online" : "Auto-start";
        if (!state.busy) setConnection(health.ollama === "online" ? "online" : "standby", health.ollama === "online" ? "Local intelligence ready." : "Ollama starts automatically when a request needs a model.");
    } catch {
        $("ollamaStatus").textContent = "Unavailable";
        if (!state.busy) setConnection("offline", "Cannot reach the Sentinel server. Check the local server and reload.");
    }
}

function configureVoice() {
    const supported = Boolean(SpeechRecognition && window.speechSynthesis);
    state.voice = state.voice && supported;
    $("voiceToggle").disabled = !supported;
    $("voiceToggle").setAttribute("aria-checked", String(state.voice));
    $("micButton").disabled = !SpeechRecognition;
    if (!SpeechRecognition) { $("micButton").title = "Voice input is unavailable in this browser. You can still type."; $("voiceFeedback").textContent = "Voice input is unavailable in this browser. You can still type."; syncVoiceVisual(); return; }
    const recognition = new SpeechRecognition();
    state.recognition = recognition;
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onstart = () => { state.listening = true; $("voiceFeedback").textContent = "Listening. Tap the microphone to finish, or Escape to cancel."; $("micButton").setAttribute("aria-pressed", "true"); syncVoiceVisual(); };
    recognition.onresult = (event) => {
        if (state.voiceAborted) return;
        messageInput.value = Array.from(event.results).map((result) => result[0].transcript).join(" ").slice(0, 20000);
        state.finalVoice = Array.from(event.results).filter((result) => result.isFinal).map((result) => result[0].transcript).join(" ").slice(0, 20000);
        resizeInput();
    };
    recognition.onerror = (event) => {
        state.voiceAborted = true;
        state.finalVoice = "";
        $("voiceFeedback").textContent = event.error === "not-allowed" ? "Microphone permission was denied. Enable it in browser settings or type your message." : "Voice input ended. Type your message or try the microphone again.";
    };
    recognition.onend = () => {
        state.listening = false;
        $("micButton").setAttribute("aria-pressed", "false");
        syncVoiceVisual();
        const finalText = state.finalVoice;
        state.finalVoice = "";
        if (!state.voiceAborted) $("voiceFeedback").textContent = state.voice && finalText ? "Voice message sent." : "Review the transcript, then press Transmit.";
        if (state.voice && !state.voiceAborted && finalText && !state.busy) sendMessage(finalText);
    };
    syncVoiceVisual();
}

function initCoreVisualization() {
    const canvas = $("coreCanvas");
    const context = canvas.getContext("2d");
    if (!context) return;
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
    const particles = Array.from({length: 560}, (_, i) => {
        const y = 1 - i / 559 * 2;
        const r = Math.sqrt(1 - y * y);
        const angle = Math.PI * (3 - Math.sqrt(5)) * i;
        return {x: Math.cos(angle) * r, y, z: Math.sin(angle) * r, size: 0.45 + Math.random() * 1.35, phase: Math.random() * Math.PI * 2};
    });
    let size = 1;
    let pointer = 0;
    function resize() {
        size = Math.max(1, canvas.getBoundingClientRect().width);
        const dpr = Math.min(devicePixelRatio || 1, 2);
        canvas.width = canvas.height = Math.round(size * dpr);
        context.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function render(time) {
        const t = reducedMotion.matches ? 0 : time;
        context.clearRect(0, 0, size, size);
        const center = size / 2;
        const pulse = state.speaking ? 1 + Math.sin(t * 0.008) * 0.06 : 1;
        const radius = size * 0.32 * pulse;
        const angle = t * (state.busy ? 0.00018 : 0.000065) + pointer;
        const glow = context.createRadialGradient(center, center, 0, center, center, radius);
        glow.addColorStop(0, state.listening ? "rgba(110, 229, 210, .3)" : "rgba(255, 155, 46, .25)");
        glow.addColorStop(1, "rgba(255, 106, 0, 0)");
        context.fillStyle = glow;
        context.fillRect(0, 0, size, size);
        for (const p of particles) {
            const x = p.x * Math.cos(angle) - p.z * Math.sin(angle);
            const z = p.x * Math.sin(angle) + p.z * Math.cos(angle);
            const depth = (z + 1) / 2;
            context.beginPath();
            context.fillStyle = state.listening ? `rgba(122, 231, 211, ${0.18 + depth * 0.72})` : `rgba(255, ${Math.round(105 + depth * 90)}, 35, ${0.18 + depth * 0.72})`;
            context.arc(center + x * radius, center + p.y * radius, p.size * (0.55 + depth) * (0.85 + Math.sin(t * 0.002 + p.phase) * 0.15), 0, Math.PI * 2);
            context.fill();
        }
        context.save();
        context.translate(center, center);
        context.rotate(t * 0.00016);
        context.strokeStyle = "rgba(255, 161, 60, .6)";
        for (let i = 0; i < 7; i++) {
            context.beginPath();
            context.arc(0, 0, radius * (0.18 + i * 0.055), i * 0.7, i * 0.7 + Math.PI * 1.1);
            context.stroke();
        }
        context.restore();
        if (!reducedMotion.matches) requestAnimationFrame(render);
    }
    coreOrbit.addEventListener("pointermove", (event) => { if (!reducedMotion.matches) pointer = (event.clientX - coreOrbit.getBoundingClientRect().left) / size - 0.5; });
    coreOrbit.addEventListener("pointerleave", () => { pointer = 0; });
    new ResizeObserver(() => { resize(); if (reducedMotion.matches) render(0); }).observe(canvas);
    new MutationObserver(() => { if (reducedMotion.matches) render(0); }).observe(coreOrbit, {attributes: true, attributeFilter: ["class"]});
    reducedMotion.addEventListener("change", () => { if (!reducedMotion.matches) requestAnimationFrame(render); });
    resize();
    requestAnimationFrame(render);
}

$("composer").addEventListener("submit", (event) => { event.preventDefault(); sendMessage(messageInput.value); });
messageInput.addEventListener("input", resizeInput);
messageInput.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("composer").requestSubmit(); } });
$("stopButton").addEventListener("click", stopAll);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") stopAll(); });
$("micButton").addEventListener("click", async () => {
    if (!state.recognition) return;
    if (state.listening) { state.recognition.stop(); return; }
    const wasBusy = state.busy;
    stopAll();
    if (wasBusy) { announce("Response stopped. Tap the microphone again to speak."); return; }
    state.voiceAborted = false;
    state.finalVoice = "";
    try { state.recognition.start(); } catch { announce("Microphone is not ready. Try again."); }
});
$("voiceToggle").addEventListener("click", () => {
    state.voice = !state.voice;
    $("voiceToggle").setAttribute("aria-checked", String(state.voice));
    saved.set("voice-conversation", state.voice ? "enabled" : "disabled");
    if (!state.voice) { state.voiceAborted = true; stopSpeech(); }
});
$("newChatButton").addEventListener("click", () => sessionOperation(newSession));
$("sessionSelect").addEventListener("change", () => sessionOperation(() => loadSession($("sessionSelect").value)));
$("clearButton").addEventListener("click", () => sessionOperation(async () => {
    if (!window.confirm("Delete this conversation from this computer? Saved memories will remain.")) return;
    stopAll();
    await api(`/api/sessions/${encodeURIComponent(state.session)}`, {method: "DELETE"});
    state.session = null;
    saved.set("session", "");
    await newSession();
}));
$("modelSelect").addEventListener("change", () => saved.set("model", $("modelSelect").value));
$("refreshModels").addEventListener("click", async () => { try { await refreshModels(); } catch (error) { $("modelNote").textContent = error.message; } });
$("memoryForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("memoryInput");
    if (!input.value.trim()) return;
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try { await api("/api/memories", {method: "POST", body: JSON.stringify({content: input.value.trim()})}); input.value = ""; await refreshMemories(); $("memoryFeedback").textContent = "Remembered for future requests."; }
    catch (error) { $("memoryFeedback").textContent = error.message; }
    finally { button.disabled = false; }
});
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => sendMessage(button.dataset.prompt)));

async function initialize() {
    configureVoice();
    initCoreVisualization();
    resizeInput();
    updateControls();
    const tick = () => {
        $("systemClock").textContent = new Date().toLocaleTimeString([], {hour12: false});
        const seconds = Math.floor((Date.now() - sessionStartedAt) / 1000);
        $("sessionTime").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    };
    tick();
    setInterval(tick, 1000);
    await sessionOperation(async () => {
        const sessions = await refreshSessions();
        const last = sessions.find((session) => session.id === saved.get("session")) || sessions[0];
        if (last) await loadSession(last.id); else await newSession();
    });
    const results = await Promise.allSettled([checkHealth(), refreshModels(), refreshMemories()]);
    if (results[1].status === "rejected") $("modelNote").textContent = "Could not load models. Use Refresh models to retry.";
    if (results[2].status === "rejected") $("memoryFeedback").textContent = "Could not load memories. Reload to retry.";
    messageInput.focus();
}
initialize();
