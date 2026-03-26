from fastapi import APIRouter, Query

from app.services.species_service import SpeciesService

router = APIRouter(prefix="/species", tags=["Species"])
species_service = SpeciesService()


@router.get("")
def list_species(
    keyword: str = Query(default=""),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=12, ge=1, le=100),
):
    return species_service.list_species(keyword, page, size)


@router.get("/{species_id}/summary")
def get_species_summary(species_id: str):
    return species_service.get_species_summary(species_id)


@router.get("/{species_id}/scientific-profile")
def get_species_scientific_profile(species_id: str):
    return species_service.get_scientific_profile(species_id)
