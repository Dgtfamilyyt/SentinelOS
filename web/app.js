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
const linkState = document.querySelector("#linkState");
const connectionCopy = document.querySelector("#connectionCopy");
const systemClock = document.querySelector("#systemClock");
const versionValue = document.querySelector("#versionValue");
const toolCount = document.querySelector("#toolCount");
const sessionTime = document.querySelector("#sessionTime");
const voiceStatus = document.querySelector("#voiceStatus");
const requestCounter = document.querySelector("#requestCounter");

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const sessionStartedAt = Date.now();
let recognition = null;
let isBusy = false;
let requestCount = 0;
let voiceEnabled = localStorage.getItem("sentinel-voice") === "enabled";

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
    coreStatus.classList.remove("online", "offline");
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
    time.textContent = formatClock(new Date());

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
        setConnectionState("busy", "Sentinel is routing and processing the request.");
    } else {
        setConnectionState("online", "Encrypted local command channel established.");
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
        });
        speak(payload.reply);
    } catch (error) {
        const detail = error instanceof Error ? error.message : "Unknown interface error.";
        createMessage("sentinel", detail, { error: true });
        setConnectionState("offline", "The local API did not complete the request.");
    } finally {
        setBusy(false);
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
        setConnectionState("online", "Encrypted local command channel established.");
    } catch {
        versionValue.textContent = "—";
        toolCount.textContent = "—";
        setConnectionState("offline", "Start the local Sentinel API to establish a link.");
    }
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
resizeInput();
updateTime();
setInterval(updateTime, 1000);
checkHealth();
messageInput.focus();
