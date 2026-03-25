package com.wildlifevn.backend.dto.response;

import java.util.List;

public record SpeciesDetailResponse(
        String id,
        String scientificName,
        String vietnameseName,
        String conservationStatus,
        String shortDescription,
        String heroImageUrl,
        List<String> mediaUrls) {
}
