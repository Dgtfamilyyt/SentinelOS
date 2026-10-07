# Sentinel Molecular Lab

Sentinel Molecular Lab is an optional desktop 3D chemistry workspace. It is served as a standalone page at `/static/labs/molecular_lab/index.html`; the Sentinel dashboard only links to it. It has no camera/AR dependency and makes no LLM calls.

```text
Sentinel dashboard link
        │
        ▼
Molecular Lab page ── HTTP ── api/molecular.py
        │                       │
        │ local Three.js        ▼
        │ scene renderer   labs/molecular/engine.py
        │                       ▲
        └─ mouse input ─────────┤
                                │ shared in-process scene
Sentinel Planner → ToolManager ┘
```

The UI uses the locally vendored, pinned Three.js 0.186.1 module under `web/labs/molecular_lab/vendor/`. Its source metadata and lockfile are alongside the page, and its MIT license is included there. No CDN is used at runtime. The chemistry engine is independent from rendering and contains the element catalog, bounded serializable scene model, valence checks, Hill/common formula generation, and a small explicit registry for H2, H2O, O2, N2, CO2, CH4, and NH3.

Validation is deterministic: over-valence and disconnected structures are `INVALID`; under-filled valence is `INCOMPLETE`; only a connected structure whose element labels and bond-order graph exactly match a registry entry is `VALID`; a connected, saturated but unregistered graph is `UNKNOWN`. This is a teaching-scale common-valence model, not a quantum chemistry or general chemical-equilibrium engine.

The browser talks only to the narrow `/api/molecular/*` endpoints. Its current scene is shared in-process with Sentinel tools; browser Save stores a version-1 JSON snapshot in that browser's local storage, and Load validates/restores it through the scene API. No extra database was added. To inspect or mutate the same scene from Sentinel, the standard ToolManager discovers `molecular_get_structure`, `molecular_validate`, `molecular_add_atom`, `molecular_move_atom`, `molecular_remove_atom`, `molecular_add_bond`, `molecular_remove_bond`, and `molecular_clear_scene`. Mutations are marked `STATE_CHANGE`; reads are `READ_ONLY`. They do not expose files, shell, or arbitrary code.

Open the page from the Sentinel dashboard's **Labs → Open Molecular Lab** link, or visit the static page path directly while the app is running. Mouse controls: choose an element and click empty scene space to place it; choose **Select / move** and drag an atom; choose **Bond** and click two atoms; choose **Delete** and click an atom/bond. Drag empty space to orbit and use the wheel to zoom. Save and Load are local to that browser profile; the live scene is reset if the server process restarts.

Run focused tests with:

```powershell
python -m pytest -q tests/test_molecular_lab.py
```

The module intentionally stops at desktop 3D. Camera, hand tracking, WebXR, arbitrary-molecule recognition, and persistent server-side lab sessions are not implemented.
