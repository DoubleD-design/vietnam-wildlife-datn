package com.wildlifevn.backend.dto.response;

import java.util.List;
import java.util.Map;

public record SpeciesScientificProfileResponse(
        String id,
        String canonicalId,
        String scientificName,
        String authority,
        String rank,
        String commonNameVi,
        String commonNameEn,
        String group,
        Map<String, Object> taxonomy,
        String imageUrl,
        List<Map<String, Object>> mediaAssets,
        String description,
        Map<String, Object> distribution,
        String behavior,
        Map<String, Object> ecology,
        Map<String, Object> conservation,
        List<String> searchKeywords) {
}
