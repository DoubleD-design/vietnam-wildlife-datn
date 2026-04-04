package com.wildlifevn.backend.service;

import com.wildlifevn.backend.dto.response.SpeciesCardResponse;
import com.wildlifevn.backend.dto.response.SpeciesDetailResponse;
import com.wildlifevn.backend.dto.response.SpeciesScientificProfileResponse;
import com.wildlifevn.backend.model.SpeciesDocument;
import com.wildlifevn.backend.model.SpeciesMedia;
import com.wildlifevn.backend.repository.SpeciesRepository;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.lang.NonNull;
import org.springframework.stereotype.Service;

@Service
public class SpeciesService {
    private final SpeciesRepository speciesRepository;
    private final MongoTemplate mongoTemplate;

    public SpeciesService(SpeciesRepository speciesRepository, MongoTemplate mongoTemplate) {
        this.speciesRepository = speciesRepository;
        this.mongoTemplate = mongoTemplate;
    }

    public Page<SpeciesCardResponse> listSpecies(String keyword, int page, int size) {
        Pageable pageable = PageRequest.of(page, size);

        Page<SpeciesDocument> speciesPage;
        if (keyword == null || keyword.isBlank()) {
            speciesPage = speciesRepository.findAll(pageable);
        } else {
            speciesPage = speciesRepository
                    .findByVietnameseNameContainingIgnoreCaseOrScientificNameContainingIgnoreCase(
                            keyword,
                            keyword,
                            pageable);
        }

        return speciesPage.map(this::toCard);
    }

    public SpeciesDetailResponse getSpeciesDetail(@NonNull String speciesId) {
        SpeciesDocument species = speciesRepository.findById(Objects.requireNonNull(speciesId))
                .orElseThrow(() -> new IllegalArgumentException("Species not found: " + speciesId));
        return toDetail(species);
    }

    public SpeciesScientificProfileResponse getSpeciesScientificProfile(@NonNull String speciesId) {
        Objects.requireNonNull(speciesId);

        Document document;
        if (ObjectId.isValid(speciesId)) {
            Query query = new Query(Criteria.where("_id").is(new ObjectId(speciesId)));
            document = mongoTemplate.findOne(query, Document.class, "species");
        } else {
            Query query = new Query(Criteria.where("_id").is(speciesId));
            document = mongoTemplate.findOne(query, Document.class, "species");
        }

        if (document == null) {
            throw new IllegalArgumentException("Species not found: " + speciesId);
        }

        return toScientificProfile(document);
    }

    public Optional<SpeciesDocument> findSpeciesMention(String question) {
        if (question == null || question.isBlank()) {
            return Optional.empty();
        }

        String normalized = question.toLowerCase(Locale.ROOT);
        List<SpeciesDocument> allSpecies = speciesRepository.findAll();
        for (SpeciesDocument species : allSpecies) {
            String vn = nullableLower(species.getVietnameseName());
            String sci = nullableLower(species.getScientificName());
            if ((!vn.isBlank() && normalized.contains(vn)) || (!sci.isBlank() && normalized.contains(sci))) {
                return Optional.of(species);
            }
        }
        return Optional.empty();
    }

    public List<SpeciesCardResponse> topCandidatesFromCurrentData(int limit) {
        return speciesRepository.findAll(PageRequest.of(0, limit))
                .stream()
                .map(this::toCard)
                .toList();
    }

    public SpeciesDocument getSpeciesOrThrow(@NonNull String speciesId) {
        return speciesRepository.findById(Objects.requireNonNull(speciesId))
                .orElseThrow(() -> new IllegalArgumentException("Species not found: " + speciesId));
    }

    private SpeciesCardResponse toCard(SpeciesDocument species) {
        return new SpeciesCardResponse(
                species.getId(),
                species.getScientificName(),
                species.getVietnameseName(),
                resolveConservationStatus(species),
                resolveHeroImage(species),
                species.getGroup(),
                resolvePrimaryRegion(species));
    }

    private String resolveConservationStatus(SpeciesDocument species) {
        String direct = normalizeConservationCode(species.getConservationStatus());
        if (!"DD".equals(direct)) {
            return direct;
        }

        Map<String, Object> conservation = species.getConservation();
        String fromMap = extractConservationFromMap(conservation);
        if (!"DD".equals(fromMap)) {
            return fromMap;
        }

        return resolveConservationStatusFromMongo(species.getId());
    }

    private String normalizeConservationCode(String rawValue) {
        String raw = rawValue == null ? "" : rawValue.trim();
        if (raw.isEmpty()) {
            return "DD";
        }

        String normalized = raw.toUpperCase(Locale.ROOT)
                .replace('-', ' ')
                .replace('_', ' ')
                .trim();

        return switch (normalized) {
            case "LC", "LEAST CONCERN", "ÍT LO NGẠI" -> "LC";
            case "NT", "NEAR THREATENED", "GẦN BỊ ĐE DỌA" -> "NT";
            case "VU", "VULNERABLE", "SẼ NGUY CẤP" -> "VU";
            case "EN", "ENDANGERED", "NGUY CẤP" -> "EN";
            case "CR", "CRITICALLY ENDANGERED", "CỰC KỲ NGUY CẤP" -> "CR";
            case "DD", "DATA DEFICIENT", "THIẾU DỮ LIỆU" -> "DD";
            default -> {
                // Handle values containing codes, e.g. "IUCN: EN".
                if (normalized.contains(" CR ") || normalized.endsWith(" CR") || normalized.startsWith("CR ")) {
                    yield "CR";
                }
                if (normalized.contains(" EN ") || normalized.endsWith(" EN") || normalized.startsWith("EN ")) {
                    yield "EN";
                }
                if (normalized.contains(" VU ") || normalized.endsWith(" VU") || normalized.startsWith("VU ")) {
                    yield "VU";
                }
                if (normalized.contains(" NT ") || normalized.endsWith(" NT") || normalized.startsWith("NT ")) {
                    yield "NT";
                }
                if (normalized.contains(" LC ") || normalized.endsWith(" LC") || normalized.startsWith("LC ")) {
                    yield "LC";
                }
                yield "DD";
            }
        };
    }

    private String extractConservationFromMap(Map<String, Object> conservation) {
        if (conservation == null || conservation.isEmpty()) {
            return "DD";
        }

        Object iucnCategory = conservation.get("iucn_category");
        String normalized = normalizeConservationCode(iucnCategory == null ? null : String.valueOf(iucnCategory));
        if (!"DD".equals(normalized)) {
            return normalized;
        }

        Object iucnCategoryCamel = conservation.get("iucnCategory");
        normalized = normalizeConservationCode(iucnCategoryCamel == null ? null : String.valueOf(iucnCategoryCamel));
        if (!"DD".equals(normalized)) {
            return normalized;
        }

        Object iucn = conservation.get("iucn");
        if (iucn instanceof Map<?, ?> iucnMap) {
            Object nestedCategory = iucnMap.get("category");
            normalized = normalizeConservationCode(nestedCategory == null ? null : String.valueOf(nestedCategory));
            if (!"DD".equals(normalized)) {
                return normalized;
            }
        }

        return "DD";
    }

    private String resolveConservationStatusFromMongo(String speciesId) {
        if (speciesId == null || speciesId.isBlank()) {
            return "DD";
        }

        Query query;
        if (ObjectId.isValid(speciesId)) {
            query = new Query(Criteria.where("_id").is(new ObjectId(speciesId)));
        } else {
            query = new Query(Criteria.where("_id").is(speciesId));
        }
        query.fields().include("conservation_status").include("conservation");

        Document doc = mongoTemplate.findOne(query, Document.class, "species");
        if (doc == null) {
            return "DD";
        }

        String direct = normalizeConservationCode(doc.getString("conservation_status"));
        if (!"DD".equals(direct)) {
            return direct;
        }

        Object conservationObj = doc.get("conservation");
        if (conservationObj instanceof Map<?, ?> map) {
            Map<String, Object> typedMap = (Map<String, Object>) map;
            return extractConservationFromMap(typedMap);
        }

        return "DD";
    }

    @SuppressWarnings("unchecked")
    private String resolvePrimaryRegion(SpeciesDocument species) {
        Map<String, Object> distribution = species.getDistribution();
        if (distribution == null || distribution.isEmpty()) {
            return null;
        }

        Object regions = distribution.get("regions_vi");
        if (regions instanceof List<?> list) {
            for (Object item : list) {
                if (item != null) {
                    String region = String.valueOf(item).trim();
                    if (!region.isEmpty()) {
                        return region;
                    }
                }
            }
        }

        return null;
    }

    private SpeciesDetailResponse toDetail(SpeciesDocument species) {
        List<String> mediaUrls = species.getMedia() == null
                ? List.of()
                : species.getMedia().stream()
                        .map(this::resolveMediaUrl)
                        .filter(url -> url != null && !url.isBlank())
                        .toList();

        return new SpeciesDetailResponse(
                species.getId(),
                species.getScientificName(),
                species.getVietnameseName(),
                resolveConservationStatus(species),
                species.getShortDescription(),
                resolveHeroImage(species),
                mediaUrls);
    }

    private String resolveHeroImage(SpeciesDocument species) {
        if (species.getHeroImageUrl() != null && !species.getHeroImageUrl().isBlank()) {
            return species.getHeroImageUrl();
        }

        if (species.getMedia() == null || species.getMedia().isEmpty()) {
            return null;
        }

        for (SpeciesMedia media : species.getMedia()) {
            if (Boolean.TRUE.equals(media.getHero())) {
                String heroUrl = resolveMediaUrl(media);
                if (heroUrl != null && !heroUrl.isBlank()) {
                    return heroUrl;
                }
            }
        }

        return resolveMediaUrl(species.getMedia().getFirst());
    }

    private String resolveMediaUrl(SpeciesMedia media) {
        if (media == null) {
            return null;
        }
        if (media.getBlobUrl() != null && !media.getBlobUrl().isBlank()) {
            return media.getBlobUrl();
        }
        return media.getUrl();
    }

    private String nullableLower(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    private SpeciesScientificProfileResponse toScientificProfile(Document document) {
        return new SpeciesScientificProfileResponse(
                document.getObjectId("_id") != null ? document.getObjectId("_id").toHexString()
                        : toStringValue(document.get("_id")),
                toStringValue(document.get("canonical_id")),
                toStringValue(document.get("scientific_name")),
                toStringValue(document.get("authority")),
                toStringValue(document.get("rank")),
                toStringValue(document.get("common_name_vi")),
                toStringValue(document.get("common_name_en")),
                toStringValue(document.get("group")),
                toMap(document.get("taxonomy")),
                toStringValue(document.get("image_url")),
                toDocumentList(document.get("media_assets")),
                toStringValue(document.get("description")),
                toMap(document.get("distribution")),
                toStringValue(document.get("behavior")),
                toMap(document.get("ecology")),
                toMap(document.get("conservation")),
                toStringList(document.get("search_keywords")));
    }

    private String toStringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> toMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        return Map.of();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> toDocumentList(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }

        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                result.add((Map<String, Object>) map);
            }
        }
        return result;
    }

    private List<String> toStringList(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }

        return list.stream()
                .map(this::toStringValue)
                .filter(item -> item != null && !item.isBlank())
                .toList();
    }
}
