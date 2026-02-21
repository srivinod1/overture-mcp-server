# Test Strategy

This document defines the comprehensive test plan for the Overture Maps MCP Server. Tests are designed to validate correctness, security, performance, and real-world agent workflows — not just happy-path functionality.

---

## Principles

- **More tests > fewer tests.** When in doubt, add the test.
- **Deterministic fixtures.** Tests assert exact values against known data. No "check if count > 0" unless testing live S3.
- **No S3 in CI.** The default test suite runs entirely against local parquet fixtures. S3-dependent tests are marked and skipped in CI.
- **Test the contract, not the internals.** Unit tests verify inputs → outputs. Integration tests verify the full operation pipeline. Don't test private methods directly.
- **Edge cases are first-class.** Null names, empty results, boundary coordinates, oversized geometry, and injection payloads all have dedicated tests.

---

## Test Directory Structure

```
tests/
├── conftest.py                           # Global fixtures (DuckDB, servers, known coords)
├── fixtures/
│   ├── generate_fixtures.py              # Script to create deterministic parquet files
│   ├── sample_places.parquet             # 50 known places near Amsterdam
│   ├── sample_buildings.parquet          # 50 known buildings near Amsterdam
│   ├── sample_divisions.parquet          # 10 known admin boundaries
│   └── categories.json                   # Category taxonomy snapshot (~200 categories)
│
├── unit/                                 # No DuckDB, no S3, no server
│   ├── test_query_builders_places.py     # SQL generation for places theme
│   ├── test_query_builders_buildings.py  # SQL generation for buildings theme
│   ├── test_query_builders_divisions.py  # SQL generation for divisions theme
│   ├── test_validation.py               # Parameter validation logic
│   ├── test_response.py                 # Response envelope builder
│   ├── test_registry.py                 # Operation registry: lookup, schema, listing
│   ├── test_config.py                   # Config loading, env var handling
│   └── test_bbox.py                     # Bounding box computation from radius
│
├── integration/                          # DuckDB + local parquet fixtures, no S3
│   ├── test_duckdb_places.py            # Place queries against fixture data
│   ├── test_duckdb_buildings.py         # Building queries against fixture data
│   ├── test_duckdb_divisions.py         # Division queries against fixture data
│   ├── test_db_connection.py            # Connection lifecycle, semaphore behavior
│   ├── test_server_direct.py            # FastMCP direct mode tool calls
│   ├── test_server_progressive.py       # FastMCP progressive mode tool calls
│   └── test_auth.py                     # API key middleware
│
├── e2e/                                  # Multi-operation agent workflows
│   ├── test_retail_site_selection.py     # Evaluate retail locations across metrics
│   ├── test_insurance_risk.py           # Building composition for risk assessment
│   ├── test_customer_segmentation.py    # Area profiling for audience analysis
│   ├── test_advertising_competitor.py   # Competitor density analysis
│   └── test_multi_mcp_workflow.py       # Simulated geocoding → Overture pipeline
│
├── edge/                                 # Boundary values, nulls, empty results
│   ├── test_boundary_values.py          # Min/max radius, coordinates at limits
│   ├── test_null_handling.py            # Null names, null building classes
│   ├── test_empty_results.py            # Valid queries that return zero results
│   └── test_invalid_inputs.py           # Wrong types, missing params, out of range
│
├── security/                             # Injection, tampering, auth bypass
│   ├── test_sql_injection.py            # SQL injection via all string params
│   ├── test_parameter_tampering.py      # Oversized radius, negative values, NaN/Inf
│   └── test_auth_bypass.py             # Missing key, wrong key, empty key, header manipulation
│
├── performance/                          # Latency, concurrency, memory
│   ├── test_latency_baselines.py        # @pytest.mark.s3 — latency against real S3
│   ├── test_concurrency.py              # Semaphore behavior under parallel load
│   └── test_memory.py                   # @pytest.mark.s3 — memory usage under load
│
└── compatibility/                        # Direct vs progressive mode equivalence
    └── test_mode_parity.py              # Same params → same results in both modes
```

---

## Fixture Data Design

All fixture data is deterministic and pre-generated. Tests make exact assertions (not "result count > 0").

### Reference Point

All fixture data is centered around Amsterdam:
```
amsterdam_center = {"lat": 52.3676, "lng": 4.9041}
```

### `sample_places.parquet` — 50 Records

| Category | Count | Distance Range from Center | Notes |
|----------|-------|---------------------------|-------|
| `coffee_shop` | 10 | 95m – 480m | Known distances for ordering tests |
| `restaurant` | 8 | 100m – 450m | |
| `bank` | 5 | 150m – 400m | |
| `hospital` | 5 | 200m – 490m | |
| `atm` | 3 | 120m – 350m | |
| `pharmacy` | 2 | 180m – 300m | |
| Other categories | 17 | 50m – 500m | Variety for taxonomy tests |

Additional properties:
- 5 places have `names.primary = NULL` (tests null name handling)
- All places within ~500m of center (tests radius boundary exactly)
- 1 coffee_shop at exactly 495m (tests inclusive/exclusive boundary)
- 1 coffee_shop at exactly 505m (just outside 500m radius)
- Categories match entries in `categories.json`

### `sample_buildings.parquet` — 50 Records

| Class | Count | Notes |
|-------|-------|-------|
| `residential` | 20 | |
| `commercial` | 10 | |
| `industrial` | 5 | |
| `NULL` (unknown) | 15 | Tests null class → "unknown" mapping |

Additional properties:
- All within ~1000m of center
- Polygon geometries (not points)
- 1 building with very large geometry (>10,000 char WKT) for geometry cap test

### `sample_divisions.parquet` — 10 Records

| Name | Admin Level | Contains Center? |
|------|-------------|------------------|
| Netherlands | 2 | Yes |
| North Holland | 4 | Yes |
| Amsterdam | 8 | Yes |
| Germany | 2 | No |
| Bavaria | 4 | No |
| Munich | 8 | No |
| France | 2 | No |
| 3 additional | Various | Mixed |

This supports both positive tests (point in Amsterdam → Netherlands, North Holland, Amsterdam) and negative tests (point in Amsterdam → NOT Germany, Bavaria, Munich).

### `categories.json` — ~200 Categories

A snapshot of the Overture category taxonomy including:
- All categories used in fixture places
- Hierarchical structure (`eat_and_drink.coffee.coffee_shop`)
- Enough variety for `get_place_categories` search tests

### `generate_fixtures.py`

A standalone script that creates all parquet files deterministically:
```bash
python tests/fixtures/generate_fixtures.py
```

Uses DuckDB to write GeoParquet with exact coordinates, names, categories, and geometries. Running the script twice produces identical files. The script is committed to the repo so any contributor can regenerate fixtures.

---

## Shared Fixtures (`tests/conftest.py`)

### Database Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `mock_duckdb` | function | In-memory DuckDB with spatial extension loaded. No data. |
| `loaded_fixture_db` | session | DuckDB loaded with all 3 fixture parquet files as tables. Shared across tests for speed. |

### Server Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `mock_registry` | session | Operation registry populated with all 7 operations, wired to `loaded_fixture_db`. |
| `direct_server` | session | FastMCP server instance in `TOOL_MODE=direct`, using fixture DB. |
| `progressive_server` | session | FastMCP server instance in `TOOL_MODE=progressive`, using fixture DB. |

### Constant Fixtures

| Fixture | Value | Description |
|---------|-------|-------------|
| `valid_api_key` | `"test-key-12345"` | Valid API key for auth tests. |
| `amsterdam_center` | `{"lat": 52.3676, "lng": 4.9041}` | Center of all fixture data. |
| `ocean_point` | `{"lat": 0.0, "lng": 0.0}` | Gulf of Guinea — no nearby places or buildings. |
| `north_pole` | `{"lat": 90.0, "lng": 0.0}` | Extreme latitude edge case. |
| `south_pole` | `{"lat": -90.0, "lng": 0.0}` | Extreme latitude edge case. |
| `date_line_point` | `{"lat": 0.0, "lng": 180.0}` | International date line edge case. |

---

## Test Categories

### 1. Unit Tests (~68 tests)

Unit tests verify individual functions in isolation. No DuckDB, no S3, no server. Pure input → output.

#### `test_query_builders_places.py` (~8 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_places_in_radius_sql_structure` | Generated SQL has correct SELECT, WHERE, ORDER BY, LIMIT clauses |
| `test_places_in_radius_coordinate_order` | `ST_Point(lng, lat)` — not `ST_Point(lat, lng)` |
| `test_places_in_radius_bbox_params` | Bbox deltas computed correctly from radius and latitude |
| `test_places_in_radius_parameterized_category` | Category appears as `?` placeholder, not string literal |
| `test_places_in_radius_include_geometry` | Geometry column added to SELECT when `include_geometry=true` |
| `test_nearest_place_sql_limit_one` | SQL has `LIMIT 1` |
| `test_count_places_sql_count_only` | SQL uses `COUNT(*)`, no name/lat/lng columns |
| `test_categories_query_substring_match` | Category search filters by case-insensitive substring |

#### `test_query_builders_buildings.py` (~5 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_building_count_sql_structure` | COUNT(*) query with bbox + spheroid filter |
| `test_building_composition_sql_groupby` | GROUP BY COALESCE(class, 'unknown') |
| `test_building_composition_sql_order` | ORDER BY count DESC |
| `test_building_bbox_params` | Bbox deltas correct for building queries |
| `test_building_no_category_filter` | No `categories.primary` in WHERE clause |

#### `test_query_builders_divisions.py` (~3 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_division_sql_contains` | Uses `ST_Contains` not `ST_Distance_Spheroid` |
| `test_division_bbox_point_containment` | Bbox filter uses `<=` / `>=` (containment, not range) |
| `test_division_order_by_admin_level` | Results ordered by `admin_level ASC` |

#### `test_validation.py` (~22 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_lat_valid_range` | -90 to 90 accepted |
| `test_lat_below_min` | -90.001 rejected |
| `test_lat_above_max` | 90.001 rejected |
| `test_lng_valid_range` | -180 to 180 accepted |
| `test_lng_below_min` | -180.001 rejected |
| `test_lng_above_max` | 180.001 rejected |
| `test_radius_valid_range` | 1 to 50000 accepted |
| `test_radius_zero` | 0 rejected |
| `test_radius_negative` | -100 rejected |
| `test_radius_above_max` | 50001 rejected |
| `test_limit_valid_range` | 1 to 100 accepted |
| `test_limit_zero` | 0 rejected |
| `test_limit_above_max` | 101 rejected |
| `test_limit_default` | Omitted → defaults to 20 |
| `test_category_valid` | Known category accepted |
| `test_category_unknown` | Unknown category rejected with helpful error |
| `test_category_empty_string` | Empty string rejected |
| `test_category_none_when_required` | None rejected for operations that require it |
| `test_lat_not_a_number` | String "abc" rejected |
| `test_radius_float` | Float 500.5 accepted (cast to int) or rejected (depending on decision) |
| `test_missing_required_param` | Missing `lat` returns clear error |
| `test_extra_unknown_params` | Unknown params ignored (not error) |

#### `test_response.py` (~8 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_success_envelope_structure` | Has results, count, query_params, data_version, suggestion fields |
| `test_success_envelope_count_matches` | `count` equals `len(results)` |
| `test_success_envelope_suggestion_null` | suggestion is null when results exist |
| `test_empty_envelope_suggestion` | suggestion is populated when results empty |
| `test_empty_envelope_results_array` | results is `[]` not `null` |
| `test_error_envelope_structure` | Has error, error_type, query_params fields |
| `test_error_types` | All 4 error types produce valid envelopes |
| `test_query_params_echoed` | Input params appear in query_params unchanged |

#### `test_registry.py` (~8 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_all_v1_operations_registered` | 7 operations in registry |
| `test_operation_has_required_fields` | Each entry has name, description, parameters, handler, theme |
| `test_list_operations_returns_all` | `list_operations` returns all 7 with name + description |
| `test_list_operations_grouped_by_theme` | Results grouped by places, buildings, divisions |
| `test_get_schema_known_operation` | Returns full parameter schema for known operation |
| `test_get_schema_unknown_operation` | Returns helpful error for unknown operation name |
| `test_get_schema_includes_example` | Each schema includes a valid example |
| `test_operation_names_are_snake_case` | All operation names follow `snake_case` convention |

#### `test_config.py` (~8 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_default_tool_mode` | Default is "direct" |
| `test_tool_mode_progressive` | `TOOL_MODE=progressive` parsed correctly |
| `test_tool_mode_invalid` | Invalid mode raises error at startup |
| `test_default_data_version` | Default is "2026-01-21.0" |
| `test_data_version_override` | Env var overrides default |
| `test_default_max_concurrent` | Default is 3 |
| `test_default_max_radius` | Default is 50000 |
| `test_s3_path_construction` | Version + theme + type → correct S3 path |

#### `test_bbox.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_bbox_delta_equator` | At lat=0, lng_delta ≈ lat_delta (cos(0)=1) |
| `test_bbox_delta_high_latitude` | At lat=60, lng_delta > lat_delta (cos(60)=0.5) |
| `test_bbox_delta_500m` | 500m radius → ~0.0045 degree delta at equator |
| `test_bbox_delta_50km` | 50km radius → ~0.45 degree delta at equator |
| `test_bbox_delta_pole` | Near pole, lng_delta is very large (cos→0) — verify no division by zero |
| `test_bbox_always_larger_than_radius` | Bbox always contains the circle (generous, never clips) |

---

### 2. Integration Tests (~36 tests)

Integration tests run queries against local parquet fixtures via DuckDB. No S3.

#### `test_duckdb_places.py` (~8 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_places_in_radius_returns_correct_count` | 500m radius, coffee_shop → 10 results (all fixture coffee shops) |
| `test_places_in_radius_ordered_by_distance` | Results are ascending by `distance_m` |
| `test_places_in_radius_distance_accuracy` | Nearest coffee shop distance matches expected haversine within 1% |
| `test_places_in_radius_respects_limit` | `limit=3` → exactly 3 results |
| `test_places_in_radius_excludes_outside_radius` | 400m radius excludes coffee shops at 410m+ |
| `test_nearest_place_returns_one` | Returns exactly 1 result (closest coffee shop) |
| `test_nearest_place_correct_name` | Returns the known closest coffee shop by name |
| `test_count_places_matches_search` | Count matches number of results from `places_in_radius` for same params |

#### `test_duckdb_buildings.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_building_count_total` | 1000m radius → 50 buildings (all fixtures) |
| `test_building_composition_percentages` | residential=40%, commercial=20%, industrial=10%, unknown=30% |
| `test_building_composition_sums_to_100` | All percentages sum to 100.0 |
| `test_building_composition_count_matches_total` | Sum of class counts = total_buildings |
| `test_building_count_smaller_radius` | 200m radius → fewer than 50 |
| `test_building_null_class_mapped_to_unknown` | NULL class appears as "unknown" in composition |

#### `test_duckdb_divisions.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_point_in_amsterdam_returns_hierarchy` | Returns Netherlands (2), North Holland (4), Amsterdam (8) |
| `test_point_in_amsterdam_admin_levels_ascending` | Levels ordered 2, 4, 8 |
| `test_point_not_in_germany` | Germany NOT in results for Amsterdam point |
| `test_ocean_point_returns_empty_or_minimal` | Point at (0,0) returns few or no boundaries |
| `test_locality_field_populated` | `locality` = "Amsterdam" |
| `test_country_field_populated` | `country` = "Netherlands" |

#### `test_db_connection.py` (~4 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_connection_initializes_spatial` | Spatial extension loaded and functional |
| `test_connection_initializes_httpfs` | httpfs extension loaded |
| `test_semaphore_limits_concurrency` | With semaphore(2), 3 simultaneous queries → max 2 concurrent |
| `test_semaphore_released_on_error` | Query that raises exception still releases semaphore |

#### `test_server_direct.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_direct_mode_registers_all_tools` | 7 tools registered |
| `test_direct_mode_tool_names` | Tool names match operation names |
| `test_direct_mode_tool_schemas` | Each tool has correct parameter schema |
| `test_direct_mode_call_places_in_radius` | End-to-end tool call returns correct results |
| `test_direct_mode_call_with_invalid_params` | Returns validation error, not crash |
| `test_direct_mode_call_unknown_tool` | Returns helpful error |

#### `test_server_progressive.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_progressive_mode_registers_three_tools` | Exactly 3 tools: list, schema, execute |
| `test_progressive_list_operations` | Returns all 7 operations with names and descriptions |
| `test_progressive_get_schema` | Returns full parameter schema for known operation |
| `test_progressive_get_schema_unknown` | Returns helpful error for unknown operation |
| `test_progressive_execute_operation` | End-to-end call returns correct results |
| `test_progressive_execute_unknown_operation` | Returns helpful error |

---

### 3. End-to-End Workflow Tests (~12 tests)

These simulate real-world agent workflows that chain multiple operations. They validate that the server supports the use cases we designed for.

#### `test_retail_site_selection.py` (~3 tests)

Scenario: An agent evaluates 3 potential retail store locations by querying multiple metrics per location.

| Test | What It Verifies |
|------|-----------------|
| `test_evaluate_three_locations` | For each of 3 points: places_in_radius + building_count + building_composition all succeed |
| `test_building_count_matches_composition` | `building_count_in_radius` count == sum of `building_class_composition` class counts for same point/radius |
| `test_empty_location_handled` | A point with no nearby places returns structured empty result (not error) |

#### `test_insurance_risk.py` (~2 tests)

Scenario: An agent assesses building risk profile for an area.

| Test | What It Verifies |
|------|-----------------|
| `test_building_profile_for_area` | building_class_composition returns valid breakdown for known area |
| `test_admin_boundary_for_context` | point_in_admin_boundary returns region/country for the same point |

#### `test_customer_segmentation.py` (~3 tests)

Scenario: An agent profiles an area by combining place types and building composition.

| Test | What It Verifies |
|------|-----------------|
| `test_area_amenity_profile` | Count restaurants, banks, hospitals in area → all return valid counts |
| `test_residential_vs_commercial_ratio` | Building composition residential% and commercial% are both > 0 |
| `test_multiple_radii_comparison` | Same point at 500m and 1000m → larger radius has >= count |

#### `test_advertising_competitor.py` (~2 tests)

Scenario: An agent maps competitor density for a brand.

| Test | What It Verifies |
|------|-----------------|
| `test_competitor_density_multiple_locations` | count_places_by_type for same category at 3 points → all return valid counts |
| `test_nearest_competitor` | nearest_place_of_type returns closest competitor with distance |

#### `test_multi_mcp_workflow.py` (~2 tests)

Scenario: Simulates the workflow where a geocoding MCP returns coordinates, then Overture operations are called.

| Test | What It Verifies |
|------|-----------------|
| `test_geocode_then_analyze` | Given coordinates (simulating geocoding output), chain places_in_radius + building_composition + point_in_admin_boundary |
| `test_multiple_geocoded_points` | 3 different coordinate sets → all 3 return valid, independent results |

---

### 4. Edge Case Tests (~30 tests)

#### `test_boundary_values.py` (~10 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_lat_exactly_90` | North pole accepted |
| `test_lat_exactly_negative_90` | South pole accepted |
| `test_lng_exactly_180` | Date line accepted |
| `test_lng_exactly_negative_180` | Date line accepted |
| `test_radius_exactly_1` | Minimum radius accepted |
| `test_radius_exactly_50000` | Maximum radius accepted |
| `test_limit_exactly_1` | Returns exactly 1 result |
| `test_limit_exactly_100` | Returns up to 100 results |
| `test_place_at_exact_radius_boundary` | Place at 500m included in 500m search (inclusive) |
| `test_place_just_outside_radius` | Place at 505m excluded from 500m search |

#### `test_null_handling.py` (~8 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_place_with_null_name` | Place with null name appears in results with `name: null` |
| `test_null_name_does_not_crash` | Query doesn't error on null name |
| `test_building_null_class_is_unknown` | Null class mapped to "unknown" in composition |
| `test_null_class_counted` | Null-class buildings included in total count |
| `test_null_categories_alternate` | Place with null alternate categories handled gracefully |
| `test_null_confidence` | Null confidence score doesn't affect results |
| `test_null_websites` | Null websites field doesn't affect results |
| `test_null_phones` | Null phones field doesn't affect results |

#### `test_empty_results.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_no_places_in_ocean` | Ocean point → empty results, not error |
| `test_empty_result_has_suggestion` | Empty result includes helpful suggestion string |
| `test_empty_result_count_is_zero` | `count: 0` in response |
| `test_empty_result_is_array` | `results: []` not `results: null` |
| `test_no_buildings_in_ocean` | Ocean point → empty building results |
| `test_rare_category_no_results` | Valid but rare category → empty results with suggestion |

#### `test_invalid_inputs.py` (~6 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_lat_as_string` | `lat: "abc"` → validation_error |
| `test_radius_as_negative` | `radius_m: -100` → validation_error |
| `test_missing_required_lat` | No `lat` param → validation_error with field name |
| `test_missing_required_category` | No `category` for places_in_radius → validation_error |
| `test_nan_latitude` | `lat: NaN` → validation_error |
| `test_infinity_longitude` | `lng: Infinity` → validation_error |

---

### 5. Security Tests (~17 tests)

#### `test_sql_injection.py` (~8 tests)

All tests verify that malicious input is either rejected by validation or safely parameterized — never executed as SQL.

| Test | What It Verifies |
|------|-----------------|
| `test_category_drop_table` | `category="'; DROP TABLE places; --"` → rejected by category validation |
| `test_category_union_select` | `category="x' UNION SELECT * FROM information_schema.tables --"` → rejected |
| `test_category_semicolon` | `category="coffee_shop; SELECT 1"` → rejected |
| `test_category_comment` | `category="coffee_shop --"` → rejected |
| `test_query_injection` | `query="'; DROP TABLE places; --"` in get_place_categories → no SQL executed |
| `test_query_union` | `query="x' UNION SELECT * --"` → safe (returns no matching categories) |
| `test_numeric_param_string_injection` | `lat="52.37; DROP TABLE"` → rejected by type validation |
| `test_all_string_params_parameterized` | Verify no string interpolation in generated SQL for any operation |

#### `test_parameter_tampering.py` (~5 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_radius_100km` | `radius_m: 100000` → rejected (max 50km) |
| `test_limit_1000` | `limit: 1000` → rejected (max 100) |
| `test_negative_radius` | `radius_m: -1` → rejected |
| `test_lat_200` | `lat: 200` → rejected |
| `test_float_overflow` | `lat: 1e308` → rejected |

#### `test_auth_bypass.py` (~4 tests)

| Test | What It Verifies |
|------|-----------------|
| `test_no_api_key` | Request without X-API-Key header → 401 auth_error |
| `test_wrong_api_key` | Wrong key value → 401 auth_error |
| `test_empty_api_key` | Empty string key → 401 auth_error |
| `test_api_key_in_query_param` | Key in URL query param (not header) → 401 auth_error |

---

### 6. Performance Tests (~18 tests)

Performance tests are split: concurrency tests run locally, latency/memory tests require S3.

#### `test_concurrency.py` (~6 tests, local)

| Test | What It Verifies |
|------|-----------------|
| `test_semaphore_3_allows_3_concurrent` | 3 simultaneous queries all run concurrently |
| `test_semaphore_3_queues_4th` | 4th query waits until a slot opens |
| `test_semaphore_3_completes_5_queries` | 5 queries all complete (none dropped) |
| `test_semaphore_released_on_timeout` | Timed-out query releases semaphore |
| `test_semaphore_released_on_exception` | Failed query releases semaphore (no deadlock) |
| `test_concurrent_different_operations` | Mixed operations (places + buildings + divisions) run concurrently without interference |

#### `test_latency_baselines.py` (~6 tests, `@pytest.mark.s3`)

| Test | What It Verifies |
|------|-----------------|
| `test_places_in_radius_500m_under_5s` | places_in_radius 500m completes < 5s |
| `test_places_in_radius_5km_under_10s` | places_in_radius 5km completes < 10s |
| `test_building_count_1km_under_5s` | building_count_in_radius 1km completes < 5s |
| `test_building_composition_1km_under_5s` | building_class_composition 1km completes < 5s |
| `test_point_in_admin_boundary_under_10s` | point_in_admin_boundary completes < 10s |
| `test_get_place_categories_under_100ms` | Category lookup completes < 100ms (cached) |

#### `test_memory.py` (~6 tests, `@pytest.mark.s3`)

| Test | What It Verifies |
|------|-----------------|
| `test_single_query_memory_under_200mb` | Single places query peak memory < 200MB |
| `test_large_radius_memory_under_500mb` | 50km building query peak memory < 500MB |
| `test_concurrent_queries_memory_under_800mb` | 3 concurrent queries total memory < 800MB |
| `test_memory_released_after_query` | Memory returns to baseline after query completes |
| `test_no_memory_leak_100_queries` | 100 sequential queries don't grow memory |
| `test_large_geometry_memory` | include_geometry=true doesn't cause memory spike |

---

### 7. Compatibility Tests (~9 tests)

#### `test_mode_parity.py`

Verifies that direct mode and progressive mode return identical results for the same inputs.

| Test | What It Verifies |
|------|-----------------|
| `test_parity_places_in_radius` | Same params → same results in both modes |
| `test_parity_nearest_place` | Same params → same results |
| `test_parity_count_places` | Same params → same results |
| `test_parity_building_count` | Same params → same results |
| `test_parity_building_composition` | Same params → same results |
| `test_parity_point_in_admin` | Same params → same results |
| `test_parity_get_categories` | Same params → same results |
| `test_parity_empty_results` | Both modes return identical empty response structure |
| `test_parity_validation_errors` | Both modes return identical error for invalid params |

---

## Test Summary

| Category | Test Count | Hits S3? | Runtime |
|----------|-----------|----------|---------|
| Unit: Query builders | 16 | No | <1s |
| Unit: Validation | 22 | No | <1s |
| Unit: Response/Registry/Config/Bbox | 30 | No | <1s |
| Integration: DuckDB queries | 20 | No | <5s |
| Integration: Server + Auth | 16 | No | <5s |
| E2E: Use case workflows | 12 | No | <10s |
| Edge: Boundaries, nulls, empty, invalid | 30 | No | <5s |
| Security: Injection, tampering, auth | 17 | No | <3s |
| Performance: Concurrency | 6 | No | <10s |
| Performance: Latency + Memory | 12 | Yes | 2-5 min |
| Compatibility: Mode parity | 9 | No | <5s |
| **Total** | **~190** | | |

---

## Run Configurations

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Fast CI — unit + edge + security (no DuckDB, no S3)
pytest tests/unit tests/edge tests/security -m "not s3" -x --timeout=10

# Full local — everything except S3-dependent tests
pytest tests/ -m "not s3" --timeout=30

# Full with S3 — requires network access
pytest tests/ --timeout=60

# Security only
pytest tests/security -v

# Performance baselines (requires S3)
pytest tests/performance -m s3 --timeout=120

# Single test category
pytest tests/integration/test_duckdb_places.py -v
```

### Pytest Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "s3: tests that require S3 network access (deselect with '-m not s3')",
    "slow: tests that take >10 seconds",
]
timeout = 30
```

### Custom Markers

- `@pytest.mark.s3` — requires network access to Overture S3 bucket. Skipped in CI by default.
- `@pytest.mark.slow` — takes >10 seconds. Can be excluded for rapid iteration.

---

## CI/CD Integration

### GitHub Actions Pipeline

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: python tests/fixtures/generate_fixtures.py
      - run: pytest tests/ -m "not s3" --timeout=30 --tb=short
```

### Nightly S3 Tests (Optional)

```yaml
# .github/workflows/nightly.yml
name: Nightly S3 Tests
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily

jobs:
  s3-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ --timeout=120 --tb=short
```

---

## Writing New Tests

When adding a new operation to the registry, add tests in this order:

1. **Unit test** in `tests/unit/test_query_builders_{theme}.py` — verify SQL generation
2. **Add fixture data** to the relevant parquet file if needed
3. **Integration test** in `tests/integration/test_duckdb_{theme}.py` — verify query against fixtures
4. **Edge case tests** in `tests/edge/` — boundary values, nulls, empty results
5. **Security test** if the operation accepts string params — verify injection safety
6. **Mode parity test** in `tests/compatibility/test_mode_parity.py` — verify both modes return same results
7. **E2E test** if the operation enables a new use case workflow
