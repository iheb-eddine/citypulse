"""CityPulse configuration — constants, city data, and city-related helpers."""

from typing import Optional

SEVERITY_COLORS = {"low": "green", "medium": "orange", "high": "orange", "critical": "red"}
SEVERITY_WEIGHTS = {"low": 1, "medium": 2, "high": 3, "critical": 5}
ACCESSIBILITY_WEIGHTS = {"pothole": 3, "streetlight": 2, "flooding": 2, "sign": 1.5, "graffiti": 1, "dumping": 1.5, "other": 1}

_SEVERITY_BASE_DAYS = {"low": 3, "medium": 5, "high": 7, "critical": 2}
_CATEGORY_EXTRA_DAYS = {"pothole": 2, "streetlight": 1}

VALID_CATEGORIES = {"pothole", "streetlight", "graffiti", "flooding", "dumping", "sign", "other", "unclassified"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_STATUSES = {"open", "in_progress", "resolved"}
SEVERITY_ESCALATION = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}

MAX_FILE_SIZE = 10_485_760

CITIES = {
    "stuttgart": {
        "name": "Stuttgart",
        "lat": 48.7758,
        "lng": 9.1829,
        "zoom": 13,
        "neighborhoods": [
            (48.781, 48.788, 9.177, 9.186, "Hauptbahnhof"),
            (48.800, 48.809, 9.209, 9.219, "Bad Cannstatt"),
            (48.767, 48.775, 9.164, 9.176, "Stuttgart-West"),
            (48.757, 48.767, 9.164, 9.176, "Stuttgart-Süd"),
            (48.786, 48.795, 9.188, 9.202, "Stuttgart-Nord"),
            (48.764, 48.773, 9.204, 9.216, "Stuttgart-Ost"),
            (48.750, 48.759, 9.153, 9.167, "Vaihingen"),
            (48.741, 48.750, 9.170, 9.182, "Möhringen"),
            (48.774, 48.782, 9.150, 9.162, "Botnang"),
            (48.806, 48.815, 9.225, 9.236, "Münster"),
            (48.730, 48.740, 9.145, 9.156, "Büsnau"),
            (48.791, 48.800, 9.135, 9.148, "Feuerbach"),
            (48.756, 48.764, 9.184, 9.196, "Degerloch"),
            (48.746, 48.755, 9.200, 9.212, "Sillenbuch"),
            (48.781, 48.790, 9.155, 9.167, "Zuffenhausen"),
            (48.766, 48.775, 9.215, 9.226, "Wangen"),
            (48.736, 48.745, 9.180, 9.192, "Plieningen"),
        ],
        "bbox": (48.70, 48.85, 9.10, 9.30),
        "news_keywords": {"stuttgart", "cannstatt", "vaihingen", "degerloch", "feuerbach",
                          "zuffenhausen", "möhringen", "botnang", "plieningen", "sillenbuch",
                          "hauptbahnhof", "neckar", "killesberg", "schlossplatz", "königstraße",
                          "s-bahn", "ssb", "vvs"},
        "rss_feeds": [
            "https://www.swr.de/~rss/swraktuell-bw-100.xml",
            "https://www.stuttgarter-zeitung.de/rss/topthemen.rss.feed",
        ],
    },
    "berlin": {
        "name": "Berlin",
        "lat": 52.5200,
        "lng": 13.4050,
        "zoom": 12,
        "neighborhoods": [
            (52.516, 52.523, 13.370, 13.385, "Mitte"),
            (52.497, 52.505, 13.415, 13.435, "Kreuzberg"),
            (52.505, 52.515, 13.320, 13.340, "Charlottenburg"),
            (52.530, 52.540, 13.395, 13.415, "Prenzlauer Berg"),
            (52.475, 52.485, 13.430, 13.450, "Neukölln"),
            (52.510, 52.520, 13.440, 13.460, "Friedrichshain"),
            (52.485, 52.495, 13.340, 13.360, "Schöneberg"),
            (52.540, 52.550, 13.350, 13.370, "Wedding"),
        ],
        "bbox": (52.40, 52.60, 13.25, 13.55),
        "news_keywords": {"berlin", "mitte", "kreuzberg", "charlottenburg", "neukölln",
                          "friedrichshain", "prenzlauer", "schöneberg", "wedding",
                          "alexanderplatz", "brandenburger", "bvg", "s-bahn"},
        "rss_feeds": [
            "https://www.rbb24.de/aktuell/index.xml/feed=rss.xml",
        ],
    },
    "munich": {
        "name": "Munich",
        "lat": 48.1351,
        "lng": 11.5820,
        "zoom": 13,
        "neighborhoods": [
            (48.135, 48.142, 11.570, 11.585, "Altstadt"),
            (48.148, 48.155, 11.555, 11.570, "Schwabing"),
            (48.125, 48.133, 11.545, 11.560, "Sendling"),
            (48.130, 48.138, 11.600, 11.615, "Haidhausen"),
            (48.155, 48.163, 11.535, 11.550, "Milbertshofen"),
            (48.118, 48.126, 11.575, 11.590, "Giesing"),
            (48.140, 48.148, 11.530, 11.545, "Nymphenburg"),
            (48.108, 48.116, 11.555, 11.570, "Thalkirchen"),
        ],
        "bbox": (48.06, 48.22, 11.43, 11.72),
        "news_keywords": {"münchen", "munich", "schwabing", "sendling", "haidhausen",
                          "nymphenburg", "marienplatz", "oktoberfest", "mvv", "mvg"},
        "rss_feeds": [
            "https://www.br.de/nachrichten/bayern/index~rss.xml",
        ],
    },
}

DEFAULT_CITY = "stuttgart"


def get_city(city_key: Optional[str] = None) -> tuple[str, dict]:
    """Return (city_key, city_config). Falls back to DEFAULT_CITY."""
    key = city_key if city_key in CITIES else DEFAULT_CITY
    return key, CITIES[key]


def nearest_city(lat: float, lng: float) -> str:
    """Return the city key nearest to the given coordinates."""
    best, best_dist = DEFAULT_CITY, float("inf")
    for key, cfg in CITIES.items():
        d = (lat - cfg["lat"]) ** 2 + (lng - cfg["lng"]) ** 2
        if d < best_dist:
            best, best_dist = key, d
    return best


def neighborhood_for_coords(lat: float, lng: float, city_key: Optional[str] = None) -> str:
    key, cfg = get_city(city_key)
    for lat_min, lat_max, lng_min, lng_max, name in cfg["neighborhoods"]:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return name
    bbox = cfg.get("bbox")
    if bbox:
        lat_min, lat_max, lng_min, lng_max = bbox
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return cfg["name"]
    return "Unknown area"
