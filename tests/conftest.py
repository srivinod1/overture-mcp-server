"""
Global test fixtures for the Overture Maps MCP Server.

Provides:
- DuckDB connections (empty and loaded with fixture data)
- Known coordinate points for consistent test data
- Fixture file paths
- Category taxonomy cache
"""

import json
import os
import pathlib

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PLACES_PARQUET = str(FIXTURES_DIR / "sample_places.parquet")
BUILDINGS_PARQUET = str(FIXTURES_DIR / "sample_buildings.parquet")
DIVISIONS_PARQUET = str(FIXTURES_DIR / "sample_divisions.parquet")
CATEGORIES_JSON = str(FIXTURES_DIR / "categories.json")


# ---------------------------------------------------------------------------
# Coordinate fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def amsterdam_center() -> dict:
    """Center of all fixture data. Lat/Lng for Amsterdam."""
    return {"lat": 52.3676, "lng": 4.9041}


@pytest.fixture
def ocean_point() -> dict:
    """Gulf of Guinea — no nearby places or buildings in fixtures."""
    return {"lat": 0.0, "lng": 0.0}


@pytest.fixture
def north_pole() -> dict:
    """North pole — extreme latitude edge case."""
    return {"lat": 90.0, "lng": 0.0}


@pytest.fixture
def south_pole() -> dict:
    """South pole — extreme latitude edge case."""
    return {"lat": -90.0, "lng": 0.0}


@pytest.fixture
def date_line_point() -> dict:
    """International date line — extreme longitude edge case."""
    return {"lat": 0.0, "lng": 180.0}


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_api_key() -> str:
    """Valid API key for auth tests."""
    return "test-key-12345"


# ---------------------------------------------------------------------------
# Category fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def category_taxonomy() -> list[dict]:
    """Load the category taxonomy from the fixture file."""
    with open(CATEGORIES_JSON) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def category_names(category_taxonomy) -> set[str]:
    """Set of all valid category names from the taxonomy."""
    return {c["category"] for c in category_taxonomy}


# ---------------------------------------------------------------------------
# DuckDB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_duckdb() -> duckdb.DuckDBPyConnection:
    """
    In-memory DuckDB with spatial extension loaded. No data.
    Use for unit tests that need DuckDB SQL parsing but not fixture data.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn


@pytest.fixture(scope="session")
def loaded_fixture_db() -> duckdb.DuckDBPyConnection:
    """
    Session-scoped DuckDB loaded with all fixture parquet files as views.

    Provides these views:
      - places: 50 records from sample_places.parquet
      - buildings: 50 records from sample_buildings.parquet
      - divisions: 10 records from sample_divisions.parquet

    Shared across all tests in a session for speed.
    Uses views (not tables) so the parquet files are the source of truth.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")

    # Create views pointing to fixture parquet files
    conn.execute(f"CREATE VIEW places AS SELECT * FROM read_parquet('{PLACES_PARQUET}')")
    conn.execute(f"CREATE VIEW buildings AS SELECT * FROM read_parquet('{BUILDINGS_PARQUET}')")
    conn.execute(f"CREATE VIEW divisions AS SELECT * FROM read_parquet('{DIVISIONS_PARQUET}')")

    # Sanity check: verify data loaded correctly
    place_count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    building_count = conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
    division_count = conn.execute("SELECT COUNT(*) FROM divisions").fetchone()[0]
    assert place_count == 50, f"Expected 50 places, got {place_count}"
    assert building_count == 50, f"Expected 50 buildings, got {building_count}"
    assert division_count == 10, f"Expected 10 divisions, got {division_count}"

    return conn


# ---------------------------------------------------------------------------
# Fixture data constants (known values for exact assertions)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def known_coffee_shop_count() -> int:
    """Total number of coffee shops in fixtures."""
    return 10


@pytest.fixture(scope="session")
def known_coffee_shops_within_500m() -> int:
    """Number of coffee shops within 500m of amsterdam_center.
    Includes Java Junction at ~496m, excludes Far Away Beans at ~506m.
    """
    return 9


@pytest.fixture(scope="session")
def known_nearest_coffee_shop() -> dict:
    """The closest coffee shop to amsterdam_center."""
    return {"name": "Koffie Centrum", "distance_m": 95}


@pytest.fixture(scope="session")
def known_building_composition() -> dict:
    """Expected building class breakdown for all 50 fixture buildings."""
    return {
        "residential": 20,
        "commercial": 10,
        "industrial": 5,
        "unknown": 15,
        "total": 50,
    }


@pytest.fixture(scope="session")
def known_null_name_count() -> int:
    """Number of places with null names in fixtures."""
    return 5


@pytest.fixture(scope="session")
def known_divisions_containing_center() -> list[dict]:
    """Admin boundaries that contain amsterdam_center, ordered by admin_level."""
    return [
        {"name": "Netherlands", "admin_level": 2, "subtype": "country"},
        {"name": "North Holland", "admin_level": 4, "subtype": "region"},
        {"name": "Amsterdam", "admin_level": 8, "subtype": "locality"},
    ]


# ---------------------------------------------------------------------------
# Fixture file path helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def places_parquet_path() -> str:
    """Absolute path to the places fixture parquet file."""
    return PLACES_PARQUET


@pytest.fixture(scope="session")
def buildings_parquet_path() -> str:
    """Absolute path to the buildings fixture parquet file."""
    return BUILDINGS_PARQUET


@pytest.fixture(scope="session")
def divisions_parquet_path() -> str:
    """Absolute path to the divisions fixture parquet file."""
    return DIVISIONS_PARQUET


# ---------------------------------------------------------------------------
# Operation test fixtures (for integration tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_config() -> "ServerConfig":
    """Server config pointing to local fixture data instead of S3."""
    from overture_mcp.config import ServerConfig
    return ServerConfig(
        api_key="test-key-12345",
        _places_source="places",
        _buildings_source="buildings",
        _divisions_source="divisions",
    )


@pytest.fixture(scope="session")
def test_db() -> "Database":
    """Database initialized with local fixture data."""
    from overture_mcp.db import Database
    from overture_mcp.config import ServerConfig

    config = ServerConfig(api_key="test-key-12345")
    db = Database(config)
    db.initialize_local(
        places_path=PLACES_PARQUET,
        buildings_path=BUILDINGS_PARQUET,
        divisions_path=DIVISIONS_PARQUET,
    )
    return db


@pytest.fixture(scope="session")
def test_registry(test_db, test_config, category_taxonomy) -> "OperationRegistry":
    """Fully populated operation registry wired to fixture data."""
    from overture_mcp.server import build_registry
    return build_registry(test_db, test_config, category_taxonomy)
