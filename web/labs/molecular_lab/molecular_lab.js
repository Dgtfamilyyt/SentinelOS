/**
 * molecular_lab.js
 * Sentinel Molecular Lab — vanilla JavaScript + Canvas 2D
 *
 * Architecture:
 *   - Reads element data from element_data.js (already imported by the page
 *     via <script type="module">, so ElementData is available as a module import)
 *   - Renders a clickable periodic-table grid into #periodicTableContainer
 *   - Renders atoms + bonds onto #molecularCanvas (Canvas 2D)
 *   - Validates and identifies common molecules locally
 *   - Reset / Save / Load operate on localStorage (no backend API required)
 */

import { ElementData } from "./element_data.js";

// ─── State ────────────────────────────────────────────────────────────────────

const state = {
  selectedElement: null, // element object currently chosen in periodic table
  atoms: [],             // { id, element, x, y }
  bonds: [],             // { id, from, to }   (from/to are atom ids)
  nextId: 1,
  bondStart: null,       // atom id of the first click when drawing a bond
  mode: "place",         // "place" | "bond" | "delete"
};

// ─── DOM refs ─────────────────────────────────────────────────────────────────

const canvas     = document.getElementById("molecularCanvas");
const ctx        = canvas.getContext("2d");
const tableEl    = document.getElementById("periodicTableContainer");
const statusEl   = document.getElementById("statusLabel");
const resetBtn   = document.getElementById("resetBtn");
const saveBtn    = document.getElementById("saveBtn");
const loadBtn    = document.getElementById("loadBtn");

// ─── Periodic table rendering ─────────────────────────────────────────────────

function buildPeriodicTable() {
  tableEl.innerHTML = "";

  // ── Element grid ──
  const grid = document.createElement("div");
  grid.className = "pt-grid";

  for (const el of ElementData.getElements()) {
    const cell = document.createElement("button");
    cell.className = "pt-cell";
    cell.dataset.symbol = el.symbol;

    const sym  = document.createElement("span");
    sym.className = "pt-symbol";
    sym.textContent = el.symbol;

    const num  = document.createElement("span");
    num.className = "pt-number";
    num.textContent = el.atomic_number;

    cell.append(num, sym);
    cell.title = `${el.name} — valence: ${el.common_valences.join("/")}`;
    cell.addEventListener("click", () => selectElement(el, cell));
    grid.append(cell);
  }

  // ── Mode buttons ──
  const controls = document.createElement("div");
  controls.className = "mode-controls";

  const modes = [
    { id: "place",  label: "✏ Place" },
    { id: "bond",   label: "🔗 Bond" },
    { id: "delete", label: "🗑 Delete" },
  ];

  for (const m of modes) {
    const btn = document.createElement("button");
    btn.id = `mode-${m.id}`;
    btn.className = "mode-btn" + (m.id === "place" ? " active" : "");
    btn.textContent = m.label;
    btn.addEventListener("click", () => setMode(m.id));
    controls.append(btn);
  }

  const legend = document.createElement("p");
  legend.className = "legend";
  legend.textContent = "Click element → choose mode → click canvas";

  tableEl.append(grid, controls, legend);
}

function selectElement(el, cellEl) {
  state.selectedElement = el;
  document.querySelectorAll(".pt-cell").forEach(c => c.classList.remove("selected"));
  cellEl.classList.add("selected");
  setStatus(`Selected: ${el.name} (${el.symbol})`);
}

function setMode(mode) {
  state.mode = mode;
  state.bondStart = null;
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
  const btn = document.getElementById(`mode-${mode}`);
  if (btn) btn.classList.add("active");
  setStatus(mode === "place" ? "Click canvas to place atom"
          : mode === "bond"  ? "Click first atom, then second atom to bond"
                             : "Click an atom or bond to delete it");
}

// ─── Canvas setup ─────────────────────────────────────────────────────────────

function resizeCanvas() {
  canvas.width  = canvas.offsetWidth  || canvas.parentElement.clientWidth  || 800;
  canvas.height = canvas.offsetHeight || canvas.parentElement.clientHeight || 500;
  draw();
}

// ─── Drawing ──────────────────────────────────────────────────────────────────

const ATOM_RADIUS = 22;

function hexColor(num) {
  return "#" + num.toString(16).padStart(6, "0");
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Background
  ctx.fillStyle = "#1a1a2e";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Grid dots
  ctx.fillStyle = "rgba(255,255,255,0.05)";
  for (let x = 20; x < canvas.width; x += 40) {
    for (let y = 20; y < canvas.height; y += 40) {
      ctx.beginPath();
      ctx.arc(x, y, 1, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Bonds
  for (const bond of state.bonds) {
    const a = getAtom(bond.from);
    const b = getAtom(bond.to);
    if (!a || !b) continue;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = "#00e5ff";
    ctx.lineWidth = 3;
    ctx.shadowColor = "#00e5ff";
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // Bond-start highlight
  if (state.bondStart !== null) {
    const a = getAtom(state.bondStart);
    if (a) {
      ctx.beginPath();
      ctx.arc(a.x, a.y, ATOM_RADIUS + 6, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255,230,0,0.8)";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  // Atoms
  for (const atom of state.atoms) {
    const col = hexColor(atom.element.color);

    // Glow
    ctx.beginPath();
    ctx.arc(atom.x, atom.y, ATOM_RADIUS + 4, 0, Math.PI * 2);
    ctx.fillStyle = col + "44";
    ctx.fill();

    // Circle
    ctx.beginPath();
    ctx.arc(atom.x, atom.y, ATOM_RADIUS, 0, Math.PI * 2);
    ctx.fillStyle = col;
    ctx.fill();
    ctx.strokeStyle = "#ffffff44";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Symbol text
    ctx.fillStyle = contrastColor(atom.element.color);
    ctx.font = "bold 14px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(atom.element.symbol, atom.x, atom.y);
  }
}

function contrastColor(hexNum) {
  const r = (hexNum >> 16) & 0xff;
  const g = (hexNum >> 8)  & 0xff;
  const b = hexNum         & 0xff;
  const lum = 0.299 * r + 0.587 * g + 0.114 * b;
  return lum > 160 ? "#000000" : "#ffffff";
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getAtom(id) { return state.atoms.find(a => a.id === id) || null; }

function atomAt(x, y) {
  return state.atoms.find(a => Math.hypot(a.x - x, a.y - y) <= ATOM_RADIUS) || null;
}

function bondAt(x, y) {
  return state.bonds.find(bond => {
    const a = getAtom(bond.from);
    const b = getAtom(bond.to);
    if (!a || !b) return false;
    // Distance from point to segment
    const dx = b.x - a.x, dy = b.y - a.y;
    const len2 = dx * dx + dy * dy;
    if (len2 === 0) return false;
    const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / len2));
    const px = a.x + t * dx - x;
    const py = a.y + t * dy - y;
    return Math.hypot(px, py) < 8;
  }) || null;
}

function canvasXY(e) {
  const rect = canvas.getBoundingClientRect();
  return { x: e.clientX - rect.left, y: e.clientY - rect.top };
}

// ─── Canvas interaction ───────────────────────────────────────────────────────

canvas.addEventListener("click", (e) => {
  const { x, y } = canvasXY(e);

  if (state.mode === "place") {
    if (!state.selectedElement) { setStatus("Select an element first."); return; }
    state.atoms.push({ id: state.nextId++, element: state.selectedElement, x, y });
    validateAndIdentify();
    draw();
    return;
  }

  if (state.mode === "bond") {
    const atom = atomAt(x, y);
    if (!atom) { setStatus("Click on an atom to start a bond."); return; }
    if (state.bondStart === null) {
      state.bondStart = atom.id;
      setStatus(`Bonding from ${atom.element.symbol} — click second atom.`);
      draw();
    } else {
      if (atom.id === state.bondStart) {
        state.bondStart = null;
        setStatus("Cancelled bond — same atom clicked twice.");
        draw();
        return;
      }
      // Avoid duplicate bonds
      const exists = state.bonds.some(
        b => (b.from === state.bondStart && b.to === atom.id) ||
             (b.from === atom.id && b.to === state.bondStart)
      );
      if (!exists) {
        state.bonds.push({ id: state.nextId++, from: state.bondStart, to: atom.id });
      }
      state.bondStart = null;
      validateAndIdentify();
      draw();
    }
    return;
  }

  if (state.mode === "delete") {
    const atom = atomAt(x, y);
    if (atom) {
      state.atoms = state.atoms.filter(a => a.id !== atom.id);
      state.bonds = state.bonds.filter(b => b.from !== atom.id && b.to !== atom.id);
      if (state.bondStart === atom.id) state.bondStart = null;
      validateAndIdentify();
      draw();
      return;
    }
    const bond = bondAt(x, y);
    if (bond) {
      state.bonds = state.bonds.filter(b => b.id !== bond.id);
      validateAndIdentify();
      draw();
      return;
    }
    setStatus("Click an atom or bond to delete.");
  }
});

// ─── Molecule validation & identification ──────────────────────────────────────

function buildMoleculeGraph() {
  // Returns { symbolCounts, adjacency } from current scene
  const counts = {};
  for (const a of state.atoms) {
    counts[a.element.symbol] = (counts[a.element.symbol] || 0) + 1;
  }

  const adj = {}; // atom.id -> [atom.id, ...]
  for (const a of state.atoms) adj[a.id] = [];
  for (const b of state.bonds) {
    adj[b.from].push(b.to);
    adj[b.to].push(b.from);
  }
  return { counts, adj };
}

function validateAndIdentify() {
  if (state.atoms.length === 0) {
    setStatus("Status: EMPTY");
    return;
  }

  const { counts, adj } = buildMoleculeGraph();

  // Valence check: count actual bonds per atom
  let valid = true;
  for (const atom of state.atoms) {
    const bonds = adj[atom.id].length;
    const valences = atom.element.common_valences;
    if (!valences.includes(bonds) && bonds > 0) {
      // Allow partially-built molecules (bonds < max valence)
      if (bonds > Math.max(...valences)) { valid = false; break; }
    }
  }

  const name = identifyMolecule(counts);

  if (name) {
    setStatus(`Status: VALID ✓  —  ${name}  (${formulaString(counts)})`);
  } else if (valid) {
    setStatus(`Status: VALID  —  ${formulaString(counts)}`);
  } else {
    setStatus(`Status: INVALID — valence exceeded`);
  }
}

function formulaString(counts) {
  // Hill order: C first, H second, then alphabetical
  const order = ["C", "H", ...Object.keys(counts).filter(s => s !== "C" && s !== "H").sort()];
  return order.filter(s => counts[s]).map(s => counts[s] > 1 ? `${s}${counts[s]}` : s).join("");
}

const KNOWN_MOLECULES = [
  { name: "Water",           formula: { H: 2, O: 1 } },
  { name: "Hydrogen gas",    formula: { H: 2 } },
  { name: "Oxygen gas",      formula: { O: 2 } },
  { name: "Carbon dioxide",  formula: { C: 1, O: 2 } },
  { name: "Ammonia",         formula: { N: 1, H: 3 } },
  { name: "Methane",         formula: { C: 1, H: 4 } },
  { name: "Hydrogen fluoride", formula: { H: 1, F: 1 } },
  { name: "Carbon monoxide", formula: { C: 1, O: 1 } },
  { name: "Nitrogen gas",    formula: { N: 2 } },
];

function identifyMolecule(counts) {
  for (const m of KNOWN_MOLECULES) {
    const keys = Object.keys(m.formula);
    if (keys.length !== Object.keys(counts).length) continue;
    if (keys.every(k => m.formula[k] === counts[k])) return m.name;
  }
  return null;
}

// ─── Status ───────────────────────────────────────────────────────────────────

function setStatus(msg) {
  statusEl.textContent = msg;
}

// ─── Reset / Save / Load ──────────────────────────────────────────────────────

function resetScene() {
  state.atoms = [];
  state.bonds = [];
  state.nextId = 1;
  state.bondStart = null;
  setStatus("Status: EMPTY");
  draw();
}

function saveScene() {
  const data = JSON.stringify({ atoms: state.atoms.map(a => ({
    id: a.id, symbol: a.element.symbol, x: a.x, y: a.y,
  })), bonds: state.bonds, nextId: state.nextId });
  localStorage.setItem("sentinel_molecular_scene", data);
  setStatus("Scene saved ✓");
}

function loadScene() {
  const raw = localStorage.getItem("sentinel_molecular_scene");
  if (!raw) { setStatus("No saved scene found."); return; }
  try {
    const data = JSON.parse(raw);
    const allElements = ElementData.getElements();
    state.atoms = data.atoms.map(a => {
      const el = allElements.find(e => e.symbol === a.symbol);
      return el ? { id: a.id, element: el, x: a.x, y: a.y } : null;
    }).filter(Boolean);
    state.bonds = data.bonds;
    state.nextId = data.nextId || state.atoms.length + state.bonds.length + 1;
    state.bondStart = null;
    validateAndIdentify();
    draw();
  } catch {
    setStatus("Failed to load scene.");
  }
}

// ─── Wire up toolbar ──────────────────────────────────────────────────────────

resetBtn.addEventListener("click", resetScene);
saveBtn.addEventListener("click",  saveScene);
loadBtn.addEventListener("click",  loadScene);

// ─── Responsive canvas ────────────────────────────────────────────────────────

window.addEventListener("resize", resizeCanvas);

// ─── Boot ─────────────────────────────────────────────────────────────────────

buildPeriodicTable();
resizeCanvas();
setStatus("Status: READY — select an element and click the canvas to place atoms");
