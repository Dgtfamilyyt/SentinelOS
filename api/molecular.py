"""Narrow HTTP adapter for the isolated Molecular Lab scene service."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.logger import logger
from labs.molecular import ELEMENTS, MolecularLabError, get_molecular_lab_service


router = APIRouter(prefix="/api/molecular", tags=["molecular-lab"])


class AtomRequest(BaseModel):
    element: str = Field(min_length=1, max_length=2)
    position: list[float] = Field(default_factory=lambda: [0, 0, 0], min_length=3, max_length=3)
    rotation: list[float] = Field(default_factory=lambda: [0, 0, 0], min_length=3, max_length=3)


class AtomMoveRequest(BaseModel):
    position: list[float] = Field(min_length=3, max_length=3)
    rotation: list[float] | None = Field(default=None, min_length=3, max_length=3)


class BondRequest(BaseModel):
    atom_a: str = Field(min_length=1, max_length=64)
    atom_b: str = Field(min_length=1, max_length=64)
    order: Literal[1, 2, 3] = 1


def _operate(operation):
    try:
        return operation()
    except MolecularLabError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/elements")
def molecular_elements():
    logger.info("MOLECULAR_LAB_OPENED")
    return [dict(element) for element in ELEMENTS]


@router.get("/scene")
def molecular_scene():
    return get_molecular_lab_service().scene()


@router.get("/structure")
def molecular_structure():
    return get_molecular_lab_service().structure()


@router.get("/validate")
def molecular_validate():
    return get_molecular_lab_service().validate()


@router.post("/atoms", status_code=201)
def molecular_add_atom(payload: AtomRequest):
    service = get_molecular_lab_service()
    atom = _operate(lambda: service.add_atom(payload.element, payload.position, payload.rotation))
    return {"atom": atom, "scene": service.structure()}


@router.put("/atoms/{atom_id}")
def molecular_move_atom(atom_id: str, payload: AtomMoveRequest):
    service = get_molecular_lab_service()
    _operate(lambda: service.move_atom(atom_id, payload.position, payload.rotation))
    return service.structure()


@router.delete("/atoms/{atom_id}")
def molecular_remove_atom(atom_id: str):
    service = get_molecular_lab_service()
    _operate(lambda: service.remove_atom(atom_id))
    return service.structure()


@router.post("/bonds", status_code=201)
def molecular_add_bond(payload: BondRequest):
    service = get_molecular_lab_service()
    bond = _operate(lambda: service.add_bond(payload.atom_a, payload.atom_b, payload.order))
    return {"bond": bond, "scene": service.structure()}


@router.delete("/bonds/{bond_id}")
def molecular_remove_bond(bond_id: str):
    service = get_molecular_lab_service()
    _operate(lambda: service.remove_bond(bond_id))
    return service.structure()


@router.post("/clear")
def molecular_clear():
    return get_molecular_lab_service().clear()


@router.put("/scene")
def molecular_load_scene(payload: dict):
    return _operate(lambda: get_molecular_lab_service().load(payload))


@router.post("/save")
def molecular_save_scene():
    scene = get_molecular_lab_service().scene()
    logger.info("MOLECULAR_SCENE_SAVED atom_count=%d bond_count=%d", len(scene["atoms"]), len(scene["bonds"]))
    return scene
