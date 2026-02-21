#!/usr/bin/env python3
"""
Generate deterministic test fixture parquet files for the Overture Maps MCP Server.

Run:
    python tests/fixtures/generate_fixtures.py

Produces:
    tests/fixtures/sample_places.parquet
    tests/fixtures/sample_buildings.parquet
    tests/fixtures/sample_divisions.parquet
    tests/fixtures/categories.json

All data is centered around Amsterdam (52.3676, 4.9041).
Running this script twice produces identical files.
"""

import json
import math
import os
import sys

try:
    import duckdb
except ImportError:
    print("Error: duckdb is required. Install with: pip install duckdb")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CENTER_LAT = 52.3676
CENTER_LNG = 4.9041

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))

# Earth radius in meters (WGS84 mean)
EARTH_RADIUS_M = 6_371_000


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def offset_point(lat: float, lng: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """
    Compute a new (lat, lng) given a starting point, bearing (degrees), and distance (meters).
    Uses the Vincenty direct formula approximation (spherical).
    Returns (new_lat, new_lng).
    """
    lat_r = math.radians(lat)
    lng_r = math.radians(lng)
    bearing_r = math.radians(bearing_deg)
    d = distance_m / EARTH_RADIUS_M

    new_lat_r = math.asin(
        math.sin(lat_r) * math.cos(d) +
        math.cos(lat_r) * math.sin(d) * math.cos(bearing_r)
    )
    new_lng_r = lng_r + math.atan2(
        math.sin(bearing_r) * math.sin(d) * math.cos(lat_r),
        math.cos(d) - math.sin(lat_r) * math.sin(new_lat_r)
    )

    return round(math.degrees(new_lat_r), 7), round(math.degrees(new_lng_r), 7)


def make_polygon_wkt(center_lat: float, center_lng: float, size_m: float = 20) -> str:
    """Create a small square polygon WKT centered at (lat, lng)."""
    half = size_m / 2
    nw = offset_point(center_lat, center_lng, 315, half * math.sqrt(2))
    ne = offset_point(center_lat, center_lng, 45, half * math.sqrt(2))
    se = offset_point(center_lat, center_lng, 135, half * math.sqrt(2))
    sw = offset_point(center_lat, center_lng, 225, half * math.sqrt(2))
    # WKT polygon: POLYGON((lng lat, lng lat, ...))
    coords = ", ".join(f"{p[1]} {p[0]}" for p in [nw, ne, se, sw, nw])
    return f"POLYGON(({coords}))"


def make_large_polygon_wkt(center_lat: float, center_lng: float, num_points: int = 500, radius_m: float = 50) -> str:
    """Create a polygon with many vertices to exceed 10,000 char WKT limit."""
    points = []
    for i in range(num_points):
        bearing = (360.0 / num_points) * i
        lat, lng = offset_point(center_lat, center_lng, bearing, radius_m)
        points.append(f"{lng} {lat}")
    points.append(points[0])  # close the ring
    coords = ", ".join(points)
    return f"POLYGON(({coords}))"


def make_division_polygon_wkt(center_lat: float, center_lng: float, radius_km: float) -> str:
    """Create a rough circular polygon for admin boundaries."""
    points = []
    num_points = 36  # every 10 degrees
    for i in range(num_points):
        bearing = (360.0 / num_points) * i
        lat, lng = offset_point(center_lat, center_lng, bearing, radius_km * 1000)
        points.append(f"{lng} {lat}")
    points.append(points[0])
    coords = ", ".join(points)
    return f"POLYGON(({coords}))"


# ---------------------------------------------------------------------------
# Place fixture data
# ---------------------------------------------------------------------------

def generate_places() -> list[dict]:
    """Generate 50 deterministic places near Amsterdam center."""
    places = []
    place_id = 0

    def add_place(name, category, distance_m, bearing_deg, alt_categories=None, has_name=True):
        nonlocal place_id
        lat, lng = offset_point(CENTER_LAT, CENTER_LNG, bearing_deg, distance_m)
        places.append({
            "id": f"place_{place_id:03d}",
            "name": name if has_name else None,
            "category": category,
            "alt_categories": alt_categories or [],
            "lat": lat,
            "lng": lng,
            "distance_m": distance_m,
            "confidence": round(0.7 + (place_id % 4) * 0.075, 3),
            "websites": [f"https://example.com/{category}/{place_id}"] if place_id % 3 == 0 else [],
            "phones": [f"+31-20-{place_id:04d}"] if place_id % 4 == 0 else [],
        })
        place_id += 1

    # 10 coffee_shops at known distances (bearings spread around center)
    add_place("Koffie Centrum", "coffee_shop", 95, 0)
    add_place("Bean There", "coffee_shop", 150, 45)
    add_place("The Daily Grind", "coffee_shop", 200, 90)
    add_place("Espresso Express", "coffee_shop", 245, 135)
    add_place("Amsterdam Roasters", "coffee_shop", 290, 180)
    add_place("Canal Coffee", "coffee_shop", 340, 225)
    add_place("Dam Square Brew", "coffee_shop", 380, 270)
    add_place("Mokum Coffee", "coffee_shop", 420, 315)
    add_place("Java Junction", "coffee_shop", 495, 30, alt_categories=["cafe"])  # boundary: inside 500m
    add_place("Far Away Beans", "coffee_shop", 505, 60)  # boundary: outside 500m

    # 8 restaurants
    add_place("Restaurant De Kas", "restaurant", 100, 10)
    add_place("Rijks Restaurant", "restaurant", 170, 55)
    add_place("Cafe Amsterdam", "restaurant", 230, 100, alt_categories=["cafe"])
    add_place("The Pancake Bakery", "restaurant", 280, 150)
    add_place("Blauw", "restaurant", 330, 200)
    add_place(None, "restaurant", 370, 250, has_name=False)  # null name
    add_place("D'Vijff Vlieghen", "restaurant", 410, 300)
    add_place("Greetje", "restaurant", 450, 350)

    # 5 banks
    add_place("ING Bank", "bank", 150, 20)
    add_place("ABN AMRO", "bank", 230, 80)
    add_place("Rabobank", "bank", 310, 160)
    add_place(None, "bank", 370, 240, has_name=False)  # null name
    add_place("SNS Bank", "bank", 400, 320)

    # 5 hospitals
    add_place("OLVG Hospital", "hospital", 200, 15)
    add_place("AMC Hospital", "hospital", 280, 75)
    add_place("VU Medical Center", "hospital", 350, 140)
    add_place(None, "hospital", 420, 210, has_name=False)  # null name
    add_place("Sint Lucas Hospital", "hospital", 490, 280)

    # 3 ATMs
    add_place("ING ATM Central", "atm", 120, 40)
    add_place("ABN ATM Dam", "atm", 250, 170)
    add_place("Rabo ATM Station", "atm", 350, 290)

    # 2 pharmacies
    add_place("Apotheek Centrum", "pharmacy", 180, 50)
    add_place("BENU Pharmacy", "pharmacy", 300, 230)

    # 17 other varied categories
    add_place("Albert Heijn", "supermarket", 50, 5)
    add_place("Bookshop XYZ", "bookstore", 110, 25)
    add_place("Parking Centrum", "parking", 160, 65)
    add_place("PostNL Office", "post_office", 210, 105)
    add_place("Shell Station", "gas_station", 260, 145)
    add_place("Anytime Fitness", "gym", 310, 185)
    add_place(None, "dentist", 350, 225, has_name=False)  # null name
    add_place("Bloemenmarkt", "florist", 390, 265)
    add_place("Pet Place", "pet_store", 430, 305)
    add_place("Cinema Tuschinski", "cinema", 470, 345)
    add_place("Vondelpark School", "school", 130, 70)
    add_place("Central Library", "library", 190, 110)
    add_place("Rijksmuseum", "museum", 240, 155)
    add_place("DHL Service Point", "courier", 290, 195)
    add_place(None, "laundry", 340, 235, has_name=False)  # null name
    add_place("Hotel Pulitzer", "hotel", 380, 275)
    add_place("Barbershop Jordaan", "barber", 420, 315)

    assert len(places) == 50, f"Expected 50 places, got {len(places)}"
    return places


# ---------------------------------------------------------------------------
# Building fixture data
# ---------------------------------------------------------------------------

def generate_buildings() -> list[dict]:
    """Generate 50 deterministic buildings near Amsterdam center."""
    buildings = []
    building_id = 0

    def add_building(building_class, distance_m, bearing_deg, size_m=20, large_geometry=False):
        nonlocal building_id
        lat, lng = offset_point(CENTER_LAT, CENTER_LNG, bearing_deg, distance_m)
        if large_geometry:
            geom = make_large_polygon_wkt(lat, lng, num_points=800, radius_m=40)
        else:
            geom = make_polygon_wkt(lat, lng, size_m=size_m)
        buildings.append({
            "id": f"bldg_{building_id:03d}",
            "name": None,  # most buildings have no name
            "class": building_class,
            "height": round(10 + (building_id % 5) * 5.0, 1) if building_class == "commercial" else None,
            "num_floors": 2 + (building_id % 4) if building_class == "residential" else None,
            "geometry_wkt": geom,
            "lat": lat,
            "lng": lng,
        })
        building_id += 1

    # 20 residential — spread in all directions
    for i in range(20):
        bearing = (360.0 / 20) * i
        distance = 100 + i * 40  # 100m to 860m
        add_building("residential", distance, bearing)

    # 10 commercial — clustered closer to center
    for i in range(10):
        bearing = (360.0 / 10) * i + 5  # offset slightly
        distance = 80 + i * 50  # 80m to 530m
        add_building("commercial", distance, bearing)

    # 5 industrial — farther out
    for i in range(5):
        bearing = (360.0 / 5) * i + 10
        distance = 500 + i * 80  # 500m to 820m
        add_building("industrial", distance, bearing)

    # 15 NULL class (unknown)
    for i in range(15):
        bearing = (360.0 / 15) * i + 15
        distance = 150 + i * 50  # 150m to 850m
        # Make one building with a very large geometry for cap testing
        large = (i == 7)
        add_building(None, distance, bearing, large_geometry=large)

    assert len(buildings) == 50, f"Expected 50 buildings, got {len(buildings)}"
    return buildings


# ---------------------------------------------------------------------------
# Division fixture data
# ---------------------------------------------------------------------------

def generate_divisions() -> list[dict]:
    """Generate 10 deterministic admin boundary divisions."""
    divisions = []

    # Boundaries that CONTAIN amsterdam_center
    divisions.append({
        "id": "div_netherlands",
        "name": "Netherlands",
        "subtype": "country",
        "admin_level": 2,
        "geometry_wkt": make_division_polygon_wkt(52.2, 5.3, radius_km=200),
        "parent_division_id": None,
    })
    divisions.append({
        "id": "div_north_holland",
        "name": "North Holland",
        "subtype": "region",
        "admin_level": 4,
        "geometry_wkt": make_division_polygon_wkt(52.5, 4.8, radius_km=50),
        "parent_division_id": "div_netherlands",
    })
    divisions.append({
        "id": "div_amsterdam",
        "name": "Amsterdam",
        "subtype": "locality",
        "admin_level": 8,
        "geometry_wkt": make_division_polygon_wkt(52.37, 4.9, radius_km=8),
        "parent_division_id": "div_north_holland",
    })

    # Boundaries that do NOT contain amsterdam_center
    divisions.append({
        "id": "div_germany",
        "name": "Germany",
        "subtype": "country",
        "admin_level": 2,
        "geometry_wkt": make_division_polygon_wkt(51.0, 10.0, radius_km=300),
        "parent_division_id": None,
    })
    divisions.append({
        "id": "div_bavaria",
        "name": "Bavaria",
        "subtype": "region",
        "admin_level": 4,
        "geometry_wkt": make_division_polygon_wkt(48.8, 11.5, radius_km=120),
        "parent_division_id": "div_germany",
    })
    divisions.append({
        "id": "div_munich",
        "name": "Munich",
        "subtype": "locality",
        "admin_level": 8,
        "geometry_wkt": make_division_polygon_wkt(48.14, 11.58, radius_km=15),
        "parent_division_id": "div_bavaria",
    })
    divisions.append({
        "id": "div_france",
        "name": "France",
        "subtype": "country",
        "admin_level": 2,
        "geometry_wkt": make_division_polygon_wkt(46.6, 2.2, radius_km=400),
        "parent_division_id": None,
    })

    # Additional mixed
    divisions.append({
        "id": "div_south_holland",
        "name": "South Holland",
        "subtype": "region",
        "admin_level": 4,
        "geometry_wkt": make_division_polygon_wkt(52.0, 4.4, radius_km=40),
        "parent_division_id": "div_netherlands",
    })
    divisions.append({
        "id": "div_utrecht_province",
        "name": "Utrecht",
        "subtype": "region",
        "admin_level": 4,
        "geometry_wkt": make_division_polygon_wkt(52.08, 5.12, radius_km=30),
        "parent_division_id": "div_netherlands",
    })
    divisions.append({
        "id": "div_haarlem",
        "name": "Haarlem",
        "subtype": "locality",
        "admin_level": 8,
        "geometry_wkt": make_division_polygon_wkt(52.38, 4.63, radius_km=5),
        "parent_division_id": "div_north_holland",
    })

    assert len(divisions) == 10, f"Expected 10 divisions, got {len(divisions)}"
    return divisions


# ---------------------------------------------------------------------------
# Category taxonomy
# ---------------------------------------------------------------------------

def generate_categories() -> list[dict]:
    """Generate a category taxonomy (~200 categories) matching Overture's structure."""
    categories = [
        # Eat & Drink
        {"category": "restaurant", "description": "A dining establishment serving meals"},
        {"category": "cafe", "description": "A casual dining establishment serving coffee, tea, and light meals"},
        {"category": "coffee_shop", "description": "A shop that primarily serves coffee"},
        {"category": "coffee_roaster", "description": "A business that roasts coffee beans"},
        {"category": "tea_house", "description": "A shop specializing in tea"},
        {"category": "bakery", "description": "A shop that bakes and sells bread and pastries"},
        {"category": "bar", "description": "An establishment serving alcoholic drinks"},
        {"category": "pub", "description": "A public house serving beer and food"},
        {"category": "fast_food", "description": "A quick-service restaurant"},
        {"category": "pizza", "description": "A restaurant specializing in pizza"},
        {"category": "sushi", "description": "A restaurant specializing in sushi"},
        {"category": "ice_cream", "description": "A shop selling ice cream"},
        {"category": "juice_bar", "description": "A shop selling fresh juices and smoothies"},
        {"category": "food_truck", "description": "A mobile food vendor"},
        {"category": "deli", "description": "A delicatessen selling prepared foods"},
        {"category": "butcher", "description": "A shop selling meat products"},
        {"category": "fish_market", "description": "A market selling fresh fish"},
        {"category": "wine_bar", "description": "An establishment specializing in wine"},
        {"category": "brewery", "description": "A business that brews beer"},
        {"category": "steakhouse", "description": "A restaurant specializing in steak"},

        # Shopping
        {"category": "supermarket", "description": "A large store selling food and household items"},
        {"category": "convenience_store", "description": "A small store selling everyday items"},
        {"category": "bookstore", "description": "A store selling books"},
        {"category": "clothing_store", "description": "A store selling clothing"},
        {"category": "electronics_store", "description": "A store selling electronics"},
        {"category": "furniture_store", "description": "A store selling furniture"},
        {"category": "hardware_store", "description": "A store selling tools and hardware"},
        {"category": "pet_store", "description": "A store selling pet supplies"},
        {"category": "florist", "description": "A shop selling flowers and plants"},
        {"category": "gift_shop", "description": "A shop selling gifts and souvenirs"},
        {"category": "jewelry_store", "description": "A store selling jewelry"},
        {"category": "shoe_store", "description": "A store selling shoes"},
        {"category": "toy_store", "description": "A store selling toys"},
        {"category": "sports_store", "description": "A store selling sporting goods"},
        {"category": "department_store", "description": "A large store with multiple departments"},
        {"category": "shopping_mall", "description": "A large indoor shopping center"},
        {"category": "market", "description": "An open-air or indoor market"},
        {"category": "thrift_store", "description": "A store selling secondhand goods"},
        {"category": "antique_store", "description": "A store selling antiques"},
        {"category": "art_gallery", "description": "A gallery displaying and selling art"},

        # Health
        {"category": "hospital", "description": "A medical facility for inpatient care"},
        {"category": "pharmacy", "description": "A store dispensing medications"},
        {"category": "dentist", "description": "A dental care provider"},
        {"category": "doctor", "description": "A general medical practitioner"},
        {"category": "optician", "description": "A provider of eyeglasses and eye exams"},
        {"category": "veterinarian", "description": "An animal medical care provider"},
        {"category": "clinic", "description": "A medical facility for outpatient care"},
        {"category": "physiotherapist", "description": "A physical therapy provider"},
        {"category": "psychologist", "description": "A mental health care provider"},
        {"category": "nursing_home", "description": "A residential care facility for elderly"},

        # Financial
        {"category": "bank", "description": "A financial institution offering banking services"},
        {"category": "atm", "description": "An automated teller machine"},
        {"category": "insurance", "description": "An insurance provider"},
        {"category": "accountant", "description": "An accounting and tax service"},
        {"category": "financial_advisor", "description": "A financial planning service"},
        {"category": "currency_exchange", "description": "A foreign currency exchange service"},
        {"category": "credit_union", "description": "A member-owned financial cooperative"},

        # Education
        {"category": "school", "description": "An educational institution"},
        {"category": "university", "description": "A higher education institution"},
        {"category": "kindergarten", "description": "A preschool for young children"},
        {"category": "library", "description": "A public library"},
        {"category": "language_school", "description": "A school teaching languages"},
        {"category": "driving_school", "description": "A school teaching driving"},
        {"category": "music_school", "description": "A school teaching music"},
        {"category": "tutoring_center", "description": "A center providing tutoring services"},
        {"category": "college", "description": "A post-secondary educational institution"},
        {"category": "research_institute", "description": "A research and development institution"},

        # Transportation
        {"category": "gas_station", "description": "A fuel station for vehicles"},
        {"category": "parking", "description": "A parking facility"},
        {"category": "bus_station", "description": "A bus terminal or station"},
        {"category": "train_station", "description": "A railway station"},
        {"category": "airport", "description": "An airport facility"},
        {"category": "car_rental", "description": "A car rental service"},
        {"category": "bicycle_rental", "description": "A bicycle rental service"},
        {"category": "taxi_stand", "description": "A designated taxi pickup point"},
        {"category": "car_wash", "description": "A vehicle washing facility"},
        {"category": "car_repair", "description": "An automotive repair shop"},
        {"category": "ev_charging", "description": "An electric vehicle charging station"},
        {"category": "ferry_terminal", "description": "A terminal for ferry services"},

        # Accommodation
        {"category": "hotel", "description": "A hotel providing accommodation"},
        {"category": "hostel", "description": "A budget accommodation"},
        {"category": "motel", "description": "A roadside hotel"},
        {"category": "bed_and_breakfast", "description": "A small lodging with breakfast"},
        {"category": "campground", "description": "A camping site"},
        {"category": "resort", "description": "A vacation resort"},
        {"category": "apartment_rental", "description": "A short-term apartment rental"},

        # Entertainment & Recreation
        {"category": "cinema", "description": "A movie theater"},
        {"category": "theater", "description": "A performing arts theater"},
        {"category": "museum", "description": "A museum exhibiting collections"},
        {"category": "zoo", "description": "A zoological garden"},
        {"category": "aquarium", "description": "An aquatic animal exhibit"},
        {"category": "amusement_park", "description": "An amusement or theme park"},
        {"category": "nightclub", "description": "A nighttime entertainment venue"},
        {"category": "casino", "description": "A gambling establishment"},
        {"category": "bowling_alley", "description": "A bowling facility"},
        {"category": "escape_room", "description": "An escape room entertainment venue"},
        {"category": "concert_hall", "description": "A venue for concerts and performances"},

        # Sports & Fitness
        {"category": "gym", "description": "A fitness center or gym"},
        {"category": "swimming_pool", "description": "A public swimming pool"},
        {"category": "tennis_court", "description": "A tennis facility"},
        {"category": "golf_course", "description": "A golf course"},
        {"category": "yoga_studio", "description": "A yoga and meditation studio"},
        {"category": "martial_arts", "description": "A martial arts training center"},
        {"category": "stadium", "description": "A sports stadium"},
        {"category": "sports_field", "description": "An outdoor sports field"},
        {"category": "climbing_gym", "description": "An indoor climbing facility"},
        {"category": "skating_rink", "description": "An ice or roller skating rink"},

        # Services
        {"category": "post_office", "description": "A postal service office"},
        {"category": "courier", "description": "A courier and delivery service"},
        {"category": "laundry", "description": "A laundry or dry cleaning service"},
        {"category": "barber", "description": "A barbershop"},
        {"category": "hair_salon", "description": "A hair styling salon"},
        {"category": "beauty_salon", "description": "A beauty and cosmetics salon"},
        {"category": "spa", "description": "A spa and wellness center"},
        {"category": "tailor", "description": "A clothing alteration and tailoring service"},
        {"category": "locksmith", "description": "A lock and key service"},
        {"category": "plumber", "description": "A plumbing service"},
        {"category": "electrician", "description": "An electrical service"},
        {"category": "moving_company", "description": "A moving and relocation service"},
        {"category": "real_estate", "description": "A real estate agency"},
        {"category": "lawyer", "description": "A legal services firm"},
        {"category": "notary", "description": "A notary public"},
        {"category": "translator", "description": "A translation service"},
        {"category": "print_shop", "description": "A printing service"},
        {"category": "photographer", "description": "A photography service"},
        {"category": "funeral_home", "description": "A funeral and mortuary service"},
        {"category": "travel_agency", "description": "A travel booking agency"},

        # Government & Public
        {"category": "police_station", "description": "A police station"},
        {"category": "fire_station", "description": "A fire station"},
        {"category": "city_hall", "description": "A municipal government building"},
        {"category": "embassy", "description": "A foreign embassy or consulate"},
        {"category": "courthouse", "description": "A court of law"},
        {"category": "community_center", "description": "A community gathering place"},
        {"category": "recycling_center", "description": "A waste recycling facility"},

        # Religious
        {"category": "church", "description": "A Christian church"},
        {"category": "mosque", "description": "An Islamic mosque"},
        {"category": "synagogue", "description": "A Jewish synagogue"},
        {"category": "temple", "description": "A religious temple"},

        # Nature & Parks
        {"category": "park", "description": "A public park"},
        {"category": "garden", "description": "A public or botanical garden"},
        {"category": "nature_reserve", "description": "A protected natural area"},
        {"category": "beach", "description": "A beach or waterfront area"},
        {"category": "playground", "description": "A children's playground"},

        # Technology
        {"category": "coworking_space", "description": "A shared workspace for professionals"},
        {"category": "data_center", "description": "A data storage and processing facility"},
        {"category": "tech_startup", "description": "A technology startup company"},
        {"category": "computer_repair", "description": "A computer repair service"},
        {"category": "internet_cafe", "description": "A cafe with internet access"},

        # Industrial
        {"category": "warehouse", "description": "A storage warehouse"},
        {"category": "factory", "description": "A manufacturing facility"},
        {"category": "construction_site", "description": "An active construction site"},
        {"category": "power_plant", "description": "An electrical power generation facility"},
        {"category": "water_treatment", "description": "A water treatment facility"},

        # Other / Miscellaneous
        {"category": "dog_park", "description": "A park designated for dogs"},
        {"category": "car_dealership", "description": "An automobile dealership"},
        {"category": "bike_shop", "description": "A bicycle sales and repair shop"},
        {"category": "pawn_shop", "description": "A pawn and loan shop"},
        {"category": "vape_shop", "description": "A vaporizer and e-cigarette shop"},
        {"category": "tattoo_parlor", "description": "A tattoo and body art studio"},
        {"category": "event_venue", "description": "A venue for events and conferences"},
        {"category": "wedding_venue", "description": "A venue for wedding ceremonies"},
        {"category": "storage_facility", "description": "A self-storage facility"},
        {"category": "cemetery", "description": "A burial ground"},
    ]

    assert len(categories) >= 150, f"Expected >=150 categories, got {len(categories)}"
    return categories


# ---------------------------------------------------------------------------
# Parquet writing
# ---------------------------------------------------------------------------

def write_places_parquet(places: list[dict], output_path: str):
    """Write places to a parquet file matching Overture schema."""
    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")

    # Create table with Overture-like schema
    # Note: "primary" is a reserved keyword in DuckDB, must be quoted
    conn.execute("""
        CREATE TABLE places (
            id VARCHAR,
            names STRUCT("primary" VARCHAR),
            categories STRUCT("primary" VARCHAR, alternate VARCHAR[]),
            geometry GEOMETRY,
            bbox STRUCT(xmin DOUBLE, xmax DOUBLE, ymin DOUBLE, ymax DOUBLE),
            confidence DOUBLE,
            websites VARCHAR[],
            phones VARCHAR[],
            addresses STRUCT(freeform VARCHAR),
            sources STRUCT(property VARCHAR, dataset VARCHAR, record_id VARCHAR)[]
        )
    """)

    for p in places:
        # Create point geometry
        conn.execute("""
            INSERT INTO places VALUES (
                ?, -- id
                ROW(?), -- names (struct with "primary")
                ROW(?, ?::VARCHAR[]), -- categories (struct with "primary", alternate)
                ST_Point(?, ?), -- geometry (lng, lat)
                ROW(?, ?, ?, ?), -- bbox (xmin, xmax, ymin, ymax)
                ?, -- confidence
                ?::VARCHAR[], -- websites
                ?::VARCHAR[], -- phones
                ROW(NULL), -- addresses
                []::STRUCT(property VARCHAR, dataset VARCHAR, record_id VARCHAR)[] -- sources
            )
        """, [
            p["id"],
            p["name"],
            p["category"],
            p["alt_categories"],
            p["lng"], p["lat"],  # ST_Point takes (lng, lat)
            p["lng"] - 0.0001, p["lng"] + 0.0001,  # bbox
            p["lat"] - 0.0001, p["lat"] + 0.0001,
            p["confidence"],
            p["websites"],
            p["phones"],
        ])

    conn.execute(f"COPY places TO '{output_path}' (FORMAT PARQUET)")
    count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
    conn.close()
    return count


def write_buildings_parquet(buildings: list[dict], output_path: str):
    """Write buildings to a parquet file matching Overture schema."""
    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")

    conn.execute("""
        CREATE TABLE buildings (
            id VARCHAR,
            names STRUCT("primary" VARCHAR),
            class VARCHAR,
            height DOUBLE,
            num_floors INTEGER,
            geometry GEOMETRY,
            bbox STRUCT(xmin DOUBLE, xmax DOUBLE, ymin DOUBLE, ymax DOUBLE),
            sources STRUCT(property VARCHAR, dataset VARCHAR, record_id VARCHAR)[]
        )
    """)

    for b in buildings:
        conn.execute("""
            INSERT INTO buildings VALUES (
                ?, -- id
                ROW(?), -- names
                ?, -- class
                ?, -- height
                ?, -- num_floors
                ST_GeomFromText(?), -- geometry
                ROW(?, ?, ?, ?), -- bbox (xmin, xmax, ymin, ymax)
                []::STRUCT(property VARCHAR, dataset VARCHAR, record_id VARCHAR)[] -- sources
            )
        """, [
            b["id"],
            b["name"],
            b["class"],
            b["height"],
            b["num_floors"],
            b["geometry_wkt"],
            b["lng"] - 0.001, b["lng"] + 0.001,  # bbox (larger for polygons)
            b["lat"] - 0.001, b["lat"] + 0.001,
        ])

    conn.execute(f"COPY buildings TO '{output_path}' (FORMAT PARQUET)")
    count = conn.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
    conn.close()
    return count


def write_divisions_parquet(divisions: list[dict], output_path: str):
    """Write divisions to a parquet file matching Overture schema."""
    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")

    conn.execute("""
        CREATE TABLE divisions (
            id VARCHAR,
            names STRUCT("primary" VARCHAR),
            subtype VARCHAR,
            admin_level INTEGER,
            geometry GEOMETRY,
            bbox STRUCT(xmin DOUBLE, xmax DOUBLE, ymin DOUBLE, ymax DOUBLE),
            parent_division_id VARCHAR
        )
    """)

    for d in divisions:
        # Compute bbox from geometry
        conn.execute("""
            INSERT INTO divisions
            SELECT
                ? AS id,
                ROW(?) AS names,
                ? AS subtype,
                ? AS admin_level,
                geom AS geometry,
                ROW(ST_XMin(geom), ST_XMax(geom), ST_YMin(geom), ST_YMax(geom)) AS bbox,
                ? AS parent_division_id
            FROM (SELECT ST_GeomFromText(?) AS geom)
        """, [
            d["id"],
            d["name"],
            d["subtype"],
            d["admin_level"],
            d["parent_division_id"],
            d["geometry_wkt"],
        ])

    conn.execute(f"COPY divisions TO '{output_path}' (FORMAT PARQUET)")
    count = conn.execute("SELECT COUNT(*) FROM divisions").fetchone()[0]
    conn.close()
    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Generating test fixtures...")
    print(f"Output directory: {FIXTURES_DIR}")
    print()

    # Generate places
    places = generate_places()
    places_path = os.path.join(FIXTURES_DIR, "sample_places.parquet")
    count = write_places_parquet(places, places_path)
    print(f"  sample_places.parquet: {count} records")

    # Generate buildings
    buildings = generate_buildings()
    buildings_path = os.path.join(FIXTURES_DIR, "sample_buildings.parquet")
    count = write_buildings_parquet(buildings, buildings_path)
    print(f"  sample_buildings.parquet: {count} records")

    # Generate divisions
    divisions = generate_divisions()
    divisions_path = os.path.join(FIXTURES_DIR, "sample_divisions.parquet")
    count = write_divisions_parquet(divisions, divisions_path)
    print(f"  sample_divisions.parquet: {count} records")

    # Generate categories
    categories = generate_categories()
    categories_path = os.path.join(FIXTURES_DIR, "categories.json")
    with open(categories_path, "w") as f:
        json.dump(categories, f, indent=2)
    print(f"  categories.json: {len(categories)} categories")

    print()
    print("Done! All fixtures generated successfully.")

    # Verification: read back and validate
    print()
    print("Verifying fixtures...")
    verify_conn = duckdb.connect()
    verify_conn.execute("INSTALL spatial; LOAD spatial;")

    # Verify places
    result = verify_conn.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN categories.primary = 'coffee_shop' THEN 1 ELSE 0 END) as coffee_shops,
               SUM(CASE WHEN names.primary IS NULL THEN 1 ELSE 0 END) as null_names
        FROM read_parquet('{places_path}')
    """).fetchone()
    print(f"  Places: {result[0]} total, {result[1]} coffee shops, {result[2]} null names")

    # Verify buildings
    result = verify_conn.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN class IS NULL THEN 1 ELSE 0 END) as null_class
        FROM read_parquet('{buildings_path}')
    """).fetchone()
    print(f"  Buildings: {result[0]} total, {result[1]} null class")

    # Verify divisions
    result = verify_conn.execute(f"""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN ST_Contains(geometry, ST_Point(4.9041, 52.3676)) THEN 1 ELSE 0 END) as contains_center
        FROM read_parquet('{divisions_path}')
    """).fetchone()
    print(f"  Divisions: {result[0]} total, {result[1]} contain Amsterdam center")

    # Verify coffee shop distances
    result = verify_conn.execute(f"""
        SELECT names.primary AS name,
               CAST(ST_Distance_Spheroid(geometry, ST_Point(4.9041, 52.3676)) AS INTEGER) AS distance_m
        FROM read_parquet('{places_path}')
        WHERE categories.primary = 'coffee_shop'
        ORDER BY distance_m ASC
    """).fetchall()
    print(f"  Coffee shop distances: {[f'{r[0]}: {r[1]}m' for r in result]}")

    # Check for large geometry building
    result = verify_conn.execute(f"""
        SELECT id, LENGTH(ST_AsText(geometry)) as wkt_length
        FROM read_parquet('{buildings_path}')
        ORDER BY wkt_length DESC
        LIMIT 1
    """).fetchone()
    print(f"  Largest building geometry: {result[0]} ({result[1]} chars WKT)")

    verify_conn.close()
    print()
    print("Verification complete!")


if __name__ == "__main__":
    main()
