package com.wildlifevn.backend.controller;

import com.wildlifevn.backend.dto.response.SpeciesCardResponse;
import com.wildlifevn.backend.dto.response.SpeciesDetailResponse;
import com.wildlifevn.backend.dto.response.PagedResponse;
import com.wildlifevn.backend.dto.response.SpeciesScientificProfileResponse;
import com.wildlifevn.backend.service.SpeciesService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.CacheControl;
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

    private static final Logger logger = LoggerFactory.getLogger(SpeciesController.class);
    private static final CacheControl LIST_CACHE = CacheControl.maxAge(60, TimeUnit.SECONDS).cachePublic();
    private static final CacheControl SUMMARY_CACHE = CacheControl.maxAge(5, TimeUnit.MINUTES).cachePublic();
    private static final CacheControl PROFILE_CACHE = CacheControl.maxAge(10, TimeUnit.MINUTES).cachePublic();

    private final SpeciesService speciesService;

    public SpeciesController(SpeciesService speciesService) {
        this.speciesService = speciesService;
    }

    @GetMapping
    @Operation(summary = "List species", description = "List/search species for library cards")
    public ResponseEntity<PagedResponse<SpeciesCardResponse>> listSpecies(
            @RequestParam(defaultValue = "") String keyword,
            @RequestParam(defaultValue = "") String sectorSlug,
            @RequestParam(defaultValue = "") String conservationStatus,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "12") int size) {
        Page<SpeciesCardResponse> pageData =
                speciesService.listSpecies(keyword, sectorSlug, conservationStatus, page, size);
        logger.info(
                "[SpeciesAPI] GET /api/species success keyword='{}' sectorSlug='{}' conservationStatus='{}' page={} size={} returnedElements={} totalElements={} totalPages={}",
                keyword,
                sectorSlug,
                conservationStatus,
                page,
                size,
            pageData.getNumberOfElements(),
            pageData.getTotalElements(),
            pageData.getTotalPages());
        return ResponseEntity.ok()
            .cacheControl(Objects.requireNonNull(LIST_CACHE))
            .body(PagedResponse.from(pageData));
    }

    @GetMapping("/{speciesId}/summary")
    @Operation(summary = "Species summary", description = "Get lightweight species summary for cards/quick preview")
    public ResponseEntity<SpeciesDetailResponse> getSpeciesSummary(@PathVariable @NonNull String speciesId) {
        SpeciesDetailResponse result = speciesService.getSpeciesDetail(speciesId);
        logger.info("[SpeciesAPI] GET /api/species/{}/summary success", speciesId);
        return ResponseEntity.ok().cacheControl(Objects.requireNonNull(SUMMARY_CACHE)).body(result);
    }

    @GetMapping("/{speciesId}/scientific-profile")
    @Operation(summary = "Species scientific profile", description = "Get full scientific profile document from MongoDB")
    public ResponseEntity<SpeciesScientificProfileResponse> getSpeciesScientificProfile(
            @PathVariable @NonNull String speciesId) {
        SpeciesScientificProfileResponse result = speciesService.getSpeciesScientificProfile(speciesId);
        logger.info("[SpeciesAPI] GET /api/species/{}/scientific-profile success", speciesId);
        return ResponseEntity.ok().cacheControl(Objects.requireNonNull(PROFILE_CACHE)).body(result);
    }

    @GetMapping("/{speciesId}/media")
    @Operation(summary = "Species media gallery", description = "Get species detail including media URLs")
    public ResponseEntity<SpeciesDetailResponse> getSpeciesMedia(@PathVariable @NonNull String speciesId) {
        SpeciesDetailResponse result = speciesService.getSpeciesDetail(speciesId);
        int mediaCount = result.mediaUrls() == null ? 0 : result.mediaUrls().size();
        logger.info("[SpeciesAPI] GET /api/species/{}/media success mediaCount={}", speciesId, mediaCount);
        return ResponseEntity.ok().cacheControl(Objects.requireNonNull(SUMMARY_CACHE)).body(result);
    }
}
