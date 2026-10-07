import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from labs.molecular import ELEMENTS, MolecularLabError, MolecularLabService, get_molecular_lab_service
from tools.manager import ToolManager
from tools.policy import ExecutionPolicy


def make_atoms(service, symbols):
    return [service.add_atom(symbol, [index * 1.5, 0, 0]) for index, symbol in enumerate(symbols)]


def test_element_catalog_has_structured_demo_data():
    service = MolecularLabService()
    elements = service.elements()
    assert len(elements) >= 10
    assert all({"atomic_number", "symbol", "name", "atomic_mass", "common_valences", "category", "color"} <= set(e) for e in elements)
    assert {"H", "C", "N", "O"} <= {element["symbol"] for element in ELEMENTS}


def test_atom_bond_creation_and_deletion_cascade():
    service = MolecularLabService()
    hydrogen, oxygen = make_atoms(service, ["H", "O"])
    bond = service.add_bond(hydrogen["id"], oxygen["id"])
    assert service.scene()["bonds"] == [bond]
    service.remove_atom(oxygen["id"])
    assert service.scene()["atoms"] == [hydrogen]
    assert service.scene()["bonds"] == []


@pytest.mark.parametrize(
    "symbols,bonds,formula,name",
    [
        (["H", "H"], [(0, 1, 1)], "H2", "Hydrogen"),
        (["H", "O", "H"], [(0, 1, 1), (1, 2, 1)], "H2O", "Water"),
        (["O", "O"], [(0, 1, 2)], "O2", "Oxygen"),
        (["N", "N"], [(0, 1, 3)], "N2", "Nitrogen"),
        (["O", "C", "O"], [(0, 1, 2), (1, 2, 2)], "CO2", "Carbon dioxide"),
        (["C", "H", "H", "H", "H"], [(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1)], "CH4", "Methane"),
        (["N", "H", "H", "H"], [(0, 1, 1), (0, 2, 1), (0, 3, 1)], "NH3", "Ammonia"),
    ],
)
def test_supported_molecules_require_valid_graph(symbols, bonds, formula, name):
    service = MolecularLabService()
    atoms = make_atoms(service, symbols)
    for left, right, order in bonds:
        service.add_bond(atoms[left]["id"], atoms[right]["id"], order)
    result = service.validate()
    assert result["status"] == "VALID"
    assert (result["formula"], result["molecule"]) == (formula, name)


def test_formula_match_with_wrong_bond_graph_is_not_recognized():
    service = MolecularLabService()
    h1, oxygen, h2 = make_atoms(service, ["H", "O", "H"])
    service.add_bond(h1["id"], h2["id"], 1)
    service.add_bond(oxygen["id"], h1["id"], 1)
    result = service.validate()
    assert result["formula"] == "H2O"
    assert result["status"] != "VALID"


def test_incomplete_invalid_and_unknown_states_are_distinct():
    incomplete = MolecularLabService()
    make_atoms(incomplete, ["H", "O"])
    assert incomplete.validate()["status"] == "INCOMPLETE"

    invalid = MolecularLabService()
    carbon, *hydrogens = make_atoms(invalid, ["C", "H", "H", "H", "H", "H"])
    for hydrogen in hydrogens:
        invalid.add_bond(carbon["id"], hydrogen["id"])
    assert invalid.validate()["status"] == "INVALID"

    unknown = MolecularLabService()
    fluorine_a, fluorine_b = make_atoms(unknown, ["F", "F"])
    unknown.add_bond(fluorine_a["id"], fluorine_b["id"])
    assert unknown.validate()["status"] == "UNKNOWN"
    assert unknown.validate()["molecule"] is None


def test_serialization_round_trip_and_rejects_dangling_bond():
    original = MolecularLabService()
    h1, oxygen, h2 = make_atoms(original, ["H", "O", "H"])
    original.add_bond(h1["id"], oxygen["id"])
    original.add_bond(oxygen["id"], h2["id"])
    serialized = original.scene()
    restored = MolecularLabService()
    assert restored.load(serialized) == serialized
    assert restored.validate()["molecule"] == "Water"
    serialized["bonds"][0]["atom_a"] = "missing"
    with pytest.raises(MolecularLabError, match="bond"):
        restored.load(serialized)


class FakeCommandCenter:
    def __init__(self):
        self.ai = type("FakeAI", (), {"clear": lambda self: None})()
        self.tools = type("FakeTools", (), {"names": lambda self: []})()


def test_toolmanager_molecular_tools_share_scene_and_obey_policy():
    service = get_molecular_lab_service()
    service.clear()
    manager = ToolManager(policy=ExecutionPolicy())
    manager.discover()
    added = manager.execute("molecular_add_atom", {"element": "H", "position": [0, 0, 0]})
    assert added["success"] is True
    observed = manager.execute("molecular_get_structure")
    assert observed["result"]["atoms"][0]["element"] == "H"

    blocked = ToolManager(policy=ExecutionPolicy(set()))
    blocked.discover()
    assert blocked.execute("molecular_clear_scene")["error"] == "Tool execution denied by policy"
    service.clear()


def test_http_routes_serve_lab_and_mutations_reach_same_scene_service():
    service = get_molecular_lab_service()
    service.clear()
    app = create_app(FakeCommandCenter())
    with TestClient(app) as client:
        assert client.get("/static/labs/molecular_lab/index.html").status_code == 200
        elements = client.get("/api/molecular/elements")
        assert elements.status_code == 200
        assert {item["symbol"] for item in elements.json()} >= {"H", "O", "C", "N"}
        first = client.post("/api/molecular/atoms", json={"element": "H", "position": [0, 0, 0]}).json()["atom"]
        oxygen = client.post("/api/molecular/atoms", json={"element": "O", "position": [1, 0, 0]}).json()["atom"]
        last = client.post("/api/molecular/atoms", json={"element": "H", "position": [2, 0, 0]}).json()["atom"]
        client.post("/api/molecular/bonds", json={"atom_a": first["id"], "atom_b": oxygen["id"]})
        client.post("/api/molecular/bonds", json={"atom_a": oxygen["id"], "atom_b": last["id"]})
        observed = client.get("/api/molecular/structure").json()
        assert observed["status"] == "VALID"
        assert observed["formula"] == "H2O"

        manager = ToolManager(policy=ExecutionPolicy())
        manager.discover()
        tool_observation = manager.execute("molecular_get_structure")["result"]
        assert tool_observation["molecule"] == "Water"
        client.post("/api/molecular/clear")
    assert service.scene()["atoms"] == []
