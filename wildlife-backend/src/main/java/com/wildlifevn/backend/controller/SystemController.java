package com.wildlifevn.backend.controller;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/system")
@Tag(name = "System", description = "System and health endpoints")
public class SystemController {

    @GetMapping("/health")
    @Operation(summary = "Health check", description = "Simple endpoint to verify backend is running")
    public Map<String, String> health() {
        return Map.of("status", "ok", "service", "wildlife-backend");
    }
}
