import * as THREE from "./vendor/three.module.js";

const API = "/api/molecular";
const SAVE_KEY = "sentinel.molecular-lab.scene.v1";
const host = document.getElementById("sceneHost");
const errorBox = document.getElementById("sceneError");
const elementGrid = document.getElementById("periodicTableContainer");
const state = { elements: [], atoms: [], bonds: [], status: "INCOMPLETE", formula: "", molecule: null,
  mode: "place", selectedElement: null, selectedAtom: null, bondStart: null, pointer: null };

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x0a1012, 22, 46);
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
const target = new THREE.Vector3(0, 0.2, 0);
const spherical = new THREE.Spherical(14, 1.18, 0.12);
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
} catch (error) {
  showError("This browser could not create a WebGL 2 scene. Try a browser with hardware acceleration enabled.");
  throw error;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
host.prepend(renderer.domElement);

scene.add(new THREE.HemisphereLight(0xd8e7ed, 0x11191b, 2.1));
const keyLight = new THREE.PointLight(0xffc17d, 65, 34, 2);
keyLight.position.set(-4, 8, 5);
scene.add(keyLight);
const rimLight = new THREE.PointLight(0x60bbc9, 38, 30, 2);
rimLight.position.set(5, 3, -6);
scene.add(rimLight);
const grid = new THREE.GridHelper(30, 30, 0x34464a, 0x233135);
grid.position.y = -0.02;
grid.material.transparent = true;
grid.material.opacity = 0.55;
scene.add(grid);

const atomGroup = new THREE.Group();
const bondGroup = new THREE.Group();
scene.add(bondGroup, atomGroup);
const raycaster = new THREE.Raycaster();
const pointerNdc = new THREE.Vector2();
const plane = new THREE.Plane();
const pickables = [];
const atomMeshes = new Map();
const bondMeshes = new Map();
const labelNodes = new Map();

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) throw new Error(data?.detail || `Molecular Lab request failed (${response.status})`);
  return data;
}

function buildPeriodicTable() {
  elementGrid.replaceChildren();
  for (const element of state.elements) {
    const button = document.createElement("button");
    button.className = "element";
    button.type = "button";
    button.dataset.symbol = element.symbol;
    button.title = `${element.name} · atomic mass ${element.atomic_mass} · valence ${element.common_valences.join(" / ")}`;
    button.innerHTML = `<span class="num">${element.atomic_number}</span><span class="sym">${element.symbol}</span><span class="name">${element.name}</span>`;
    button.addEventListener("click", () => {
      state.selectedElement = element.symbol;
      state.mode = "place";
      syncControls();
      document.getElementById("selectedElement").textContent = `${element.name} (${element.symbol})`;
      document.getElementById("elementDetail").textContent = `Common valence ${element.common_valences.join(" / ")} · mass ${element.atomic_mass}`;
      setInteractionHint(`Place ${element.name} in the scene`);
    });
    elementGrid.append(button);
  }
}

function setInteractionHint(text) {
  document.getElementById("interactionHint").textContent = text;
  document.getElementById("toolMessage").textContent = text;
}

function syncControls() {
  document.querySelectorAll(".element").forEach((button) => {
    button.classList.toggle("selected", button.dataset.symbol === state.selectedElement);
  });
  document.querySelectorAll(".mode").forEach((button) => button.classList.toggle("active", button.dataset.mode === state.mode));
}

function disposeGroup(group) {
  while (group.children.length) {
    const object = group.children.pop();
    object.parent = null;
    object.geometry?.dispose();
    if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
    else object.material?.dispose();
    object.material?.map?.dispose();
  }
}

function buildBonds() {
  disposeGroup(bondGroup);
  bondMeshes.clear();
  const byId = new Map(state.atoms.map((atom) => [atom.id, atom]));
  for (const bond of state.bonds) {
    const atomA = byId.get(bond.atom_a), atomB = byId.get(bond.atom_b);
    if (!atomA || !atomB) continue;
    const start = new THREE.Vector3(...atomA.position);
    const end = new THREE.Vector3(...atomB.position);
    const delta = end.clone().sub(start);
    const length = delta.length();
    if (length < 0.01) continue;
    const direction = delta.normalize();
    let offset = new THREE.Vector3().crossVectors(direction, new THREE.Vector3(0, 1, 0));
    if (offset.lengthSq() < 0.001) offset.set(1, 0, 0);
    offset.normalize();
    const shifts = bond.order === 1 ? [0] : bond.order === 2 ? [-0.11, 0.11] : [-0.16, 0, 0.16];
    for (const shift of shifts) {
      const geometry = new THREE.CylinderGeometry(0.038, 0.038, length, 12, 1, false);
      const material = new THREE.MeshStandardMaterial({ color: 0xe4ad71, metalness: 0.25, roughness: 0.36, emissive: 0x46280e, emissiveIntensity: 0.28 });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(start).add(end).multiplyScalar(0.5).addScaledVector(offset, shift);
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
      mesh.userData.bondId = bond.id;
      mesh.userData.kind = "bond";
      bondGroup.add(mesh);
      bondMeshes.set(bond.id, mesh);
    }
  }
}

function buildAtoms() {
  disposeGroup(atomGroup);
  atomMeshes.clear();
  pickables.length = 0;
  labelNodes.clear();
  document.getElementById("sceneLabels").replaceChildren();
  for (const atom of state.atoms) {
    const element = state.elements.find((item) => item.symbol === atom.element);
    if (!element) continue;
    const isSelected = atom.id === state.selectedAtom;
    const radius = atom.element === "H" ? 0.37 : atom.element === "He" || atom.element === "Ne" || atom.element === "Ar" ? 0.56 : 0.52;
    const material = new THREE.MeshStandardMaterial({
      color: element.color,
      roughness: 0.28,
      metalness: 0.08,
      emissive: isSelected ? 0x684120 : 0x000000,
      emissiveIntensity: isSelected ? 0.55 : 0,
    });
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 32, 24), material);
    mesh.position.fromArray(atom.position);
    mesh.rotation.set(...atom.rotation);
    mesh.userData.atomId = atom.id;
    mesh.userData.kind = "atom";
    mesh.castShadow = true;
    atomGroup.add(mesh);
    atomMeshes.set(atom.id, mesh);
    pickables.push(mesh);
    const label = document.createElement("span");
    label.className = "atom-label";
    label.textContent = atom.element;
    document.getElementById("sceneLabels").append(label);
    labelNodes.set(atom.id, label);
  }
}

function renderStructure(data) {
  state.atoms = data.atoms || [];
  state.bonds = data.bonds || [];
  state.status = data.status || "INCOMPLETE";
  state.formula = data.formula || "";
  state.molecule = data.molecule || null;
  if (!state.atoms.some((atom) => atom.id === state.selectedAtom)) state.selectedAtom = null;
  buildBonds();
  buildAtoms();

  const statusCard = document.getElementById("statusCard");
  statusCard.className = `status-card status-${state.status.toLowerCase()}`;
  document.getElementById("statusLabel").textContent = state.status;
  document.getElementById("moleculeName").textContent = state.molecule || (state.status === "UNKNOWN" ? "Unknown molecule" : "Unidentified structure");
  document.getElementById("formulaLabel").textContent = state.formula ? state.formula.replace(/\d/g, (digit) => "₀₁₂₃₄₅₆₇₈₉"[Number(digit)]) : "—";
  const composition = document.getElementById("compositionList");
  composition.replaceChildren();
  const names = new Map(state.elements.map((element) => [element.symbol, element.name]));
  const entries = Object.entries(data.composition || {}).sort(([a], [b]) => a.localeCompare(b));
  if (!entries.length) composition.innerHTML = "<li>No atoms yet</li>";
  for (const [symbol, count] of entries) {
    const item = document.createElement("li");
    item.innerHTML = `<span>${count} ${names.get(symbol) || symbol}</span><span>${symbol}${count > 1 ? count : ""}</span>`;
    composition.append(item);
  }
  document.getElementById("validationMessage").textContent = (data.issues || []).join(" ") || (state.molecule ? `${state.molecule} matches a supported connected molecular pattern.` : "Valence constraints are satisfied.");
  document.getElementById("counts").textContent = `${state.atoms.length} ATOMS · ${state.bonds.length} BONDS`;
}

async function applyServerStructure() {
  try { renderStructure(await request("/structure")); }
  catch (error) { showError(error.message); }
}

function resize() {
  const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function updateCamera() {
  camera.position.setFromSpherical(spherical).add(target);
  camera.lookAt(target);
}

function frame() {
  requestAnimationFrame(frame);
  renderer.render(scene, camera);
}

function hitTest(event) {
  const bounds = renderer.domElement.getBoundingClientRect();
  pointerNdc.set(((event.clientX - bounds.left) / bounds.width) * 2 - 1, -((event.clientY - bounds.top) / bounds.height) * 2 + 1);
  raycaster.setFromCamera(pointerNdc, camera);
  return { bounds, hits: raycaster.intersectObjects([...pickables, ...bondGroup.children], false) };
}

function pointOnPlane(event, y = 0) {
  hitTest(event);
  plane.set(new THREE.Vector3(0, 1, 0), -y);
  return raycaster.ray.intersectPlane(plane, new THREE.Vector3());
}

function setMode(mode) {
  state.mode = mode;
  state.bondStart = null;
  syncControls();
  const copy = {
    place: state.selectedElement ? `Place ${state.selectedElement} in the scene` : "Choose an element, then click an open point to place it.",
    move: "Drag an atom to reposition it; drag empty space to orbit the view.",
    bond: state.bondStart ? "Choose the second atom to complete the bond." : "Select two atoms to connect them.",
    delete: "Select an atom or bond to remove it.",
  };
  setInteractionHint(copy[mode]);
}

async function postAtom(position) {
  if (!state.selectedElement) { setInteractionHint("Choose an element first."); return; }
  try {
    const result = await request("/atoms", { method: "POST", body: JSON.stringify({ element: state.selectedElement, position: position.toArray(), rotation: [0, 0, 0] }) });
    renderStructure(result.scene);
  } catch (error) { setInteractionHint(error.message); }
}

async function removeObject(hit) {
  const id = hit.object.userData.atomId;
  const bondId = hit.object.userData.bondId;
  try {
    const data = await request(id ? `/atoms/${encodeURIComponent(id)}` : `/bonds/${encodeURIComponent(bondId)}`, { method: "DELETE" });
    state.selectedAtom = null;
    renderStructure(data);
  } catch (error) { setInteractionHint(error.message); }
}

async function finishBond(atomId) {
  if (!state.bondStart) {
    state.bondStart = atomId;
    state.selectedAtom = atomId;
    buildAtoms();
    setInteractionHint("First atom selected · choose the second atom.");
    return;
  }
  if (state.bondStart === atomId) {
    state.bondStart = null;
    setInteractionHint("Bond cancelled · choose two different atoms.");
    return;
  }
  try {
    const result = await request("/bonds", { method: "POST", body: JSON.stringify({ atom_a: state.bondStart, atom_b: atomId, order: Number(document.getElementById("bondOrder").value) }) });
    state.bondStart = null;
    renderStructure(result.scene);
  } catch (error) {
    state.bondStart = null;
    setInteractionHint(error.message);
  }
}

renderer.domElement.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  const { hits } = hitTest(event);
  const hit = hits[0] || null;
  const atomId = hit?.object.userData.atomId;
  if (!hit && state.mode === "place") {
    const point = pointOnPlane(event, 0);
    if (point) void postAtom(point.add(new THREE.Vector3(0, 0.58, 0)));
    return;
  }
  if (hit && state.mode === "delete") { removeObject(hit); return; }
  if (atomId && state.mode === "bond") { finishBond(atomId); return; }
  if (atomId && state.mode === "place") { state.selectedAtom = atomId; buildAtoms(); return; }

  renderer.domElement.setPointerCapture(event.pointerId);
  if (atomId && state.mode === "move") {
    const atom = state.atoms.find((item) => item.id === atomId);
    state.selectedAtom = atomId;
    buildAtoms();
    state.pointer = { kind: "atom", id: atomId, y: atom.position[1], moved: false };
  } else if (!hit && state.mode === "move") {
    state.pointer = { kind: "orbit", x: event.clientX, y: event.clientY };
  }
});

renderer.domElement.addEventListener("pointermove", (event) => {
  const drag = state.pointer;
  if (!drag) return;
  if (drag.kind === "orbit") {
    spherical.theta -= (event.clientX - drag.x) * 0.006;
    spherical.phi = THREE.MathUtils.clamp(spherical.phi - (event.clientY - drag.y) * 0.006, 0.12, Math.PI - 0.12);
    drag.x = event.clientX;
    drag.y = event.clientY;
    updateCamera();
    return;
  }
  const point = pointOnPlane(event, drag.y);
  if (!point) return;
  drag.moved = true;
  const mesh = atomMeshes.get(drag.id);
  if (mesh) mesh.position.copy(point);
  const atom = state.atoms.find((item) => item.id === drag.id);
  if (atom) atom.position = point.toArray();
  buildBonds();
});

async function endPointer() {
  const drag = state.pointer;
  state.pointer = null;
  if (drag?.kind !== "atom" || !drag.moved) return;
  const mesh = atomMeshes.get(drag.id);
  if (!mesh) return;
  try {
    renderStructure(await request(`/atoms/${encodeURIComponent(drag.id)}`, { method: "PUT", body: JSON.stringify({ position: mesh.position.toArray() }) }));
  } catch (error) { setInteractionHint(error.message); }
}
renderer.domElement.addEventListener("pointerup", endPointer);
renderer.domElement.addEventListener("pointercancel", endPointer);
renderer.domElement.addEventListener("wheel", (event) => {
  event.preventDefault();
  spherical.radius = THREE.MathUtils.clamp(spherical.radius * (event.deltaY > 0 ? 1.09 : 0.92), 4, 35);
  updateCamera();
}, { passive: false });

document.querySelectorAll(".mode").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
document.getElementById("resetBtn").addEventListener("click", async () => {
  try { state.selectedAtom = null; state.bondStart = null; renderStructure(await request("/clear", { method: "POST" })); setInteractionHint("Scene cleared. Choose an element to begin again."); }
  catch (error) { setInteractionHint(error.message); }
});
document.getElementById("saveBtn").addEventListener("click", async () => {
  try {
    const data = await request("/save", { method: "POST" });
    localStorage.setItem(SAVE_KEY, JSON.stringify(data));
    setInteractionHint("Scene saved on this computer.");
  } catch (error) { setInteractionHint(error.message); }
});
document.getElementById("loadBtn").addEventListener("click", async () => {
  const raw = localStorage.getItem(SAVE_KEY);
  if (!raw) { setInteractionHint("No saved scene found on this computer."); return; }
  try {
    const data = JSON.parse(raw);
    const sceneData = await request("/scene", { method: "PUT", body: JSON.stringify(data) });
    state.selectedAtom = null;
    renderStructure(await request("/structure"));
    if (!sceneData.atoms) throw new Error("Saved scene was malformed.");
    setInteractionHint("Saved scene restored.");
  } catch (error) { setInteractionHint(`Load failed: ${error.message}`); }
});
document.addEventListener("keydown", async (event) => {
  if (event.key === "Escape") setMode("move");
  if ((event.key === "Delete" || event.key === "Backspace") && state.selectedAtom && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
    try { renderStructure(await request(`/atoms/${encodeURIComponent(state.selectedAtom)}`, { method: "DELETE" })); }
    catch (error) { setInteractionHint(error.message); }
  }
});

function animateLabels() {
  const labels = document.getElementById("sceneLabels");
  for (const [atomId, mesh] of atomMeshes) {
    const label = labelNodes.get(atomId);
    if (!label) continue;
    const point = mesh.position.clone().project(camera);
    const visible = point.z >= -1 && point.z <= 1 && Math.abs(point.x) < 1.2 && Math.abs(point.y) < 1.2;
    label.hidden = !visible;
    if (visible) {
      label.style.left = `${(point.x * 0.5 + 0.5) * labels.clientWidth}px`;
      label.style.top = `${(-point.y * 0.5 + 0.5) * labels.clientHeight}px`;
    }
  }
}

function animationFrame() {
  requestAnimationFrame(animationFrame);
  animateLabels();
  renderer.render(scene, camera);
}

window.addEventListener("resize", resize);

async function start() {
  try {
    state.elements = await request("/elements");
    buildPeriodicTable();
    setMode("place");
    updateCamera();
    resize();
    renderStructure(await request("/structure"));
    animationFrame();
  } catch (error) {
    showError(`Molecular Lab could not start: ${error.message}`);
  }
}

start();
