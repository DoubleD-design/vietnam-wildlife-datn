package com.wildlifevn.backend.controller;

import com.wildlifevn.backend.dto.response.SpeciesCardResponse;
import com.wildlifevn.backend.dto.response.SpeciesDetailResponse;
import com.wildlifevn.backend.dto.response.SpeciesScientificProfileResponse;
import com.wildlifevn.backend.service.SpeciesService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.data.domain.Page;
import org.springframework.http.ResponseEntity;
import org.springframework.lang.NonNull;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/species")
@Tag(name = "Species", description = "Species business APIs")
public class SpeciesController {

    private final SpeciesService speciesService;

    public SpeciesController(SpeciesService speciesService) {
        this.speciesService = speciesService;
    }

    @GetMapping
    @Operation(summary = "List species", description = "List/search species for library cards")
    public ResponseEntity<Page<SpeciesCardResponse>> listSpecies(
            @RequestParam(defaultValue = "") String keyword,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "12") int size) {
        return ResponseEntity.ok(speciesService.listSpecies(keyword, page, size));
    }

    @GetMapping("/{speciesId}/summary")
    @Operation(summary = "Species summary", description = "Get lightweight species summary for cards/quick preview")
    public ResponseEntity<SpeciesDetailResponse> getSpeciesSummary(@PathVariable @NonNull String speciesId) {
        return ResponseEntity.ok(speciesService.getSpeciesDetail(speciesId));
    }

    @GetMapping("/{speciesId}/scientific-profile")
    @Operation(summary = "Species scientific profile", description = "Get full scientific profile document from MongoDB")
    public ResponseEntity<SpeciesScientificProfileResponse> getSpeciesScientificProfile(
            @PathVariable @NonNull String speciesId) {
        return ResponseEntity.ok(speciesService.getSpeciesScientificProfile(speciesId));
    }

    @GetMapping("/{speciesId}/media")
    @Operation(summary = "Species media gallery", description = "Get species detail including media URLs")
    public ResponseEntity<SpeciesDetailResponse> getSpeciesMedia(@PathVariable @NonNull String speciesId) {
        return ResponseEntity.ok(speciesService.getSpeciesDetail(speciesId));
    }
}
