package com.university.learning.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Local synthetic benchmark, with no application context or external services. */
class AgentMemoryPerformanceTest {
    @Test
    void warmedObserveAndReadContextStayWithinLocalLatencyBudget() throws Exception {
        JdbcTemplate jdbc = new JdbcTemplate(new DriverManagerDataSource(
                "jdbc:h2:mem:memory_perf_" + UUID.randomUUID()
                        + ";MODE=MySQL;DB_CLOSE_DELAY=-1", "sa", ""));
        AgentMemoryService memory = new AgentMemoryService(jdbc, true);
        final int warmupCount = 10;
        final int sampleCount = 100;
        final double thresholdMs = 100.0;

        for (int i = 0; i < warmupCount; i++) {
            assertEquals(true, memory.observe(1001L, 2001L, 3001L + i,
                    "我在学Java").get("available"));
            assertEquals(true, memory.readContext(1001L, 2001L).get("available"));
        }

        List<Double> observeMs = new ArrayList<>();
        List<Double> readMs = new ArrayList<>();
        List<Double> combinedMs = new ArrayList<>();
        for (int i = 0; i < sampleCount; i++) {
            long start = System.nanoTime();
            Map<String, Object> observed = memory.observe(1001L, 2001L, 4001L + i,
                    i % 2 == 0 ? "我在学Java" : "我在学Python");
            long afterObserve = System.nanoTime();
            Map<String, Object> read = memory.readContext(1001L, 2001L);
            long afterRead = System.nanoTime();
            observeMs.add((afterObserve - start) / 1_000_000.0);
            readMs.add((afterRead - afterObserve) / 1_000_000.0);
            combinedMs.add((afterRead - start) / 1_000_000.0);
            assertEquals(true, observed.get("available"));
            assertEquals(true, read.get("available"));
            assertTrue(read.get("facts") instanceof List<?> facts && !facts.isEmpty());
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("recorded_at_utc", Instant.now().toString());
        result.put("scope", "one local synthetic H2 fixture; no production database or network calls");
        result.put("warmup_iterations", warmupCount);
        result.put("sample_count_per_operation", sampleCount);
        result.put("percentile_method", "nearest rank; median is the mean of the middle two samples");
        result.put("threshold_p95_ms", thresholdMs);
        result.put("machine", Map.of(
                "os_name", System.getProperty("os.name"),
                "os_version", System.getProperty("os.version"),
                "os_arch", System.getProperty("os.arch"),
                "available_processors", Runtime.getRuntime().availableProcessors()));
        result.put("jdk", Map.of(
                "java_version", System.getProperty("java.version"),
                "java_vendor", System.getProperty("java.vendor"),
                "vm_name", System.getProperty("java.vm.name")));
        result.put("observe", statistics(observeMs));
        result.put("read_context", statistics(readMs));
        result.put("combined", statistics(combinedMs));
        result.put("combined_p95_within_threshold", percentile95(combinedMs) <= thresholdMs);

        Path output = Path.of("target", "memory-validation", "java-memory-performance.json");
        Files.createDirectories(output.getParent());
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(output.toFile(), result);
        assertTrue(percentile95(combinedMs) <= thresholdMs,
                "Combined observe/readContext p95 exceeds " + thresholdMs + " ms; see " + output);
    }

    private static Map<String, Object> statistics(List<Double> samples) {
        List<Double> sorted = new ArrayList<>(samples);
        Collections.sort(sorted);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("median_ms", (sorted.get(49) + sorted.get(50)) / 2.0);
        result.put("p95_ms", percentile95(samples));
        result.put("max_ms", sorted.get(sorted.size() - 1));
        result.put("samples_ms", samples);
        return result;
    }

    private static double percentile95(List<Double> samples) {
        List<Double> sorted = new ArrayList<>(samples);
        Collections.sort(sorted);
        return sorted.get((int) Math.ceil(samples.size() * 0.95) - 1);
    }
}
