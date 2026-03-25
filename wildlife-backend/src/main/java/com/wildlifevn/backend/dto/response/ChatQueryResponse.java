package com.wildlifevn.backend.dto.response;

import java.util.List;

public record ChatQueryResponse(
        String status,
        String message,
        String answer,
        String activeSpeciesId,
        String activeSpeciesName,
        List<SpeciesCandidateResponse> candidates) {
}
