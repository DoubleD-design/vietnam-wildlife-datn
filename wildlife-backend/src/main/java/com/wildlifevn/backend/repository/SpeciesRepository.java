package com.wildlifevn.backend.repository;

import com.wildlifevn.backend.model.SpeciesDocument;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SpeciesRepository extends MongoRepository<SpeciesDocument, String> {
    Page<SpeciesDocument> findByVietnameseNameContainingIgnoreCaseOrScientificNameContainingIgnoreCase(
            String vietnameseName,
            String scientificName,
            Pageable pageable);

    Optional<SpeciesDocument> findFirstByVietnameseNameIgnoreCaseOrScientificNameIgnoreCase(
            String vietnameseName,
            String scientificName);
}
