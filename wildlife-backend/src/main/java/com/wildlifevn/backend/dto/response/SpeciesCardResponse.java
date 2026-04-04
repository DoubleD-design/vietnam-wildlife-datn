package com.wildlifevn.backend.dto.response;

public record SpeciesCardResponse(
                String id,
                String scientificName,
                String vietnameseName,
                String conservationStatus,
                String heroImageUrl,
                String group,
                String region) {
}
