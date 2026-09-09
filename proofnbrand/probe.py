"""Auditoria barata do site: um GET no HTML revela ~80% dos problemas vendaveis.

Nada aqui custa dinheiro. So os finalistas seguem para o PageSpeed.
"""
import re
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from requests.exceptions import SSLError

MAX_BYTES = 500_000
TIMEOUT = (6, 14)  # (connect, read)
UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Dominios que NAO sao site proprio: o negocio nao tem site, tem perfil.
SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "fb.me", "instagram.com", "linktr.ee", "linktree.com",
    "twitter.com", "x.com", "yelp.com", "yelp.ie", "tripadvisor.com", "wa.me",
    "business.site", "sites.google.com", "linkedin.com", "wixsite.com",
    "weebly.com", "blogspot.com", "wordpress.com", "tumblr.com",
    "zocdoc.com", "yellowpages.com", "doctolib.fr", "doctolib.de",
)

# Construtores "sem projeto": template padrao, quase sempre feito pelo proprio dono.
BUILDER_PLATFORMS = {"wix", "godaddy", "weebly", "google_sites", "jimdo", "site123"}

PLATFORM_PATTERNS = [
    ("wix",          re.compile(r"static\.parastorage\.com|wix\.com/website|X-Wix-", re.I)),
    ("squarespace",  re.compile(r"static1\.squarespace\.com|squarespace\.com", re.I)),
    ("godaddy",      re.compile(r"img1\.wsimg\.com|godaddy(?:sites)?\.com", re.I)),
    ("weebly",       re.compile(r"weebly\.com|editmysite\.com", re.I)),
    ("jimdo",        re.compile(r"jimdo(?:site)?\.com", re.I)),
    ("site123",      re.compile(r"site123\.me", re.I)),
    ("shopify",      re.compile(r"cdn\.shopify\.com|shopifycloud", re.I)),
    ("webflow",      re.compile(r"assets\.website-files\.com|webflow\.(?:io|com)", re.I)),
    ("google_sites", re.compile(r"sites\.google\.com|business\.site", re.I)),
    ("joomla",       re.compile(r"/media/jui/|Joomla!", re.I)),
    ("drupal",       re.compile(r"Drupal\.settings|/sites/default/files/", re.I)),
    ("wordpress",    re.compile(r"/wp-content/|/wp-includes/", re.I)),
]

RE_VIEWPORT = re.compile(r"<meta[^>]+name=[\"']?viewport", re.I)
RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
RE_META_DESC = re.compile(r"<meta[^>]+name=[\"']?description[\"']?[^>]*content=[\"']([^\"']{10,})", re.I)
RE_OG = re.compile(r"<meta[^>]+property=[\"']og:", re.I)
RE_SCHEMA = re.compile(r"application/ld\+json|itemtype=[\"']https?://schema\.org", re.I)
RE_FAVICON = re.compile(r"<link[^>]+rel=[\"'][^\"']*icon", re.I)
RE_COPYRIGHT = re.compile(r"(?:©|&copy;|copyright)[^0-9]{0,20}(?:\d{4}\s*[-–]\s*)?(20\d{2}|19\d{2})", re.I)
RE_LEGACY = re.compile(r"<font\b|<center\b|<marquee\b|bgcolor=|<frameset|\.swf\b|cellpadding=", re.I)
RE_MODERN_CSS = re.compile(r"display:\s*(?:flex|grid)|grid-template|flex-direction|tailwind|bootstrap", re.I)
RE_JQUERY_OLD = re.compile(r"jquery[.-]?(1\.[0-8])[\.\d]*(?:\.min)?\.js", re.I)
RE_MIXED = re.compile(r"(?:src|href)=[\"']http://(?!localhost)", re.I)
RE_PARKED = re.compile(
    r"coming soon|under construction|site (?:is )?(?:under|in) (?:construction|maintenance)|"
    r"domain (?:is )?for sale|buy this domain|default web site page|welcome to nginx|"
    r"apache2 (?:ubuntu|debian) default", re.I)
RE_TABLE = re.compile(r"<table\b", re.I)

# Contato dentro da propria pagina. A OSM quase nunca traz e-mail; o site traz.
RE_MAILTO = re.compile(r"mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.I)
RE_TEL = re.compile(r"tel:(\+?[\d\s().-]{7,25})", re.I)
RE_WHATS = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send/\?phone=)(\+?\d{8,15})", re.I)
# Enderecos de infraestrutura, nao de prospeccao.
RE_JUNK_EMAIL = re.compile(
    r"(?:example|sentry|wixpress|godaddy|squarespace|wordpress\.|shopify|"
    r"hostmaster|postmaster|abuse@|noreply|no-reply|donotreply|sentry\.io)", re.I)

CURRENT_YEAR = datetime.now(timezone.utc).year

PROBE_FIELDS = (
    "checked_at", "final_url", "status_code", "reachable", "error", "ttfb_ms",
    "html_bytes", "https", "responsive", "platform", "copyright_year", "has_title",
    "has_meta_desc", "has_og", "has_schema", "has_favicon", "legacy_html", "signals",
)


def _blank_result(error=""):
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "final_url": "", "status_code": None, "reachable": 0, "error": error,
        "ttfb_ms": None, "html_bytes": None, "https": 0, "responsive": 0,
        "platform": "", "copyright_year": None, "has_title": 0, "has_meta_desc": 0,
        "has_og": 0, "has_schema": 0, "has_favicon": 0, "legacy_html": 0, "signals": [],
        "found_email": "", "found_phone": "", "found_whats": "",
    }


def host_of(url):
    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def is_social_only(url):
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in SOCIAL_HOSTS)


def _fetch(session, url):
    """Devolve (resp, html, erro). Le no maximo MAX_BYTES."""
    try:
        resp = session.get(
            url, timeout=TIMEOUT, allow_redirects=True, stream=True,
            headers={"User-Agent": UA_BROWSER, "Accept-Language": "en-US,en;q=0.9"},
        )
    except SSLError:
        return None, "", "ssl_error"
    except requests.exceptions.ConnectionError as exc:
        inner = str(exc.__cause__ or exc)
        kind = "dns_fail" if ("NameResolution" in inner or "getaddrinfo" in inner) else "conn_refused"
        return None, "", kind
    except requests.exceptions.Timeout:
        return None, "", "timeout"
    except Exception as exc:
        return None, "", "err_" + type(exc).__name__

    chunks, total = [], 0
    try:
        for chunk in resp.iter_content(8192):
            chunks.append(chunk)
            total += len(chunk)
            if total >= MAX_BYTES:
                break
    except Exception:
        pass
    finally:
        resp.close()

    raw = b"".join(chunks)
    encoding = resp.encoding or "utf-8"
    html = raw.decode(encoding, errors="ignore")
    return resp, html, ""


def _https_reachable(url):
    """Testa se o dominio serve HTTPS valido. Usado quando o site declarado e http://."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return True
    except Exception:
        return False


def probe_url(url):
    """Auditoria de um unico site. Nunca levanta excecao."""
    out = _blank_result()

    if is_social_only(url):
        out["platform"] = "social_profile"
        out["error"] = "social_only"
        out["signals"] = ["social_only"]
        return out

    session = requests.Session()
    try:
        resp, html, err = _fetch(session, url)

        # Se https falhou, tenta http: distingue "sem certificado" de "site morto".
        if resp is None and url.startswith("https://"):
            resp, html, err2 = _fetch(session, "http://" + url[len("https://"):])
            if resp is not None:
                out["signals"].append("no_ssl")
                err = ""
            else:
                err = err or err2
    finally:
        session.close()

    if resp is None:
        out["error"] = err or "unknown"
        out["signals"].append(err if err in ("dns_fail", "timeout") else "site_down")
        return out

    signals = out["signals"]
    out["reachable"] = 1
    out["final_url"] = resp.url
    out["status_code"] = resp.status_code
    out["ttfb_ms"] = int(resp.elapsed.total_seconds() * 1000)
    out["html_bytes"] = len(html.encode("utf-8", errors="ignore"))
    out["https"] = 1 if resp.url.startswith("https://") else 0

    if resp.status_code >= 400:
        signals.append("http_" + str(resp.status_code))
        signals.append("site_error")

    if not out["https"]:
        signals.append("no_ssl" if not _https_reachable(resp.url) else "http_no_redirect")

    out["responsive"] = 1 if RE_VIEWPORT.search(html) else 0
    if not out["responsive"]:
        signals.append("not_responsive")

    title_m = RE_TITLE.search(html)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    out["has_title"] = 1 if len(title) > 3 else 0
    if not out["has_title"]:
        signals.append("no_title")
    elif title.lower() in ("home", "untitled", "index", "welcome", "new page 1", "home page"):
        signals.append("generic_title")

    out["has_meta_desc"] = 1 if RE_META_DESC.search(html) else 0
    out["has_og"] = 1 if RE_OG.search(html) else 0
    out["has_schema"] = 1 if RE_SCHEMA.search(html) else 0
    out["has_favicon"] = 1 if RE_FAVICON.search(html) else 0
    for field, signal in (("has_meta_desc", "no_meta_description"), ("has_og", "no_open_graph"),
                          ("has_schema", "no_schema_org"), ("has_favicon", "no_favicon")):
        if not out[field]:
            signals.append(signal)

    header_blob = " ".join(f"{k}: {v}" for k, v in resp.headers.items())
    for name, pattern in PLATFORM_PATTERNS:
        if pattern.search(html) or pattern.search(header_blob):
            out["platform"] = name
            break
    if out["platform"] in BUILDER_PLATFORMS:
        signals.append("diy_builder")

    years = [int(y) for y in RE_COPYRIGHT.findall(html) if 1990 <= int(y) <= CURRENT_YEAR + 1]
    if years:
        out["copyright_year"] = max(years)
        if out["copyright_year"] <= CURRENT_YEAR - 2:
            signals.append("stale_copyright_" + str(out["copyright_year"]))

    legacy_hits = len(RE_LEGACY.findall(html))
    table_heavy = len(RE_TABLE.findall(html)) >= 5 and not RE_MODERN_CSS.search(html)
    out["legacy_html"] = 1 if (legacy_hits >= 3 or table_heavy) else 0
    if out["legacy_html"]:
        signals.append("legacy_html")

    if RE_JQUERY_OLD.search(html):
        signals.append("ancient_jquery")
    if out["https"] and RE_MIXED.search(html):
        signals.append("mixed_content")
    # Uma pagina de erro ja foi classificada como site_error; nao e "estacionada".
    if resp.status_code < 400 and (RE_PARKED.search(html) or len(html.strip()) < 800):
        signals.append("parked_or_empty")

    if out["ttfb_ms"] > 1500:
        signals.append("very_slow_ttfb")
    elif out["ttfb_ms"] > 800:
        signals.append("slow_ttfb")

    if out["html_bytes"] > 400_000:
        signals.append("bloated_html")

    if re.search(r"apache/2\.[0-2]\b|iis/[5-7]\.", (resp.headers.get("Server") or ""), re.I):
        signals.append("ancient_server")

    # --- contato colhido da propria pagina ---
    # Muda o jogo: a OSM traz e-mail em ~1% dos casos, o rodape do site traz sempre.
    emails = [e for e in RE_MAILTO.findall(html) if not RE_JUNK_EMAIL.search(e)]
    if emails:
        out["found_email"] = emails[0].lower()

    phones = [re.sub(r"[^\d+]", "", t) for t in RE_TEL.findall(html)]
    phones = [t for t in phones if len(re.sub(r"\D", "", t)) >= 8]
    if phones:
        out["found_phone"] = phones[0]

    whats = RE_WHATS.findall(html)
    if whats:
        out["found_whats"] = re.sub(r"\D", "", whats[0])

    return out


def probe_many(urls, workers=12, on_result=None):
    """Audita varios sites em paralelo. Devolve {url: resultado}."""
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe_url, u): u for u in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                results[url] = fut.result()
            except Exception as exc:
                results[url] = _blank_result("probe_crash_" + type(exc).__name__)
                results[url]["signals"] = ["probe_crash"]
            if on_result:
                on_result(url, results[url])
    return results
