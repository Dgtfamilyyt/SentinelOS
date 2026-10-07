"""ToolManager adapters for observing and manipulating the Molecular Lab."""

from labs.molecular import get_molecular_lab_service
from tools.base import Tool
from tools.policy import PermissionClass


class MolecularGetStructure(Tool):
    name = "molecular_get_structure"
    description = "Observe the current Molecular Lab atoms, bonds, formula, validation status, and recognized molecule."
    category = "molecular_lab"
    parameters = {}
    permission = PermissionClass.READ_ONLY

    def execute(self, **kwargs):
        return get_molecular_lab_service().structure()


class MolecularValidate(Tool):
    name = "molecular_validate"
    description = "Deterministically validate the current Molecular Lab structure and identify supported molecules."
    category = "molecular_lab"
    parameters = {}
    permission = PermissionClass.READ_ONLY

    def execute(self, **kwargs):
        return get_molecular_lab_service().validate()


class MolecularAddAtom(Tool):
    name = "molecular_add_atom"
    description = "Add a supported element atom to the Molecular Lab scene at an optional 3D position."
    category = "molecular_lab"
    parameters = {
        "element": {"type": "string", "required": True},
        "position": {"type": "list", "required": False, "default": [0, 0, 0]},
    }
    permission = PermissionClass.STATE_CHANGE

    def execute(self, element, position):
        service = get_molecular_lab_service()
        atom = service.add_atom(element, position)
        return {"atom": atom, **service.structure()}


class MolecularMoveAtom(Tool):
    name = "molecular_move_atom"
    description = "Move a Molecular Lab atom to a validated 3D position."
    category = "molecular_lab"
    parameters = {
        "atom_id": {"type": "string", "required": True},
        "position": {"type": "list", "required": True},
    }
    permission = PermissionClass.STATE_CHANGE

    def execute(self, atom_id, position):
        service = get_molecular_lab_service()
        service.move_atom(atom_id, position)
        return service.structure()


class MolecularRemoveAtom(Tool):
    name = "molecular_remove_atom"
    description = "Remove an atom and its attached bonds from the Molecular Lab scene."
    category = "molecular_lab"
    parameters = {"atom_id": {"type": "string", "required": True}}
    permission = PermissionClass.STATE_CHANGE

    def execute(self, atom_id):
        return get_molecular_lab_service().remove_atom(atom_id)


class MolecularAddBond(Tool):
    name = "molecular_add_bond"
    description = "Connect two existing Molecular Lab atoms with a single, double, or triple bond."
    category = "molecular_lab"
    parameters = {
        "atom_a": {"type": "string", "required": True},
        "atom_b": {"type": "string", "required": True},
        "order": {"type": "integer", "required": False, "default": 1},
    }
    permission = PermissionClass.STATE_CHANGE

    def execute(self, atom_a, atom_b, order):
        service = get_molecular_lab_service()
        bond = service.add_bond(atom_a, atom_b, order)
        return {"bond": bond, **service.structure()}


class MolecularRemoveBond(Tool):
    name = "molecular_remove_bond"
    description = "Remove a bond from the Molecular Lab scene."
    category = "molecular_lab"
    parameters = {"bond_id": {"type": "string", "required": True}}
    permission = PermissionClass.STATE_CHANGE

    def execute(self, bond_id):
        return get_molecular_lab_service().remove_bond(bond_id)


class MolecularClearScene(Tool):
    name = "molecular_clear_scene"
    description = "Clear every atom and bond from the Molecular Lab scene."
    category = "molecular_lab"
    parameters = {}
    permission = PermissionClass.STATE_CHANGE

    def execute(self, **kwargs):
        return get_molecular_lab_service().clear()
