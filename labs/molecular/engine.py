"""Small, deterministic molecule graph model used by the lab UI and tools."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from itertools import permutations, product
import math
import threading
import uuid

from core.logger import logger


ELEMENTS = (
    {"atomic_number": 1, "symbol": "H", "name": "Hydrogen", "atomic_mass": 1.008, "common_valences": [1], "category": "nonmetal", "color": "#f4f7fb"},
    {"atomic_number": 2, "symbol": "He", "name": "Helium", "atomic_mass": 4.0026, "common_valences": [0], "category": "noble-gas", "color": "#d9ffff"},
    {"atomic_number": 6, "symbol": "C", "name": "Carbon", "atomic_mass": 12.011, "common_valences": [4], "category": "nonmetal", "color": "#343b46"},
    {"atomic_number": 7, "symbol": "N", "name": "Nitrogen", "atomic_mass": 14.007, "common_valences": [3, 5], "category": "nonmetal", "color": "#4f83ff"},
    {"atomic_number": 8, "symbol": "O", "name": "Oxygen", "atomic_mass": 15.999, "common_valences": [2], "category": "nonmetal", "color": "#ff5c67"},
    {"atomic_number": 9, "symbol": "F", "name": "Fluorine", "atomic_mass": 18.998, "common_valences": [1], "category": "halogen", "color": "#77e6c0"},
    {"atomic_number": 10, "symbol": "Ne", "name": "Neon", "atomic_mass": 20.180, "common_valences": [0], "category": "noble-gas", "color": "#b3f4ff"},
    {"atomic_number": 11, "symbol": "Na", "name": "Sodium", "atomic_mass": 22.990, "common_valences": [1], "category": "alkali-metal", "color": "#ab8cff"},
    {"atomic_number": 12, "symbol": "Mg", "name": "Magnesium", "atomic_mass": 24.305, "common_valences": [2], "category": "alkaline-earth", "color": "#58d7a3"},
    {"atomic_number": 15, "symbol": "P", "name": "Phosphorus", "atomic_mass": 30.974, "common_valences": [3, 5], "category": "nonmetal", "color": "#ffad50"},
    {"atomic_number": 16, "symbol": "S", "name": "Sulfur", "atomic_mass": 32.06, "common_valences": [2, 4, 6], "category": "nonmetal", "color": "#f3d94e"},
    {"atomic_number": 17, "symbol": "Cl", "name": "Chlorine", "atomic_mass": 35.45, "common_valences": [1], "category": "halogen", "color": "#73df78"},
    {"atomic_number": 18, "symbol": "Ar", "name": "Argon", "atomic_mass": 39.948, "common_valences": [0], "category": "noble-gas", "color": "#a7e9ff"},
)
ELEMENT_BY_SYMBOL = {element["symbol"]: element for element in ELEMENTS}


class MolecularLabError(ValueError):
    """A rejected operation or malformed scene in the Molecular Lab."""


MOLECULES = (
    {"name": "Hydrogen", "formula": "H2", "atoms": ["H", "H"], "bonds": [(0, 1, 1)]},
    {"name": "Water", "formula": "H2O", "atoms": ["H", "O", "H"], "bonds": [(0, 1, 1), (1, 2, 1)]},
    {"name": "Oxygen", "formula": "O2", "atoms": ["O", "O"], "bonds": [(0, 1, 2)]},
    {"name": "Nitrogen", "formula": "N2", "atoms": ["N", "N"], "bonds": [(0, 1, 3)]},
    {"name": "Carbon dioxide", "formula": "CO2", "atoms": ["O", "C", "O"], "bonds": [(0, 1, 2), (1, 2, 2)]},
    {"name": "Methane", "formula": "CH4", "atoms": ["C", "H", "H", "H", "H"], "bonds": [(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)]},
    {"name": "Ammonia", "formula": "NH3", "atoms": ["N", "H", "H", "H"], "bonds": [(0, 1, 1), (0, 2, 1), (0, 3, 1)]},
)


def _formula(atoms):
    counts = Counter(atom["element"] for atom in atoms)
    if counts["C"]:
        order = ["C", "H"]
    elif counts["N"] and counts["H"]:
        order = ["N", "H"]
    else:
        order = ["H"]
    order += sorted(symbol for symbol in counts if symbol not in order)
    return "".join(symbol + (str(counts[symbol]) if counts[symbol] > 1 else "") for symbol in order if counts[symbol])


def _canonical_graph(symbols, edge_orders):
    """Canonical key for these small supported structures, independent of IDs."""
    groups = []
    for symbol in sorted(set(symbols)):
        indices = [index for index, value in enumerate(symbols) if value == symbol]
        groups.append((symbol, list(permutations(indices))))
    best = None
    for group_permutations in product(*(items for _, items in groups)):
        order = [index for group in group_permutations for index in group]
        key = "|".join(symbols[index] for index in order) + ":"
        key += ",".join(str(edge_orders.get(tuple(sorted((order[i], order[j]))), 0))
                         for i in range(len(order)) for j in range(i + 1, len(order)))
        if best is None or key < best:
            best = key
    return best or ""


def _molecule_signature(molecule):
    edges = {tuple(sorted((a, b))): order for a, b, order in molecule["bonds"]}
    return _canonical_graph(molecule["atoms"], edges)


MOLECULE_BY_SIGNATURE = {_molecule_signature(molecule): molecule for molecule in MOLECULES}


class MolecularLabService:
    MAX_ATOMS = 100

    def __init__(self):
        self._lock = threading.RLock()
        self._atoms = []
        self._bonds = []

    def elements(self):
        return [dict(element, common_valences=list(element["common_valences"])) for element in ELEMENTS]

    def scene(self):
        with self._lock:
            return {"version": 1, "atoms": [dict(a, position=list(a["position"]), rotation=list(a["rotation"])) for a in self._atoms],
                    "bonds": [dict(b) for b in self._bonds]}

    def add_atom(self, element, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
        if element not in ELEMENT_BY_SYMBOL:
            raise MolecularLabError(f"Unsupported element: {element}")
        position = self._vector(position, "position")
        rotation = self._vector(rotation, "rotation")
        with self._lock:
            if len(self._atoms) >= self.MAX_ATOMS:
                raise MolecularLabError(f"A scene may contain at most {self.MAX_ATOMS} atoms")
            atom = {"id": uuid.uuid4().hex, "element": element, "position": position,
                    "rotation": rotation, "selected": False}
            self._atoms.append(atom)
        logger.info("ATOM_CREATED element=%s id=%s", element, atom["id"])
        return dict(atom)

    def move_atom(self, atom_id, position, rotation=None):
        position = self._vector(position, "position")
        rotation = self._vector(rotation, "rotation") if rotation is not None else None
        with self._lock:
            atom = self._find_atom(atom_id)
            atom["position"] = position
            if rotation is not None:
                atom["rotation"] = rotation
            return dict(atom)

    def remove_atom(self, atom_id):
        with self._lock:
            self._find_atom(atom_id)
            self._atoms = [atom for atom in self._atoms if atom["id"] != atom_id]
            self._bonds = [bond for bond in self._bonds if atom_id not in (bond["atom_a"], bond["atom_b"])]
        logger.info("ATOM_REMOVED id=%s", atom_id)
        return self.scene()

    def add_bond(self, atom_a, atom_b, order=1):
        if atom_a == atom_b:
            raise MolecularLabError("An atom cannot bond to itself")
        if isinstance(order, bool) or order not in (1, 2, 3):
            raise MolecularLabError("Bond order must be 1, 2, or 3")
        with self._lock:
            self._find_atom(atom_a)
            self._find_atom(atom_b)
            if any({bond["atom_a"], bond["atom_b"]} == {atom_a, atom_b} for bond in self._bonds):
                raise MolecularLabError("These atoms are already bonded")
            bond = {"id": uuid.uuid4().hex, "atom_a": atom_a, "atom_b": atom_b, "order": order}
            self._bonds.append(bond)
        logger.info("BOND_CREATED order=%s a=%s b=%s", order, atom_a, atom_b)
        return dict(bond)

    def remove_bond(self, bond_id):
        with self._lock:
            if not any(bond["id"] == bond_id for bond in self._bonds):
                raise MolecularLabError("Bond not found")
            self._bonds = [bond for bond in self._bonds if bond["id"] != bond_id]
        logger.info("BOND_REMOVED id=%s", bond_id)
        return self.scene()

    def clear(self):
        with self._lock:
            self._atoms = []
            self._bonds = []
        logger.info("MOLECULAR_SCENE_CLEARED")
        return self.scene()

    def load(self, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise MolecularLabError("Scene version must be 1")
        atoms, bonds = data.get("atoms"), data.get("bonds")
        if not isinstance(atoms, list) or not isinstance(bonds, list):
            raise MolecularLabError("Scene must contain atom and bond lists")
        if len(atoms) > self.MAX_ATOMS or len(bonds) > self.MAX_ATOMS * 3:
            raise MolecularLabError("Scene exceeds size limits")
        new_atoms, ids = [], set()
        for raw in atoms:
            if not isinstance(raw, dict):
                raise MolecularLabError("Atom entries must be objects")
            atom_id, element = raw.get("id"), raw.get("element")
            if not isinstance(atom_id, str) or not atom_id or len(atom_id) > 64 or atom_id in ids:
                raise MolecularLabError("Atom IDs must be unique non-empty strings")
            if not isinstance(element, str) or element not in ELEMENT_BY_SYMBOL:
                raise MolecularLabError(f"Unsupported element: {element}")
            ids.add(atom_id)
            new_atoms.append({"id": atom_id, "element": element,
                              "position": self._vector(raw.get("position", (0, 0, 0)), "position"),
                              "rotation": self._vector(raw.get("rotation", (0, 0, 0)), "rotation"),
                              "selected": False})
        new_bonds, pairs, bond_ids = [], set(), set()
        for raw in bonds:
            if not isinstance(raw, dict):
                raise MolecularLabError("Bond entries must be objects")
            bond_id, a, b, order = raw.get("id"), raw.get("atom_a"), raw.get("atom_b"), raw.get("order")
            pair = tuple(sorted((a, b))) if isinstance(a, str) and isinstance(b, str) else ()
            if (not isinstance(bond_id, str) or not bond_id or bond_id in bond_ids or
                    not isinstance(a, str) or not isinstance(b, str) or
                    a not in ids or b not in ids or a == b or pair in pairs or
                    isinstance(order, bool) or order not in (1, 2, 3)):
                raise MolecularLabError("Invalid, duplicated, or dangling bond")
            bond_ids.add(bond_id)
            pairs.add(pair)
            new_bonds.append({"id": bond_id, "atom_a": a, "atom_b": b, "order": order})
        with self._lock:
            self._atoms, self._bonds = new_atoms, new_bonds
        logger.info("MOLECULAR_SCENE_LOADED atom_count=%d bond_count=%d", len(new_atoms), len(new_bonds))
        return self.scene()

    def validate(self):
        with self._lock:
            atoms = [dict(atom) for atom in self._atoms]
            bonds = [dict(bond) for bond in self._bonds]
        result = self._validate(atoms, bonds)
        logger.info("MOLECULE_VALIDATED status=%s formula=%s", result["status"], result["formula"])
        if result["molecule"]:
            logger.info("MOLECULE_IDENTIFIED name=%s formula=%s", result["molecule"], result["formula"])
        return result

    @staticmethod
    def _validate(atoms, bonds):
        formula = _formula(atoms)
        base = {"status": "INCOMPLETE", "formula": formula, "molecule": None,
                "composition": dict(sorted(Counter(a["element"] for a in atoms).items())),
                "issues": [], "atom_count": len(atoms), "bond_count": len(bonds)}
        if not atoms:
            base["issues"] = ["Add at least one atom to begin."]
            return base
        ids = {atom["id"] for atom in atoms}
        if any(bond["atom_a"] not in ids or bond["atom_b"] not in ids or bond["atom_a"] == bond["atom_b"] or bond["order"] not in (1, 2, 3) for bond in bonds):
            base.update(status="INVALID", issues=["A bond has an invalid endpoint or order."])
            return base
        valence = defaultdict(int)
        adjacency = defaultdict(set)
        edges = {}
        for bond in bonds:
            a, b = bond["atom_a"], bond["atom_b"]
            valence[a] += bond["order"]
            valence[b] += bond["order"]
            adjacency[a].add(b)
            adjacency[b].add(a)
            edges[tuple(sorted((a, b)))] = bond["order"]
        over = []
        under = []
        for atom in atoms:
            value = valence[atom["id"]]
            valences = ELEMENT_BY_SYMBOL[atom["element"]]["common_valences"]
            if value not in valences and value > max(valences):
                over.append(atom["element"] + " " + atom["id"][:6])
            elif value not in valences and value != 0:
                if any(allowed > value for allowed in valences):
                    under.append(atom["element"] + " " + atom["id"][:6])
                else:
                    over.append(atom["element"] + " " + atom["id"][:6])
            elif value not in valences and value == 0 and max(valences) > 0:
                under.append(atom["element"] + " " + atom["id"][:6])
        if over:
            base.update(status="INVALID", issues=["Common valence exceeded for: " + ", ".join(over)])
            return base
        if under:
            base["issues"] = ["Unsatisfied common valence on: " + ", ".join(under)]
            return base
        if len(atoms) > 1:
            seen = set()
            queue = deque([atoms[0]["id"]])
            while queue:
                current = queue.popleft()
                if current in seen:
                    continue
                seen.add(current)
                queue.extend(adjacency[current] - seen)
            if len(seen) != len(atoms):
                base.update(status="INVALID", issues=["The structure has disconnected atoms; a molecule must be one connected component."])
                return base
        symbols = [atom["element"] for atom in atoms]
        index = {atom["id"]: position for position, atom in enumerate(atoms)}
        indexed_edges = {tuple(sorted((index[a], index[b]))): order for (a, b), order in edges.items()}
        molecule = None
        if any(item["formula"] == formula for item in MOLECULES):
            molecule = MOLECULE_BY_SIGNATURE.get(_canonical_graph(symbols, indexed_edges))
        if molecule:
            base.update(status="VALID", molecule=molecule["name"], formula=molecule["formula"])
        else:
            base.update(status="UNKNOWN", issues=["Valences are satisfied, but this structure is not in the supported molecule registry."])
        return base

    def structure(self):
        scene = self.scene()
        validation = self.validate()
        return {**scene, **validation}

    def _find_atom(self, atom_id):
        for atom in self._atoms:
            if atom["id"] == atom_id:
                return atom
        raise MolecularLabError("Atom not found")

    @staticmethod
    def _vector(value, name):
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise MolecularLabError(f"{name} must contain three numbers")
        try:
            if any(isinstance(component, bool) for component in value):
                raise ValueError("boolean is not a coordinate")
            result = [float(component) for component in value]
        except (TypeError, ValueError) as error:
            raise MolecularLabError(f"{name} must contain finite numbers") from error
        if not all(math.isfinite(component) and abs(component) <= 1000 for component in result):
            raise MolecularLabError(f"{name} values must be finite and within +/-1000")
        return result


_service = None
_service_lock = threading.Lock()


def get_molecular_lab_service():
    global _service
    with _service_lock:
        if _service is None:
            _service = MolecularLabService()
        return _service
