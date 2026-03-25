package com.wildlifevn.backend.dto.response;

public record SpeciesCandidateResponse(
        String speciesId,
        String scientificName,
        String vietnameseName,
        String heroImageUrl) {
}
