const transcript = document.querySelector("#transcript");
const composer = document.querySelector("#composer");
const messageInput = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const micButton = document.querySelector("#micButton");
const clearButton = document.querySelector("#clearButton");
const voiceToggle = document.querySelector("#voiceToggle");
const thinkingIndicator = document.querySelector("#thinkingIndicator");
const characterCount = document.querySelector("#characterCount");
const coreStatus = document.querySelector("#coreStatus");
const coreOrbit = document.querySelector("#coreOrbit");
const coreCanvas = document.querySelector("#coreCanvas");
const thinkingCopy = document.querySelector("#thinkingCopy");
const linkState = document.querySelector("#linkState");
const connectionCopy = document.querySelector("#connectionCopy");
const systemClock = document.querySelector("#systemClock");
const versionValue = document.querySelector("#versionValue");
const toolCount = document.querySelector("#toolCount");
const sessionTime = document.querySelector("#sessionTime");
const voiceStatus = document.querySelector("#voiceStatus");
const requestCounter = document.querySelector("#requestCounter");
const ollamaStatus = document.querySelector("#ollamaStatus");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const sessionStartedAt = Date.now();
let recognition = null;
let isBusy = false;
let requestCount = 0;
let voiceEnabled = localStorage.getItem("sentinel-voice") === "enabled";
let processingStartedAt = 0;
let processingTimer = null;

function formatClock(date) {
    return new Intl.DateTimeFormat([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    }).format(date);
}

function formatElapsed(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function updateTime() {
    systemClock.textContent = formatClock(new Date());
    sessionTime.textContent = formatElapsed(Date.now() - sessionStartedAt);
}

function resizeInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
    characterCount.textContent = `${messageInput.value.length.toLocaleString()} / 20,000`;
}

function setConnectionState(state, detail) {
    coreStatus.classList.remove("online", "offline", "standby");
    coreOrbit.classList.remove("active", "error");

    if (state === "online") {
        coreStatus.classList.add("online");
        coreStatus.lastChild.textContent = " CORE ONLINE";
        linkState.textContent = "LINK READY";
    } else if (state === "busy") {
        coreStatus.classList.add("online");
        coreStatus.lastChild.textContent = " CORE ACTIVE";
        coreOrbit.classList.add("active");
        linkState.textContent = "PROCESSING";
    } else if (state === "standby") {
        coreStatus.classList.add("standby");
        coreStatus.lastChild.textContent = " CORE STANDBY";
        linkState.textContent = "LINK READY";
    } else {
        coreStatus.classList.add("offline");
        coreStatus.lastChild.textContent = " CORE OFFLINE";
        coreOrbit.classList.add("error");
        linkState.textContent = "LINK ERROR";
    }

    connectionCopy.textContent = detail;
}

function createMessage(role, content, options = {}) {
    const article = document.createElement("article");
    const meta = document.createElement("div");
    const speaker = document.createElement("span");
    const time = document.createElement("time");
    const body = document.createElement("div");
    const text = document.createElement(options.preformatted ? "pre" : "p");

    article.className = `message message-${role}`;
    if (options.kind === "tool") article.classList.add("message-tool");
    if (options.error) article.classList.add("message-error");

    meta.className = "message-meta";
    speaker.className = "speaker";
    speaker.textContent = role === "user" ? "OPERATOR" : "SENTINEL";
    time.dateTime = new Date().toISOString();
    time.textContent = options.elapsed
        ? `${formatClock(new Date())} // ${options.elapsed.toFixed(1)}S`
        : formatClock(new Date());

    body.className = "message-body";
    text.textContent = content;
    body.append(text);

    if (role !== "user") {
        const copyButton = document.createElement("button");
        copyButton.className = "copy-message";
        copyButton.type = "button";
        copyButton.textContent = "COPY";
        copyButton.setAttribute("aria-label", "Copy Sentinel response");
        copyButton.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(content);
                copyButton.textContent = "COPIED";
                setTimeout(() => { copyButton.textContent = "COPY"; }, 1200);
            } catch {
                copyButton.textContent = "FAILED";
            }
        });
        body.append(copyButton);
    }

    meta.append(speaker, time);
    article.append(meta, body);
    transcript.append(article);
    transcript.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
}

function setBusy(busy) {
    isBusy = busy;
    sendButton.disabled = busy;
    clearButton.disabled = busy;
    thinkingIndicator.hidden = !busy;

    document.querySelectorAll("[data-prompt]").forEach((button) => {
        button.disabled = busy;
    });

    if (busy) {
        processingStartedAt = Date.now();
        const updateProcessingCopy = () => {
            const elapsed = (Date.now() - processingStartedAt) / 1000;
            let phase = "WAKING LOCAL CORE";
            if (elapsed >= 3) phase = "ROUTING MODEL";
            if (elapsed >= 8) phase = "GENERATING RESPONSE";
            if (elapsed >= 20) phase = "DEEP ANALYSIS ACTIVE";
            thinkingCopy.textContent = `${phase} // ${elapsed.toFixed(1)}S`;
        };
        updateProcessingCopy();
        processingTimer = setInterval(updateProcessingCopy, 100);
        setConnectionState("busy", "Sentinel is routing and processing the request.");
    } else {
        clearInterval(processingTimer);
        processingTimer = null;
        messageInput.focus();
    }
}

function getPreferredVoice() {
    const voices = window.speechSynthesis?.getVoices() || [];

    return voices.find((voice) => voice.lang?.toLowerCase().startsWith("en")) || voices[0];
}

function speak(text) {
    if (!voiceEnabled || !window.speechSynthesis || !text) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 4000));
    utterance.voice = getPreferredVoice();
    utterance.rate = 1;
    utterance.pitch = 0.92;
    window.speechSynthesis.speak(utterance);
}

async function sendMessage(rawMessage) {
    const message = rawMessage.trim();
    if (!message || isBusy) return;

    createMessage("user", message);
    messageInput.value = "";
    resizeInput();
    setBusy(true);
    requestCount += 1;
    requestCounter.textContent = `REQUESTS ${String(requestCount).padStart(3, "0")}`;
    const requestStartedAt = performance.now();

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message }),
        });
        const payload = await response.json();

        if (!response.ok) {
            throw new Error(payload.detail || "Sentinel request failed.");
        }

        createMessage("sentinel", payload.reply, {
            kind: payload.kind,
            preformatted: payload.kind === "tool",
            elapsed: (performance.now() - requestStartedAt) / 1000,
        });
        speak(payload.reply);
    } catch (error) {
        const detail = error instanceof Error ? error.message : "Unknown interface error.";
        createMessage("sentinel", detail, { error: true });
        setConnectionState("offline", "The local API did not complete the request.");
    } finally {
        setBusy(false);
        checkHealth();
    }
}

async function clearSession() {
    if (isBusy) return;

    try {
        const response = await fetch("/api/session", { method: "DELETE" });
        if (!response.ok) throw new Error("Session clear failed.");

        window.speechSynthesis?.cancel();
        transcript.replaceChildren();
        createMessage("sentinel", "Session memory cleared. Command channel ready.");
        requestCount = 0;
        requestCounter.textContent = "REQUESTS 000";
    } catch (error) {
        createMessage("sentinel", error.message, { error: true });
    }
}

function configureVoice() {
    const speechOutputSupported = "speechSynthesis" in window;
    const speechInputSupported = Boolean(SpeechRecognition);

    voiceToggle.disabled = !speechOutputSupported;
    voiceEnabled = voiceEnabled && speechOutputSupported;
    voiceToggle.setAttribute("aria-checked", String(voiceEnabled));
    voiceStatus.textContent = speechInputSupported ? "Ready" : "Output only";

    if (!speechInputSupported) {
        micButton.disabled = true;
        micButton.title = "Voice input is not supported by this browser";
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.addEventListener("start", () => {
        micButton.setAttribute("aria-pressed", "true");
        voiceStatus.textContent = "Listening";
    });

    recognition.addEventListener("result", (event) => {
        const transcriptText = Array.from(event.results)
            .map((result) => result[0].transcript)
            .join("");
        messageInput.value = transcriptText;
        resizeInput();
    });

    recognition.addEventListener("end", () => {
        micButton.setAttribute("aria-pressed", "false");
        voiceStatus.textContent = "Ready";
        messageInput.focus();
    });

    recognition.addEventListener("error", () => {
        micButton.setAttribute("aria-pressed", "false");
        voiceStatus.textContent = "Unavailable";
    });
}

async function checkHealth() {
    try {
        const response = await fetch("/api/health");
        if (!response.ok) throw new Error("Health request failed");

        const health = await response.json();
        versionValue.textContent = `v${health.version}`;
        toolCount.textContent = String(health.tools.length).padStart(2, "0");
        ollamaStatus.textContent = health.ollama === "online" ? "Online" : "Auto-start";
        if (health.ollama === "online") {
            setConnectionState("online", "Local model runtime online. Command channel established.");
        } else {
            setConnectionState("standby", "Ollama is standing by and will start on the first model request.");
        }
    } catch {
        ollamaStatus.textContent = "Unavailable";
        versionValue.textContent = "—";
        toolCount.textContent = "—";
        setConnectionState("offline", "Start the local Sentinel API to establish a link.");
    }
}

function initCoreVisualization() {
    if (!coreCanvas) return;

    const context = coreCanvas.getContext("2d");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const particles = Array.from({ length: 560 }, (_, index) => {
        const y = 1 - (index / 559) * 2;
        const radius = Math.sqrt(1 - y * y);
        const theta = Math.PI * (3 - Math.sqrt(5)) * index;
        return {
            x: Math.cos(theta) * radius,
            y,
            z: Math.sin(theta) * radius,
            size: 0.45 + Math.random() * 1.35,
            phase: Math.random() * Math.PI * 2,
        };
    });
    let width = 0;
    let height = 0;
    let pointerX = 0;
    let pointerY = 0;
    let rotationX = -0.14;
    let rotationY = 0;

    const resize = () => {
        const bounds = coreCanvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = Math.max(1, bounds.width);
        height = Math.max(1, bounds.height);
        coreCanvas.width = Math.round(width * dpr);
        coreCanvas.height = Math.round(height * dpr);
        context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const rotatePoint = (point, time) => {
        const ay = rotationY + time * (coreOrbit.classList.contains("active") ? 0.00018 : 0.000065);
        const cosY = Math.cos(ay);
        const sinY = Math.sin(ay);
        const x = point.x * cosY - point.z * sinY;
        const z = point.x * sinY + point.z * cosY;
        const cosX = Math.cos(rotationX);
        const sinX = Math.sin(rotationX);
        return { x, y: point.y * cosX - z * sinX, z: point.y * sinX + z * cosX };
    };

    const render = (time = 0) => {
        context.clearRect(0, 0, width, height);
        rotationX += (pointerY * 0.22 - rotationX) * 0.018;
        rotationY += pointerX * 0.0007;
        const scale = Math.min(width, height) * 0.32;
        const centerX = width / 2;
        const centerY = height / 2;
        const active = coreOrbit.classList.contains("active");
        const glow = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, scale);
        glow.addColorStop(0, active ? "rgba(255, 191, 84, .30)" : "rgba(255, 139, 28, .20)");
        glow.addColorStop(0.45, "rgba(255, 106, 0, .08)");
        glow.addColorStop(1, "rgba(255, 106, 0, 0)");
        context.fillStyle = glow;
        context.fillRect(centerX - scale, centerY - scale, scale * 2, scale * 2);

        particles.forEach((particle) => {
            const point = rotatePoint(particle, time);
            const depth = (point.z + 1) / 2;
            const pulse = 0.72 + Math.sin(time * 0.002 + particle.phase) * 0.28;
            context.beginPath();
            context.fillStyle = `rgba(255, ${Math.round(105 + depth * 90)}, ${Math.round(18 + depth * 34)}, ${0.18 + depth * 0.72})`;
            context.arc(
                centerX + point.x * scale,
                centerY + point.y * scale,
                particle.size * (0.55 + depth) * pulse,
                0,
                Math.PI * 2,
            );
            context.fill();
        });

        context.save();
        context.translate(centerX, centerY);
        context.rotate(time * 0.00016);
        context.strokeStyle = active ? "rgba(255, 193, 94, .74)" : "rgba(255, 132, 28, .52)";
        context.lineWidth = 0.8;
        for (let index = 0; index < 7; index += 1) {
            context.beginPath();
            const radius = scale * (0.18 + index * 0.055);
            context.arc(0, 0, radius, index * 0.7, index * 0.7 + Math.PI * 1.1);
            context.stroke();
        }
        context.restore();

        if (!reducedMotion) requestAnimationFrame(render);
    };

    coreOrbit.addEventListener("pointermove", (event) => {
        const bounds = coreOrbit.getBoundingClientRect();
        pointerX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
        pointerY = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    });
    coreOrbit.addEventListener("pointerleave", () => {
        pointerX = 0;
        pointerY = 0;
    });
    new ResizeObserver(() => {
        resize();
        if (reducedMotion) render();
    }).observe(coreCanvas);
    resize();
    render();
}

composer.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(messageInput.value);
});

messageInput.addEventListener("input", resizeInput);
messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        composer.requestSubmit();
    }
});

micButton.addEventListener("click", () => {
    if (!recognition || isBusy) return;

    if (micButton.getAttribute("aria-pressed") === "true") {
        recognition.stop();
    } else {
        recognition.start();
    }
});

voiceToggle.addEventListener("click", () => {
    voiceEnabled = !voiceEnabled;
    voiceToggle.setAttribute("aria-checked", String(voiceEnabled));
    localStorage.setItem("sentinel-voice", voiceEnabled ? "enabled" : "disabled");

    if (!voiceEnabled) window.speechSynthesis?.cancel();
});

clearButton.addEventListener("click", clearSession);

document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        window.speechSynthesis?.cancel();
        recognition?.stop();
    }
});

configureVoice();
initCoreVisualization();
resizeInput();
updateTime();
setInterval(updateTime, 1000);
checkHealth();
messageInput.focus();
