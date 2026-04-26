import json
import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import exists

from app.dependencies import get_db, require_login
from app.models import Advertisement, Profile, ScrapeRun
from app.templates_config import templates

# Comprehensive Belgian municipality → province mapping
# Values match Dutch spellings used on redlights.be
PROVINCE_CITIES: dict[str, list[str]] = {
    "Antwerpen": [
        "Aartselaar", "Antwerpen", "Balen", "Beerse", "Berlaar", "Boechout",
        "Bonheiden", "Boom", "Bornem", "Borsbeek", "Brasschaat", "Brecht",
        "Dessel", "Duffel", "Edegem", "Essen", "Geel", "Grobbendonk",
        "Heist-op-den-Berg", "Herentals", "Herenthout", "Herselt",
        "Hoogstraten", "Hulshout", "Kalmthout", "Kapellen", "Kasterlee",
        "Kontich", "Laakdal", "Lier", "Lille", "Lint", "Malle", "Mechelen",
        "Meerhout", "Merksplas", "Mol", "Mortsel", "Niel", "Nijlen", "Olen",
        "Oud-Turnhout", "Putte", "Puurs-Sint-Amands", "Ranst", "Ravels",
        "Retie", "Rijkevorsel", "Rumst", "Schilde", "Schoten",
        "Sint-Amands", "Sint-Katelijne-Waver", "Stabroek", "Turnhout",
        "Vorselaar", "Vosselaar", "Westerlo", "Wijnegem", "Willebroek",
        "Wuustwezel", "Zandhoven", "Zoersel", "Zwijndrecht",
    ],
    "Oost-Vlaanderen": [
        "Aalst", "Aalter", "Assenede", "Berlare", "Beveren", "Brakel",
        "Buggenhout", "De Pinte", "Deinze", "Denderleeuw", "Dendermonde",
        "Destelbergen", "Eeklo", "Erpe-Mere", "Evergem", "Gavere", "Gent",
        "Geraardsbergen", "Haaltert", "Hamme", "Herzele", "Horebeke",
        "Kaprijke", "Kluisbergen", "Kruisem", "Laarne", "Lede", "Lebbeke",
        "Lierde", "Lochristi", "Lokeren", "Maarkedal", "Maldegem",
        "Moerbeke", "Nazareth", "Ninove", "Oosterzele", "Oudenaarde",
        "Ronse", "Sint-Gillis-Waas", "Sint-Laureins", "Sint-Lievens-Houtem",
        "Sint-Martens-Latem", "Sint-Niklaas", "Stekene", "Temse",
        "Waasmunster", "Wetteren", "Wichelen", "Wortegem-Petegem",
        "Zele", "Zelzate", "Zottegem", "Zulte",
    ],
    "West-Vlaanderen": [
        "Anzegem", "Ardooie", "Avelgem", "Beernem", "Blankenberge",
        "Bredene", "Brugge", "Damme", "De Haan", "De Panne", "Deerlijk",
        "Dentergem", "Diksmuide", "Gistel", "Harelbeke", "Hooglede",
        "Houthulst", "Ichtegem", "Ieper", "Ingelmunster", "Izegem",
        "Jabbeke", "Knokke-Heist", "Koekelare", "Koksijde", "Kortemark",
        "Kortrijk", "Langemark-Poelkapelle", "Ledegem", "Lendelede",
        "Lichtervelde", "Lo-Reninge", "Menen", "Middelkerke", "Moorslede",
        "Nieuwpoort", "Oostende", "Oostkamp", "Oostrozebeke", "Oudenburg",
        "Pittem", "Poperinge", "Roeselare", "Ruiselede", "Spiere-Helkijn",
        "Staden", "Tielt", "Torhout", "Veurne", "Vleteren", "Waregem",
        "Wervik", "Wevelgem", "Wielsbeke", "Wingene", "Zedelgem",
        "Zonnebeke", "Zuienkerke", "Zwevegem",
    ],
    "Vlaams-Brabant": [
        "Aarschot", "Affligem", "Asse", "Begijnendijk", "Bekkevoort",
        "Bertem", "Bierbeek", "Boortmeerbeek", "Boutersem", "Diest",
        "Dilbeek", "Galmaarden", "Geetbets", "Glabbeek", "Gooik",
        "Grimbergen", "Haacht", "Halle", "Herent", "Hoegaarden",
        "Hoeilaart", "Holsbeek", "Huldenberg", "Kampenhout", "Kortenberg",
        "Kraainem", "Landen", "Lennik", "Leuven", "Liedekerke",
        "Linkebeek", "Linter", "Londerzeel", "Lubbeek", "Machelen",
        "Meise", "Merchtem", "Opwijk", "Oud-Heverlee", "Overijse",
        "Pepingen", "Rotselaar", "Scherpenheuvel-Zichem",
        "Sint-Genesius-Rode", "Sint-Pieters-Leeuw", "Steenokkerzeel",
        "Ternat", "Tervuren", "Tienen", "Tielt-Winge", "Tremelo",
        "Vilvoorde", "Wemmel", "Wezembeek-Oppem", "Zaventem", "Zemst",
        "Zoutleeuw",
    ],
    "Limburg": [
        "As", "Beringen", "Bilzen", "Bocholt", "Bree", "Diepenbeek",
        "Dilsen-Stokkem", "Genk", "Gingelom", "Halen", "Ham",
        "Hamont-Achel", "Hasselt", "Hechtel-Eksel", "Heers",
        "Herk-de-Stad", "Heusden-Zolder", "Hoeselt",
        "Houthalen-Helchteren", "Kinrooi", "Kortessem", "Lanaken",
        "Leopoldsburg", "Lommel", "Lummen", "Maaseik", "Maasmechelen",
        "Nieuwerkerken", "Oudsbergen", "Peer", "Pelt", "Riemst",
        "Sint-Truiden", "Tessenderlo", "Tongeren", "Wellen", "Zonhoven",
        "Zutendaal",
    ],
    "Brussel": [
        "Anderlecht", "Auderghem", "Oudergem", "Berchem-Sainte-Agathe",
        "Sint-Agatha-Berchem", "Brussel", "Bruxelles", "Etterbeek",
        "Evere", "Forest", "Vorst", "Ganshoren", "Ixelles", "Elsene",
        "Jette", "Koekelberg", "Molenbeek", "Molenbeek-Saint-Jean",
        "Sint-Jans-Molenbeek", "Saint-Gilles", "Sint-Gillis",
        "Saint-Josse-ten-Noode", "Sint-Joost-ten-Node", "Schaarbeek",
        "Schaerbeek", "Uccle", "Ukkel", "Watermael-Boitsfort",
        "Watermaal-Bosvoorde", "Woluwe-Saint-Lambert",
        "Sint-Lambrechts-Woluwe", "Woluwe-Saint-Pierre",
        "Sint-Pieters-Woluwe",
    ],
    "Henegouwen": [
        "Antoing", "Ath", "Beaumont", "Beloeil", "Bernissart", "Binche",
        "Braine-le-Comte", "Brugelette", "Brunehaut",
        "Chapelle-lez-Herlaimont", "Charleroi", "Chatelet", "Châtelet",
        "Chièvres", "Chimay", "Colfontaine", "Comines-Warneton",
        "Komen-Waasten", "Dour", "Ecaussinnes", "Ellezelles", "Enghien",
        "Edingen", "Erquelinnes", "Estinnes", "Farciennes", "Fleurus",
        "Flobecq", "Fontaine-l'Evêque", "Frameries", "Gerpinnes",
        "Ham-sur-Heure-Nalinnes", "Hensies", "Jurbise", "La Louvière",
        "Lens", "Les Bons Villers", "Lessines", "Leuze-en-Hainaut",
        "Lobbes", "Manage", "Merbes-le-Château", "Momignies", "Mons",
        "Bergen", "Morlanwelz", "Mouscron", "Moeskroen", "Péruwelz",
        "Pont-à-Celles", "Quaregnon", "Quévy", "Quiévrain", "Rumes",
        "Saint-Ghislain", "Silly", "Sivry-Rance", "Soignies", "Seneffe",
        "Thuin", "Tournai", "Doornik", "Walcourt",
    ],
    "Namen": [
        "Andenne", "Anhée", "Assesse", "Beauraing", "Bièvre", "Ciney",
        "Couvin", "Dinant", "Doische", "Eghezée", "Fernelmont",
        "Floreffe", "Florennes", "Fosses-la-Ville", "Gembloux", "Gedinne",
        "Gesves", "Hamois", "Hastière", "Havelange",
        "Jemeppe-sur-Sambre", "La Bruyère", "Mettet", "Namur", "Namen",
        "Ohey", "Onhaye", "Philippeville", "Profondeville", "Rochefort",
        "Sambreville", "Sombreffe", "Somme-Leuze", "Viroinval",
        "Vresse-sur-Semois", "Walcourt", "Yvoir",
    ],
    "Luik": [
        "Amel", "Ans", "Anthisnes", "Aywaille", "Bassenge", "Berloz",
        "Beyne-Heusay", "Blegny", "Braives", "Bullange", "Burdinne",
        "Burg-Reuland", "Butgenbach", "Dalhem", "Dison", "Esneux",
        "Eupen", "Ferrières", "Fexhe-le-Haut-Clocher", "Flémalle",
        "Fléron", "Geer", "Grâce-Hollogne", "Hamoir", "Héron", "Herstal",
        "Herve", "Huy", "Hoei", "Juprelle", "Kelmis", "Liège", "Luik",
        "Lierneux", "Limbourg", "Lincent", "Lontzen", "Malmedy",
        "Marchin", "Modave", "Nandrin", "Neupré", "Olne", "Oreye",
        "Ouffet", "Oupeye", "Pepinster", "Plombières", "Raeren",
        "Remicourt", "Saint-Georges-sur-Meuse", "Saint-Nicolas",
        "Seraing", "Sint-Vith", "Sankt Vith", "Soumagne", "Spa",
        "Sprimont", "Stoumont", "Theux", "Thimister-Clermont", "Tinlot",
        "Trooz", "Verlaine", "Verviers", "Villers-le-Bouillet", "Visé",
        "Wanze", "Waremme", "Wasseiges", "Welkenraedt",
    ],
    "Luxemburg": [
        "Arlon", "Aarlen", "Attert", "Aubange", "Bastogne", "Bertogne",
        "Bertrix", "Bouillon", "Chiny", "Daverdisse", "Durbuy", "Erezée",
        "Etalle", "Fauvillers", "Florenville", "Gouvy", "Herbeumont",
        "Hotton", "Houffalize", "La Roche-en-Ardenne", "Léglise", "Libin",
        "Libramont-Chevigny", "Manhay", "Marche-en-Famenne", "Martelange",
        "Meix-devant-Virton", "Messancy", "Musson", "Nassogne",
        "Neufchâteau", "Paliseul", "Rendeux", "Rouvroy", "Saint-Hubert",
        "Saint-Léger", "Sainte-Ode", "Tellin", "Tenneville", "Tintigny",
        "Vaux-sur-Sûre", "Vielsalm", "Virton", "Wellin",
    ],
    "Waals-Brabant": [
        "Beauvechain", "Braine-l'Alleud", "Braine-le-Château",
        "Chaumont-Gistoux", "Court-Saint-Etienne", "Genappe",
        "Grez-Doiceau", "Incourt", "Ittre", "Jodoigne", "La Hulpe",
        "Lasne", "Mont-Saint-Guibert", "Nivelles", "Nijvel", "Orp-Jauche",
        "Ottignies-Louvain-la-Neuve", "Perwez", "Ramillies", "Rebecq",
        "Rixensart", "Tubize", "Tubeke", "Villers-la-Ville", "Walhain",
        "Waterloo", "Wavre", "Waver",
    ],
}

EXTRA_LABELS = {
    "gender": "Geslacht",
    "age": "Leeftijd",
    "orientation": "Geaardheid",
    "nationality": "Nationaliteit",
    "ethnicity": "Etniciteit",
    "languages": "Talen",
    "height": "Lengte",
    "weight": "Gewicht",
    "hair": "Haarkleur",
    "eyes": "Kleur ogen",
    "intimate_grooming": "Intiem kapsel",
    "bust": "Cupmaat",
    "penis_size": "Formaat penis",
    "tattoos": "Tatoeages",
    "piercings": "Piercings",
    "smoker": "Roker",
    "price_incall": "Tarieven privé",
    "price_outcall": "Tarieven escort",
}

router = APIRouter()

PAGE_SIZE = 24


def _build_profile_query(db, q, gender, location, province, nationality, language,
                          ad_category, ad_location, with_phone, with_photo,
                          show_archived=False, archived_only=False,
                          run_id="", run_filter="",
                          contacted_only=False, visited_only=False,
                          service=""):
    query = db.query(Profile).filter(Profile.is_active == True)
    if archived_only:
        query = query.filter(Profile.is_archived == True)
    elif not show_archived:
        query = query.filter(Profile.is_archived != True)
    if contacted_only:
        query = query.filter(Profile.is_contacted == True)
    if visited_only:
        query = query.filter(Profile.is_visited == True)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Profile.username.ilike(like)
            | Profile.display_name.ilike(like)
            | Profile.location.ilike(like)
            | Profile.phone.ilike(like)
            | Profile.extra_data.ilike(like)
        )
    if gender:
        query = query.filter(Profile.extra_data.contains(f'"gender": "{gender}"'))
    if province and province in PROVINCE_CITIES:
        query = query.filter(Profile.location.in_(PROVINCE_CITIES[province]))
    elif location:
        query = query.filter(Profile.location == location)
    if nationality:
        query = query.filter(Profile.extra_data.ilike(f'%"nationality": "{nationality}"%'))
    if language:
        query = query.filter(Profile.extra_data.ilike(f'%"languages": "%{language}%"'))
    if service:
        query = query.filter(Profile.extra_data.ilike(f'%"{service}"%'))
    if ad_category:
        query = query.filter(
            exists().where(
                Advertisement.profile_id == Profile.id,
                Advertisement.category == ad_category,
                Advertisement.is_active == True,
            )
        )
    if ad_location:
        query = query.filter(
            exists().where(
                Advertisement.profile_id == Profile.id,
                Advertisement.location == ad_location,
                Advertisement.is_active == True,
            )
        )
    if with_phone:
        query = query.filter(Profile.phone.isnot(None), Profile.phone != "")
    if with_photo:
        query = query.filter(Profile.photos.any())
    if run_id:
        scrape_run = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first()
        if scrape_run:
            run_end = scrape_run.finished_at or datetime.utcnow()
            if run_filter == "new":
                query = query.filter(
                    Profile.first_seen >= scrape_run.started_at,
                    Profile.first_seen <= run_end,
                )
            elif run_filter == "updated":
                query = query.filter(
                    Profile.last_changed >= scrape_run.started_at,
                    Profile.last_changed <= run_end,
                    Profile.first_seen < scrape_run.started_at,
                )
    return query


def _dropdown_values(db, archived_only=False, contacted_only=False, visited_only=False):
    """Return distinct filter dropdown values."""
    base_filter = [Profile.is_active == True]
    if archived_only:
        base_filter.append(Profile.is_archived == True)
    if contacted_only:
        base_filter.append(Profile.is_contacted == True)
    if visited_only:
        base_filter.append(Profile.is_visited == True)

    distinct_locations = [
        row[0]
        for row in db.query(Profile.location)
        .filter(*base_filter, Profile.location.isnot(None), Profile.location != "")
        .distinct()
        .order_by(Profile.location)
        .all()
    ]
    location_set = set(distinct_locations)
    distinct_provinces = [
        prov for prov, cities in PROVINCE_CITIES.items()
        if any(c in location_set for c in cities)
    ]

    _nationalities: set[str] = set()
    _languages: set[str] = set()
    _services: set[str] = set()
    for (ed,) in (
        db.query(Profile.extra_data)
        .filter(*base_filter, Profile.extra_data.isnot(None), Profile.extra_data != "")
        .all()
    ):
        try:
            d = json.loads(ed)
            if d.get("nationality"):
                _nationalities.add(str(d["nationality"]).strip())
            if d.get("languages"):
                langs = d["languages"]
                if isinstance(langs, list):
                    _languages.update(l.strip() for l in langs if l.strip())
                else:
                    _languages.update(l.strip() for l in str(langs).split(",") if l.strip())
            svcs = d.get("services", {})
            if isinstance(svcs, dict):
                for items in svcs.values():
                    if isinstance(items, list):
                        _services.update(i.strip() for i in items if i.strip())
        except Exception:
            pass

    return {
        "distinct_locations": distinct_locations,
        "distinct_provinces": distinct_provinces,
        "distinct_nationalities": sorted(_nationalities),
        "distinct_languages": sorted(_languages),
        "distinct_services": sorted(_services),
    }


@router.get("/", response_class=HTMLResponse)
async def profile_list(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = Query(""),
    gender: str = Query(""),
    location: str = Query(""),
    nationality: str = Query(""),
    language: str = Query(""),
    province: str = Query(""),
    ad_category: str = Query(""),
    ad_location: str = Query(""),
    with_phone: int = Query(0),
    with_photo: int = Query(0),
    show_archived: int = Query(0),
    service: str = Query(""),
    run_id: str = Query(""),
    run_filter: str = Query(""),
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    dropdowns = _dropdown_values(db)

    distinct_ad_locations = [
        row[0]
        for row in db.query(Advertisement.location)
        .filter(Advertisement.location.isnot(None), Advertisement.location != "", Advertisement.is_active == True)
        .distinct()
        .order_by(Advertisement.location)
        .all()
    ]

    _ALL_AD_CATEGORIES = ["escort", "massage", "prive-ontvangst", "shemale"]
    _present_cats = {
        row[0]
        for row in db.query(Advertisement.category)
        .filter(Advertisement.category.isnot(None), Advertisement.category != "")
        .distinct()
        .all()
    }
    distinct_ad_categories = [c for c in _ALL_AD_CATEGORIES if c in _present_cats]

    run_context = db.query(ScrapeRun).filter(ScrapeRun.id == run_id).first() if run_id else None

    query = _build_profile_query(
        db, q, gender, location, province, nationality, language,
        ad_category, ad_location, with_phone, with_photo,
        show_archived=bool(show_archived),
        service=service,
        run_id=run_id, run_filter=run_filter,
    )
    total = query.count()
    profiles = (
        query.order_by(Profile.last_scraped.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    total_pages = math.ceil(total / PAGE_SIZE) if total else 1
    filters_active = bool(
        gender or location or province or nationality or language
        or ad_category or ad_location
        or with_phone or with_photo or show_archived or service
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "profiles": profiles,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "page_size": PAGE_SIZE,
            "q": q,
            "gender": gender,
            "location": location,
            "province": province,
            "nationality": nationality,
            "language": language,
            "ad_category": ad_category,
            "ad_location": ad_location,
            "with_phone": with_phone,
            "with_photo": with_photo,
            "show_archived": show_archived,
            "service": service,
            "filters_active": filters_active,
            "archive_view": False,
            "contacted_view": False,
            "visited_view": False,
            "run_id": run_id,
            "run_filter": run_filter,
            "run_context": run_context,
            **dropdowns,
            "distinct_ad_categories": distinct_ad_categories,
            "distinct_ad_locations": distinct_ad_locations,
        },
    )


@router.get("/archived", response_class=HTMLResponse)
async def archived_list(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = Query(""),
    gender: str = Query(""),
    location: str = Query(""),
    nationality: str = Query(""),
    language: str = Query(""),
    province: str = Query(""),
    with_phone: int = Query(0),
    with_photo: int = Query(0),
    service: str = Query(""),
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    dropdowns = _dropdown_values(db, archived_only=True)

    query = _build_profile_query(
        db, q, gender, location, province, nationality, language,
        "", "", with_phone, with_photo, archived_only=True, service=service,
    )
    total = query.count()
    profiles = (
        query.order_by(Profile.last_scraped.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    total_pages = math.ceil(total / PAGE_SIZE) if total else 1
    filters_active = bool(
        gender or location or province or nationality or language
        or with_phone or with_photo or service
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "profiles": profiles,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "page_size": PAGE_SIZE,
            "q": q,
            "gender": gender,
            "location": location,
            "province": province,
            "nationality": nationality,
            "language": language,
            "ad_category": "",
            "ad_location": "",
            "with_phone": with_phone,
            "with_photo": with_photo,
            "show_archived": 0,
            "service": service,
            "filters_active": filters_active,
            "archive_view": True,
            "contacted_view": False,
            "visited_view": False,
            "run_id": "",
            "run_filter": "",
            "run_context": None,
            **dropdowns,
            "distinct_ad_categories": [],
            "distinct_ad_locations": [],
        },
    )


@router.get("/gecontacteerd", response_class=HTMLResponse)
async def contacted_list(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = Query(""),
    gender: str = Query(""),
    location: str = Query(""),
    nationality: str = Query(""),
    language: str = Query(""),
    province: str = Query(""),
    with_phone: int = Query(0),
    with_photo: int = Query(0),
    service: str = Query(""),
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    dropdowns = _dropdown_values(db, contacted_only=True)

    query = _build_profile_query(
        db, q, gender, location, province, nationality, language,
        "", "", with_phone, with_photo, contacted_only=True, service=service,
    )
    total = query.count()
    profiles = (
        query.order_by(Profile.last_scraped.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    total_pages = math.ceil(total / PAGE_SIZE) if total else 1
    filters_active = bool(
        gender or location or province or nationality or language
        or with_phone or with_photo or service
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "profiles": profiles,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "page_size": PAGE_SIZE,
            "q": q,
            "gender": gender,
            "location": location,
            "province": province,
            "nationality": nationality,
            "language": language,
            "ad_category": "",
            "ad_location": "",
            "with_phone": with_phone,
            "with_photo": with_photo,
            "show_archived": 0,
            "service": service,
            "filters_active": filters_active,
            "archive_view": False,
            "contacted_view": True,
            "visited_view": False,
            "run_id": "",
            "run_filter": "",
            "run_context": None,
            **dropdowns,
            "distinct_ad_categories": [],
            "distinct_ad_locations": [],
        },
    )


@router.get("/bezocht", response_class=HTMLResponse)
async def visited_list(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = Query(""),
    gender: str = Query(""),
    location: str = Query(""),
    nationality: str = Query(""),
    language: str = Query(""),
    province: str = Query(""),
    with_phone: int = Query(0),
    with_photo: int = Query(0),
    service: str = Query(""),
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    dropdowns = _dropdown_values(db, visited_only=True)

    query = _build_profile_query(
        db, q, gender, location, province, nationality, language,
        "", "", with_phone, with_photo, visited_only=True, service=service,
    )
    total = query.count()
    profiles = (
        query.order_by(Profile.last_scraped.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    total_pages = math.ceil(total / PAGE_SIZE) if total else 1
    filters_active = bool(
        gender or location or province or nationality or language
        or with_phone or with_photo or service
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "profiles": profiles,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "page_size": PAGE_SIZE,
            "q": q,
            "gender": gender,
            "location": location,
            "province": province,
            "nationality": nationality,
            "language": language,
            "ad_category": "",
            "ad_location": "",
            "with_phone": with_phone,
            "with_photo": with_photo,
            "show_archived": 0,
            "service": service,
            "filters_active": filters_active,
            "archive_view": False,
            "contacted_view": False,
            "visited_view": True,
            "run_id": "",
            "run_filter": "",
            "run_context": None,
            **dropdowns,
            "distinct_ad_categories": [],
            "distinct_ad_locations": [],
        },
    )


@router.get("/profiles/more", response_class=JSONResponse)
async def profiles_more(
    request: Request,
    page: int = Query(1, ge=1),
    q: str = Query(""),
    gender: str = Query(""),
    location: str = Query(""),
    nationality: str = Query(""),
    language: str = Query(""),
    province: str = Query(""),
    ad_category: str = Query(""),
    ad_location: str = Query(""),
    with_phone: int = Query(0),
    with_photo: int = Query(0),
    show_archived: int = Query(0),
    archived_only: int = Query(0),
    contacted_only: int = Query(0),
    visited_only: int = Query(0),
    service: str = Query(""),
    run_id: str = Query(""),
    run_filter: str = Query(""),
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    query = _build_profile_query(
        db, q, gender, location, province, nationality, language,
        ad_category, ad_location, with_phone, with_photo,
        show_archived=bool(show_archived), archived_only=bool(archived_only),
        contacted_only=bool(contacted_only), visited_only=bool(visited_only),
        service=service,
        run_id=run_id, run_filter=run_filter,
    )
    total = query.count()
    profiles = (
        query.order_by(Profile.last_scraped.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    has_more = page * PAGE_SIZE < total

    grid_html = templates.env.get_template("_grid_cards.html").render(profiles=profiles)
    list_html = templates.env.get_template("_list_rows.html").render(profiles=profiles)

    return JSONResponse({"grid_html": grid_html, "list_html": list_html, "has_more": has_more})


@router.get("/profile/{profile_id}", response_class=HTMLResponse)
async def profile_detail(
    profile_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return user

    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return HTMLResponse("Profiel niet gevonden", status_code=404)

    raw_extra = {}
    if profile.extra_data:
        try:
            raw_extra = json.loads(profile.extra_data)
        except Exception:
            pass

    services = raw_extra.pop("services", {})
    if not isinstance(services, dict):
        services = {}

    whatsapp = raw_extra.pop("whatsapp", "")
    raw_extra.pop("ad_url", "")

    extra = {EXTRA_LABELS[k]: v for k, v in raw_extra.items() if k in EXTRA_LABELS and v}

    related = []
    if profile.phone:
        related = (
            db.query(Profile)
            .filter(
                Profile.phone == profile.phone,
                Profile.id != profile.id,
                Profile.is_active == True,
            )
            .limit(12)
            .all()
        )

    return templates.TemplateResponse(
        "profile_detail.html",
        {
            "request": request,
            "profile": profile,
            "extra": extra,
            "services": services,
            "whatsapp": whatsapp,
            "related": related,
        },
    )


@router.post("/profile/{profile_id}/archive")
async def toggle_archive(
    profile_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return JSONResponse({"error": "not found"}, status_code=404)
    profile.is_archived = not bool(profile.is_archived)
    db.commit()
    return JSONResponse({"is_archived": profile.is_archived})


@router.post("/profile/{profile_id}/delete")
async def delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return JSONResponse({"error": "not found"}, status_code=404)
    db.delete(profile)
    db.commit()
    return JSONResponse({"deleted": True})


@router.post("/profile/{profile_id}/contact")
async def set_contact_status(
    profile_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return JSONResponse({"error": "not found"}, status_code=404)
    body = await request.json()
    set_val = bool(body.get("set", False))
    profile.is_contacted = set_val
    if set_val:
        date_str = body.get("date", "")
        try:
            profile.contacted_at = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()
        except ValueError:
            profile.contacted_at = datetime.utcnow()
        profile.contacted_note = body.get("note", "") or ""
    else:
        profile.contacted_at = None
        profile.contacted_note = None
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/profile/{profile_id}/visit")
async def set_visit_status(
    profile_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        return JSONResponse({"error": "not found"}, status_code=404)
    body = await request.json()
    set_val = bool(body.get("set", False))
    profile.is_visited = set_val
    if set_val:
        date_str = body.get("date", "")
        try:
            profile.visited_at = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()
        except ValueError:
            profile.visited_at = datetime.utcnow()
        profile.visited_note = body.get("note", "") or ""
    else:
        profile.visited_at = None
        profile.visited_note = None
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/profiles/bulk-delete")
async def bulk_delete_profiles(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids = body.get("ids", [])
    if not ids:
        return JSONResponse({"deleted": 0})
    for p in db.query(Profile).filter(Profile.id.in_(ids)).all():
        db.delete(p)
    db.commit()
    return JSONResponse({"deleted": len(ids)})


@router.post("/profiles/bulk-restore")
async def bulk_restore_profiles(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_login),
):
    if isinstance(user, RedirectResponse):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    ids = body.get("ids", [])
    if not ids:
        return JSONResponse({"restored": 0})
    count = 0
    for p in db.query(Profile).filter(Profile.id.in_(ids)).all():
        p.is_archived = False
        count += 1
    db.commit()
    return JSONResponse({"restored": count})
