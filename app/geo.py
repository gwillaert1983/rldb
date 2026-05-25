"""
Belgian city geodata for radius-based search.
Each entry: (province_slug, city_slug, lat, lon)
Covers all cities that appear on redlights.be/regio/ + major Belgian cities.
"""
from math import atan2, cos, radians, sin, sqrt

REGIO_BASE = "https://www.redlights.be/regio"

# (province_slug, city_slug, lat, lon)
CITY_DATA: list[tuple[str, str, float, float]] = [
    # Antwerpen
    ("antwerpen", "antwerpen",      51.2194,  4.4025),
    ("antwerpen", "mechelen",       51.0259,  4.4777),
    ("antwerpen", "turnhout",       51.3228,  4.9440),
    ("antwerpen", "lier",           51.1309,  4.5695),
    ("antwerpen", "geel",           51.1607,  4.9886),
    ("antwerpen", "herentals",      51.1770,  4.8358),
    ("antwerpen", "mol",            51.1904,  5.1127),
    ("antwerpen", "boom",           51.0893,  4.3707),
    ("antwerpen", "brasschaat",     51.2978,  4.4956),
    ("antwerpen", "berchem",        51.1969,  4.4241),
    ("antwerpen", "borgerhout",     51.2100,  4.4442),
    ("antwerpen", "deurne",         51.2228,  4.4688),
    ("antwerpen", "ekeren",         51.2838,  4.4082),
    ("antwerpen", "merksem",        51.2493,  4.4314),
    ("antwerpen", "wilrijk",        51.1693,  4.3901),
    ("antwerpen", "hoboken",        51.1764,  4.3534),
    ("antwerpen", "kontich",        51.1340,  4.4455),
    ("antwerpen", "aartselaar",     51.1108,  4.3884),
    ("antwerpen", "edegem",         51.1570,  4.4372),
    ("antwerpen", "hove",           51.1439,  4.4589),
    ("antwerpen", "boechout",       51.1609,  4.5068),
    ("antwerpen", "mortsel",        51.1651,  4.4534),
    ("antwerpen", "borsbeek",       51.1935,  4.4899),
    ("antwerpen", "wijnegem",       51.2209,  4.5185),
    ("antwerpen", "schoten",        51.2609,  4.4945),
    ("antwerpen", "kapellen",       51.3200,  4.4282),
    ("antwerpen", "brecht",         51.3516,  4.6381),
    ("antwerpen", "zandhoven",      51.2603,  4.6595),
    ("antwerpen", "malle",          51.3008,  4.6928),
    ("antwerpen", "beerse",         51.3219,  4.8607),
    ("antwerpen", "olen",           51.1599,  4.8664),
    ("antwerpen", "westerlo",       51.0876,  4.9156),
    ("antwerpen", "nijlen",         51.1639,  4.6616),
    ("antwerpen", "berlaar",        51.1186,  4.6500),
    ("antwerpen", "bonheiden",      51.0263,  4.5340),
    ("antwerpen", "putte",          51.0503,  4.6466),
    ("antwerpen", "bornem",         51.0981,  4.2400),
    ("antwerpen", "sint-amands",    51.0644,  4.2033),
    ("antwerpen", "puurs",          51.0723,  4.2851),
    ("antwerpen", "niel",           51.1085,  4.3296),
    ("antwerpen", "hemiksem",       51.1470,  4.3460),

    # Brussel
    ("brussel", "brussel",             50.8503,  4.3517),
    ("brussel", "anderlecht",          50.8344,  4.3076),
    ("brussel", "elsene",              50.8240,  4.3630),
    ("brussel", "schaarbeek",          50.8657,  4.3796),
    ("brussel", "sint-gillis",         50.8178,  4.3414),
    ("brussel", "molenbeek",           50.8540,  4.3235),
    ("brussel", "sint-jans-molenbeek", 50.8540,  4.3235),
    ("brussel", "etterbeek",           50.8333,  4.3912),
    ("brussel", "jette",               50.8793,  4.3226),
    ("brussel", "ganshoren",           50.8844,  4.3127),
    ("brussel", "ukkel",               50.8011,  4.3591),
    ("brussel", "vorst",               50.8118,  4.3323),
    ("brussel", "evere",               50.8742,  4.4022),
    ("brussel", "auderghem",           50.8036,  4.4306),
    ("brussel", "oudergem",            50.8036,  4.4306),
    ("brussel", "watermaal-bosvoorde", 50.8009,  4.4063),
    ("brussel", "koekelberg",          50.8669,  4.3273),
    ("brussel", "sint-pieters-woluwe", 50.8408,  4.4339),
    ("brussel", "sint-lambrechts-woluwe", 50.8534, 4.4282),

    # Oost-Vlaanderen
    ("oost-vlaanderen", "gent",          51.0543,  3.7174),
    ("oost-vlaanderen", "aalst",         50.9360,  4.0369),
    ("oost-vlaanderen", "sint-niklaas",  51.1603,  4.1432),
    ("oost-vlaanderen", "dendermonde",   51.0231,  4.1015),
    ("oost-vlaanderen", "ronse",         50.7457,  3.5985),
    ("oost-vlaanderen", "oudenaarde",    50.8476,  3.6031),
    ("oost-vlaanderen", "lokeren",       51.1022,  3.9928),
    ("oost-vlaanderen", "eeklo",         51.1869,  3.5723),
    ("oost-vlaanderen", "ninove",        50.8464,  4.0231),
    ("oost-vlaanderen", "zottegem",      50.8722,  3.8088),
    ("oost-vlaanderen", "geraardsbergen",50.7727,  3.8810),
    ("oost-vlaanderen", "wetteren",      51.0014,  3.8806),
    ("oost-vlaanderen", "merelbeke",     51.0079,  3.7527),
    ("oost-vlaanderen", "melle",         51.0005,  3.8183),
    ("oost-vlaanderen", "destelbergen",  51.0621,  3.7980),
    ("oost-vlaanderen", "beveren-waas",  51.2147,  4.2564),
    ("oost-vlaanderen", "temse",         51.1283,  4.2112),
    ("oost-vlaanderen", "kruibeke",      51.1783,  4.3109),
    ("oost-vlaanderen", "hamme",         51.0987,  4.1350),
    ("oost-vlaanderen", "buggenhout",    51.0226,  4.1944),
    ("oost-vlaanderen", "lebbeke",       51.0047,  4.1343),
    ("oost-vlaanderen", "berlare",       51.0267,  3.9564),
    ("oost-vlaanderen", "laarne",        51.0329,  3.8399),
    ("oost-vlaanderen", "wichelen",      51.0061,  3.9793),
    ("oost-vlaanderen", "zele",          51.0663,  4.0432),

    # West-Vlaanderen
    ("west-vlaanderen", "brugge",       51.2093,  3.2247),
    ("west-vlaanderen", "kortrijk",     50.8286,  3.2648),
    ("west-vlaanderen", "roeselare",    50.9460,  3.1236),
    ("west-vlaanderen", "ieper",        50.8520,  2.8797),
    ("west-vlaanderen", "oostende",     51.2308,  2.9168),
    ("west-vlaanderen", "knokke-heist", 51.3624,  3.2978),
    ("west-vlaanderen", "blankenberge", 51.3098,  3.1346),
    ("west-vlaanderen", "de-haan",      51.2724,  3.0388),
    ("west-vlaanderen", "tielt",        50.9941,  3.3282),
    ("west-vlaanderen", "diksmuide",    51.0343,  2.8655),
    ("west-vlaanderen", "veurne",       51.0705,  2.6640),
    ("west-vlaanderen", "menen",        50.8007,  3.1230),
    ("west-vlaanderen", "waregem",      50.8817,  3.4240),
    ("west-vlaanderen", "deinze",       50.9817,  3.5311),
    ("west-vlaanderen", "torhout",      51.0693,  3.1016),
    ("west-vlaanderen", "poperinge",    50.8554,  2.7269),
    ("west-vlaanderen", "izegem",       50.9163,  3.2140),
    ("west-vlaanderen", "wevelgem",     50.8099,  3.1780),
    ("west-vlaanderen", "harelbeke",    50.8572,  3.3118),
    ("west-vlaanderen", "zwevegem",     50.8072,  3.3395),
    ("west-vlaanderen", "lichtervelde", 51.0258,  3.1477),
    ("west-vlaanderen", "pittem",       50.9968,  3.2508),
    ("west-vlaanderen", "ardooie",      51.0006,  3.2031),
    ("west-vlaanderen", "wingene",      51.0614,  3.2846),

    # Vlaams-Brabant
    ("vlaams-brabant", "leuven",     50.8798,  4.7005),
    ("vlaams-brabant", "halle",      50.7345,  4.2336),
    ("vlaams-brabant", "aarschot",   50.9852,  4.8302),
    ("vlaams-brabant", "diest",      50.9934,  5.0570),
    ("vlaams-brabant", "tienen",     50.8083,  4.9406),
    ("vlaams-brabant", "vilvoorde",  50.9280,  4.4256),
    ("vlaams-brabant", "asse",       50.9024,  4.2078),
    ("vlaams-brabant", "zaventem",   50.8841,  4.4728),
    ("vlaams-brabant", "overijse",   50.7742,  4.5320),
    ("vlaams-brabant", "beersel",    50.7615,  4.3165),
    ("vlaams-brabant", "dilbeek",    50.8569,  4.2739),
    ("vlaams-brabant", "grimbergen", 50.9354,  4.3638),
    ("vlaams-brabant", "machelen",   50.9150,  4.4349),
    ("vlaams-brabant", "haacht",     50.9749,  4.6336),
    ("vlaams-brabant", "rotselaar",  50.9562,  4.7150),
    ("vlaams-brabant", "boutersem",  50.8477,  4.8382),
    ("vlaams-brabant", "glabbeek",   50.8763,  4.9620),
    ("vlaams-brabant", "lubbeek",    50.8820,  4.8191),
    ("vlaams-brabant", "holsbeek",   50.9300,  4.7730),
    ("vlaams-brabant", "begijnendijk", 51.0247, 4.7954),

    # Limburg
    ("limburg", "hasselt",        50.9307,  5.3378),
    ("limburg", "genk",           50.9651,  5.4996),
    ("limburg", "sint-truiden",   50.8188,  5.1892),
    ("limburg", "tongeren",       50.7800,  5.4658),
    ("limburg", "maaseik",        51.0993,  5.7815),
    ("limburg", "bree",           51.1385,  5.5943),
    ("limburg", "maasmechelen",   50.9618,  5.6906),
    ("limburg", "beringen",       51.0504,  5.2267),
    ("limburg", "leopoldsburg",   51.1164,  5.2645),
    ("limburg", "heusden-zolder", 51.0265,  5.2886),
    ("limburg", "lummen",         50.9812,  5.2040),
    ("limburg", "halen",          50.9479,  5.1115),
    ("limburg", "diest",          50.9934,  5.0570),
    ("limburg", "herk-de-stad",   50.9409,  5.1643),
    ("limburg", "bilzen",         50.8733,  5.5180),
    ("limburg", "lanaken",        50.8747,  5.6482),
    ("limburg", "riemst",         50.8145,  5.5985),
    ("limburg", "zutendaal",      50.9224,  5.5815),
    ("limburg", "as",             50.9855,  5.5872),
    ("limburg", "opglabbeek",     51.0491,  5.5900),
    ("limburg", "dilsen",         51.0215,  5.7230),
    ("limburg", "peer",           51.1283,  5.4585),
    ("limburg", "neerpelt",       51.2273,  5.4354),
    ("limburg", "hamont-achel",   51.2573,  5.5373),
    ("limburg", "overpelt",       51.2063,  5.4189),

    # Henegouwen / Hainaut
    ("henegouwen", "bergen",       50.4542,  3.9523),
    ("henegouwen", "charleroi",    50.4108,  4.4444),
    ("henegouwen", "la-louviere",  50.4783,  4.1895),
    ("henegouwen", "moeskroen",    50.7441,  3.2224),
    ("henegouwen", "tournai",      50.6050,  3.3885),
    ("henegouwen", "binche",       50.4083,  4.1633),
    ("henegouwen", "soignies",     50.5773,  4.0700),
    ("henegouwen", "braine-le-comte", 50.6072, 4.1350),
    ("henegouwen", "lessines",     50.7148,  3.8348),
    ("henegouwen", "ath",          50.6319,  3.7775),
    ("henegouwen", "enghien",      50.6962,  4.0329),
    ("henegouwen", "courcelles",   50.4622,  4.3762),
    ("henegouwen", "chatelet",     50.4054,  4.5234),
    ("henegouwen", "fleurus",      50.4815,  4.5434),
    ("henegouwen", "gerpinnes",    50.3312,  4.5252),
    ("henegouwen", "thuin",        50.3401,  4.2833),

    # Namen / Namur
    ("namen", "namen",     50.4667,  4.8667),
    ("namen", "andenne",   50.4833,  5.1000),
    ("namen", "gembloux",  50.5617,  4.6991),
    ("namen", "ciney",     50.2999,  5.1013),
    ("namen", "philippeville", 50.1979, 4.5500),
    ("namen", "dinant",    50.2600,  4.9133),
    ("namen", "beauraing", 50.1129,  4.9576),
    ("namen", "rochefort", 50.1604,  5.2250),

    # Luik / Liège
    ("luik", "luik",       50.6326,  5.5797),
    ("luik", "seraing",    50.5986,  5.5057),
    ("luik", "herstal",    50.6716,  5.6376),
    ("luik", "verviers",   50.5904,  5.8606),
    ("luik", "spa",        50.4850,  5.8483),
    ("luik", "vise",       50.7366,  5.7012),
    ("luik", "ans",        50.6655,  5.5219),
    ("luik", "grace-hollogne", 50.6254, 5.4931),
    ("luik", "fleron",     50.6108,  5.6903),
    ("luik", "beyne-heusay", 50.6089, 5.6736),
    ("luik", "soumagne",   50.6050,  5.7437),
    ("luik", "aywaille",   50.4730,  5.6672),
    ("luik", "huy",        50.5193,  5.2391),
    ("luik", "wanze",      50.5163,  5.2047),
    ("luik", "amay",       50.5483,  5.3172),
    ("luik", "waremme",    50.6961,  5.2560),
    ("luik", "hannut",     50.6732,  5.0830),
    ("luik", "libramont",  50.0000,  5.3800),

    # Luxemburg (belgie)
    ("luxemburg", "arlon",     49.6847,  5.8157),
    ("luxemburg", "bastogne",  50.0008,  5.7171),
    ("luxemburg", "marche-en-famenne", 50.2287, 5.3441),
    ("luxemburg", "neufchateau", 49.8484, 5.4265),
    ("luxemburg", "virton",    49.5671,  5.5318),
    ("luxemburg", "libramont", 49.9167,  5.3833),
    ("luxemburg", "florenville", 49.7000, 5.3167),
    ("luxemburg", "bouillon",  49.7960,  5.0649),
    ("luxemburg", "vielsalm",  50.2857,  5.9098),
    ("luxemburg", "durbuy",    50.3576,  5.4570),

    # Waals-Brabant
    ("waals-brabant", "waver",       50.7177,  4.6022),
    ("waals-brabant", "eigenbrakel", 50.6800,  4.3717),
    ("waals-brabant", "nijvel",      50.5994,  4.3316),
    ("waals-brabant", "jodoigne",    50.7218,  4.8692),
    ("waals-brabant", "geldenaken",  50.6012,  4.7630),
    ("waals-brabant", "tubeke",      50.6924,  4.2044),
]

# Build lookup dict: city_slug → (province_slug, lat, lon)
_CITY_INDEX: dict[str, tuple[str, float, float]] = {
    slug: (prov, lat, lon)
    for prov, slug, lat, lon in CITY_DATA
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def get_city_coords(city_slug: str) -> tuple[float, float] | None:
    entry = _CITY_INDEX.get(city_slug)
    if entry:
        return entry[1], entry[2]
    return None


def cities_within_radius(center_slug: str, radius_km: float) -> list[str]:
    """
    Return redlights.be regio URLs for all cities within radius_km of center_slug.
    Always includes the center city itself.
    """
    center = _CITY_INDEX.get(center_slug)
    if center is None:
        return []
    _, c_lat, c_lon = center
    result: list[str] = []
    seen: set[str] = set()
    for prov, slug, lat, lon in CITY_DATA:
        key = f"{prov}/{slug}"
        if key in seen:
            continue
        if haversine(c_lat, c_lon, lat, lon) <= radius_km:
            seen.add(key)
            result.append(f"{REGIO_BASE}/{prov}/{slug}.html")
    return result


def all_city_options() -> list[dict]:
    """Return all cities as [{slug, name, province_slug, province_name}] for UI dropdowns."""
    prov_names = {
        "antwerpen":       "Antwerpen",
        "brussel":         "Brussel",
        "henegouwen":      "Henegouwen",
        "limburg":         "Limburg",
        "luik":            "Luik",
        "luxemburg":       "Luxemburg",
        "namen":           "Namen",
        "oost-vlaanderen": "Oost-Vlaanderen",
        "vlaams-brabant":  "Vlaams-Brabant",
        "waals-brabant":   "Waals-Brabant",
        "west-vlaanderen": "West-Vlaanderen",
    }
    seen: set[str] = set()
    result = []
    for prov, slug, _, _ in CITY_DATA:
        if slug in seen:
            continue
        seen.add(slug)
        result.append({
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "province_slug": prov,
            "province_name": prov_names.get(prov, prov),
        })
    return sorted(result, key=lambda c: (c["province_name"], c["name"]))
