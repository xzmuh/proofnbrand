"""Colheita de empresas na OpenStreetMap via Overpass API. Gratuito, sem chave, sem cartao."""
import os
import time
from datetime import datetime, timezone

import requests

from .score import is_chain, is_public

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = os.environ.get("PNB_UA", "proof-n-brand/0.1 (lead prospecting)")

WEBSITE_KEYS = ("website", "contact:website", "website:official", "url", "contact:url")
PHONE_KEYS = ("phone", "contact:phone", "contact:mobile", "phone:mobile")
EMAIL_KEYS = ("email", "contact:email")


def build_query(bbox, filters, timeout=180):
    south, west, north, east = bbox
    box = f"({south},{west},{north},{east})"
    body = "\n  ".join(f"nwr{f}{box};" for f in filters)
    return f"[out:json][timeout:{timeout}];\n(\n  {body}\n);\nout center tags;"


def run_query(query, retries=3):
    last_err = None
    for attempt in range(retries):
        endpoint = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            resp = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": UA},
                timeout=240,
            )
            if resp.status_code in (429, 504):
                last_err = f"{resp.status_code} em {endpoint}"
                time.sleep(15 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:  # rede, json invalido, etc
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Overpass falhou apos {retries} tentativas: {last_err}")


def _first(tags, keys):
    for k in keys:
        v = (tags.get(k) or "").strip()
        if v:
            return v
    return ""


def normalize_url(raw):
    if not raw:
        return ""
    url = raw.strip().split(";")[0].split(",")[0].strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        if url.startswith("//"):
            url = "https:" + url
        else:
            url = "https://" + url.lstrip("/")
    return url


def _address(tags):
    line = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
    rest = ", ".join(
        x for x in (tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode")) if x
    )
    return ", ".join(x for x in (line, rest) if x)


def element_to_lead(el, city, category):
    tags = el.get("tags", {})
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    # Concessionaria de montadora e orgao publico nao compram site: barrados aqui,
    # senao voltariam a cada colheita mesmo depois de apagados.
    if is_chain(tags, name) or is_public(tags, name):
        return None

    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    now = datetime.now(timezone.utc).isoformat()

    return {
        "id": f"{el['type']}/{el['id']}",
        "source": "osm",
        "name": name,
        "category": category["key"],
        "city": city["name"],
        "country": city["country"],
        "currency": city["currency"],
        "lat": lat,
        "lon": lon,
        "phone": _first(tags, PHONE_KEYS),
        "email": _first(tags, EMAIL_KEYS),
        "website": normalize_url(_first(tags, WEBSITE_KEYS)),
        "address": _address(tags),
        "tags": tags,
        "first_seen": now,
        "last_seen": now,
    }


def harvest_city_category(db, city, category, bbox, sleep_between=4.0):
    """Busca uma categoria numa cidade e grava os leads. Devolve quantidade encontrada."""
    query = build_query(bbox, category["filters"])
    elements = run_query(query)

    count = 0
    for el in elements:
        lead = element_to_lead(el, city, category)
        if lead:
            db.upsert_lead(lead)
            count += 1
    db.commit()
    time.sleep(sleep_between)  # educacao com a API publica
    return count
