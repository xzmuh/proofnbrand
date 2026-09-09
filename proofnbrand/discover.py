"""Descobre o site de um negocio quando a OpenStreetMap nao sabe dele.

O problema que isto resolve: a OSM nao e um cadastro de empresas. "Sem tag
website" quer dizer "ninguem mapeou", nao "nao tem site". A European Denture
Center tem eurodenture.com, duas unidades e 367 avaliacoes — e estava na nossa
lista como SEM SITE.

Estrategia: gerar dominios plausiveis a partir do nome, resolver DNS (barato),
buscar os que resolvem e so aceitar quando a pagina confirma que e o negocio
certo. Zero custo, zero chave de API.

Nao acha tudo: eurodenture.com nao sai de "European Denture Center". Por isso o
resultado nao vira "confirmado que nao tem site" — vira "nao encontrei", e o
painel oferece a busca manual.
"""
import re
import socket
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .probe import UA_BROWSER

# Palavras que descrevem o ramo, nao identificam o negocio. Saem das variantes
# do dominio e nunca servem para confirmar a identidade da pagina.
GENERIC_WORDS = {
    "dental", "dentistry", "dentist", "denture", "dentures", "odontologia",
    "odonto", "odontologica", "clinica", "clinic", "centro", "center", "centre",
    "consultorio", "studio", "estudio", "group", "grupo", "spa", "estetica",
    "beleza", "beauty", "veterinaria", "veterinario", "vet", "pet", "hospital",
    "arquitetura", "arquitetos", "architecture", "architects", "fotografia",
    "foto", "photography", "photo", "garage", "garagem", "auto", "car", "cars",
    "servicos", "services", "solucoes", "do", "da", "de", "dos", "das", "e",
    "and", "the", "of", "ltda", "me", "eireli", "sa", "llc", "inc", "pllc",
    "pa", "pc", "co", "cia", "associados", "associates", "assoc",
}

TLDS = {
    "BR": (".com.br", ".com"),
    "US": (".com", ".net"),
    "CA": (".ca", ".com"),
    "IE": (".ie", ".com"),
    "NL": (".nl", ".com"),
    "PT": (".pt", ".com"),
    "ES": (".es", ".com"),
    "IT": (".it", ".com"),
    "DE": (".de", ".com"),
    "GB": (".co.uk", ".com"),
}
DEFAULT_TLDS = (".com",)

MAX_CANDIDATES = 8
TIMEOUT = (5, 10)


def slugify(text):
    """'Cárdio Imagem' -> 'cardioimagem'"""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def words_of(name):
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-zA-Z0-9]+", text.lower()) if w]


def identity_tokens(name):
    """Palavras que identificam ESTE negocio — usadas para confirmar a pagina."""
    return [w for w in words_of(name) if len(w) >= 4 and w not in GENERIC_WORDS]


def candidate_domains(name, country):
    """Variacoes plausiveis de dominio, da mais provavel para a menos."""
    words = words_of(name)
    if not words:
        return []

    distinctive = [w for w in words if w not in GENERIC_WORDS]
    stems = []

    def add(parts):
        slug = "".join(parts)
        if 3 <= len(slug) <= 40 and slug not in stems:
            stems.append(slug)

    add(words)                       # nome inteiro
    if distinctive != words:
        add(distinctive)             # sem as palavras de ramo
    if len(words) >= 2:
        add(words[:2])               # duas primeiras

    # Deliberadamente NAO geramos dominio de uma palavra so. "Purple Rain Spa"
    # gerava purple.com (colchao) e "Night Owl Pediatric" gerava nightowl.com
    # (cameras) — dominios reais, de outra empresa, que passavam na conferencia.

    tlds = TLDS.get((country or "").upper(), DEFAULT_TLDS)
    out = []
    for stem in stems:
        for tld in tlds:
            if len(out) >= MAX_CANDIDATES:
                return out
            out.append(stem + tld)
    return out


def _resolves(domain):
    try:
        socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        return True
    except Exception:
        return False


RE_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.I | re.S)


def page_text(html):
    """Texto visivel, sem acento e sem marcacao — base da conferencia."""
    text = RE_TAGS.sub(" ", html or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower())


def _confirms(html, tokens, domain, city="", exact_name=False, context=()):
    """A pagina e mesmo deste negocio?

    Uma palavra so nao basta: purple.com contem "purple" e nao tem nada a ver
    com a "Purple Rain Spa". Duas ou mais palavras identificadoras derrubam a
    chance de coincidencia.

    Para nome com um identificador so ("CWB Sorriso" -> apenas "sorriso"),
    o que resolve e o dominio SER o nome da empresa: cwbsorriso.com.br bate
    exatamente com "CWB Sorriso", enquanto purple.com nao bate com
    "Purple Rain Spa". Exigir a cidade na pagina reprovava sites legitimos que
    simplesmente nao escrevem a cidade na home.
    """
    if not tokens:
        return False

    full = page_text(html)
    # O dominio ecoado na propria pagina nao pode servir de prova de si mesmo,
    # senao qualquer site "confirma" o proprio nome.
    text = full.replace(domain.lower(), " ")
    hits = sum(1 for token in tokens if token in text)

    # Dominio identico ao nome da empresa ja e prova forte por si so — desde que
    # exista pagina de verdade atras dele, e nao um dominio estacionado.
    if exact_name:
        return len(full) > 400

    if hits == 0:
        return False
    if len(tokens) >= 2 and hits < 2:
        return False

    # Quando o dominio NAO e o nome exato, duas palavras batendo ainda e fraco:
    # "Green Tree Dental" casou com greentree.net, que e uma ONG chamada
    # GreenTree Project. Exigimos entao um sinal do ramo ou da cidade — um site
    # de dentista fala "dental"; a ONG nao.
    corroboration = [slugify(c) for c in ([city] + list(context)) if c]
    if not corroboration:
        return False
    slug_text = slugify(text)
    return any(c in slug_text for c in corroboration)


def find_website(name, country, city="", session=None):
    """Devolve (url, dominio_testado) ou (None, tentativas)."""
    tokens = identity_tokens(name)
    if not tokens:
        return None, 0

    name_slug = slugify(name)
    # Palavras de ramo do proprio nome ("dental", "odontologia"): servem de
    # corroboracao quando o dominio nao e exatamente o nome da empresa.
    context = [w for w in words_of(name) if w in GENERIC_WORDS and len(w) >= 4]
    candidates = candidate_domains(name, country)
    close = session is None
    session = session or requests.Session()
    tried = 0
    try:
        for domain in candidates:
            if not _resolves(domain):
                continue
            tried += 1
            try:
                resp = session.get(
                    "https://" + domain, timeout=TIMEOUT, allow_redirects=True,
                    headers={"User-Agent": UA_BROWSER, "Accept-Language": "en;q=0.9"},
                )
            except Exception:
                continue
            if resp.status_code >= 400:
                continue
            html = resp.text[:120_000]
            stem = domain.split(".", 1)[0] if domain.count(".") == 1 else domain[:domain.index(".")]
            if _confirms(html, tokens, domain, city,
                         exact_name=(stem == name_slug), context=context):
                return resp.url, tried
    finally:
        if close:
            session.close()
    return None, tried


def find_many(leads, workers=10, on_result=None):
    """leads: iteravel de (lead_id, name, country, city). Devolve {lead_id: url|None}."""
    found = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(find_website, name, country, city): lead_id
            for lead_id, name, country, city in leads
        }
        for fut in as_completed(futures):
            lead_id = futures[fut]
            try:
                url, _ = fut.result()
            except Exception:
                url = None
            found[lead_id] = url
            if on_result:
                on_result(lead_id, url)
    return found
