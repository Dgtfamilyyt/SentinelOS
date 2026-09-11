const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../web/local-voice.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

function setup(getMedia) {
    let stopped = 0, calls = 0;
    const stream = {getTracks: () => [{stop: () => {stopped++;}}]};
    class Recorder {
        static isTypeSupported() {return true;}
        constructor() {this.state='inactive';this.mimeType='audio/webm';}
        start() {this.state='recording';}
        stop() {this.state='inactive';this.ondataavailable({data:new Blob(['audio'])});queueMicrotask(() => this.onstop());}
    }
    const context = vm.createContext({navigator:{mediaDevices:{getUserMedia:getMedia || (async () => stream)}},
        MediaRecorder:Recorder, Blob, AbortController, setTimeout, clearTimeout,
        fetch:async () => {calls++;return {ok:true,json:async () => ({text:'hello'})};}});
    vm.runInContext(source,context);
    return {recognition:vm.runInContext('new LocalSpeechRecognition()',context),stream,
        stopped:()=>stopped,calls:()=>calls};
}

test('record stop transcribes locally and releases microphone',async () => {
    const s=setup();let transcript='',ended=false;
    s.recognition.onresult=e=>{transcript=e.results[0][0].transcript;};
    s.recognition.onend=()=>{ended=true;};
    await s.recognition.start();s.recognition.stop();await flush();
    assert.equal(transcript,'hello');assert.equal(s.calls(),1);assert.ok(s.stopped());assert.ok(ended);
});

test('denied permission reports error and ends without upload',async () => {
    const s=setup(async()=>{throw {name:'NotAllowedError'};});let error;
    s.recognition.onerror=e=>{error=e.error;};
    await s.recognition.start();assert.equal(error,'not-allowed');assert.equal(s.calls(),0);
});

test('cancel before permission resolves closes late microphone without uploading',async () => {
    let grant;const s=setup(()=>new Promise(resolve=>{grant=resolve;}));
    const pending=s.recognition.start();s.recognition.abort();grant(s.stream);await pending;
    assert.equal(s.calls(),0);assert.equal(s.stopped(),1);
});

test('cancel recording discards audio',async () => {
    const s=setup();await s.recognition.start();s.recognition.abort();await flush();
    assert.equal(s.calls(),0);assert.ok(s.stopped());
});
