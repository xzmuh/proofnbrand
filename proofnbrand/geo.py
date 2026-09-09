"""Resolve nome de cidade -> bounding box via Nominatim (OSM). Gratuito, sem chave.

Politica do Nominatim: no maximo 1 req/s e User-Agent identificavel.
O resultado fica em cache no banco, entao cada cidade e consultada uma unica vez.
"""
import os
import time
from datetime import datetime, timezone

import requests

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = os.environ.get("PNB_UA", "proof-n-brand/0.1 (lead prospecting; contato: set PNB_UA)")
_last_call = [0.0]


def _throttle(min_interval=1.1):
    delta = time.time() - _last_call[0]
    if delta < min_interval:
        time.sleep(min_interval - delta)
    _last_call[0] = time.time()


def bbox_for_city(db, city):
    """Devolve (south, west, north, east) ou None."""
    parts = [city["name"], city.get("state") or "", city["country"]]
    key = "nominatim:" + ",".join(p for p in parts if p)

    cached = db.cache_get(key)
    if cached:
        return tuple(cached["bbox"]) if cached.get("bbox") else None

    _throttle()
    resp = requests.get(
        NOMINATIM,
        params={
            "q": ", ".join(p for p in parts if p),
            "format": "json",
            "limit": 1,
            "addressdetails": 0,
        },
        headers={"User-Agent": UA, "Accept-Language": "en"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    now = datetime.now(timezone.utc).isoformat()

    if not data:
        db.cache_set(key, {"bbox": None}, now)
        return None

    # Nominatim devolve [south, north, west, east] como strings.
    s, n, w, e = (float(x) for x in data[0]["boundingbox"])
    bbox = (s, w, n, e)  # ordem que o Overpass espera
    db.cache_set(key, {"bbox": list(bbox), "display_name": data[0].get("display_name")}, now)
    return bbox
