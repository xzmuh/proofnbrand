"""Servidor do painel. Biblioteca padrao apenas - nenhuma dependencia nova.

    python -m proofnbrand.cli web

Serve o SPA em web/ e uma API JSON em cima do mesmo banco que o motor alimenta.
"""
import json
import mimetypes
import os
import posixpath
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import Database
from . import export as export_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# O painel React compilado (app/ -> web/dist) tem prioridade; web/ e o
# fallback sem build, que ainda funciona se o Node nao estiver disponivel.
_DIST = os.path.join(ROOT, "web", "dist")
WEB_DIR = _DIST if os.path.exists(os.path.join(_DIST, "index.html")) else os.path.join(ROOT, "web")
STATUSES = ("novo", "contatado", "respondeu", "fechado", "descartado")

LEAD_COLUMNS = """
       s.score, s.tier, s.lead_type, s.reasons, s.pitch,
       l.id AS lead_id, l.name, l.category, l.city, l.country, l.currency,
       l.website, l.website_source, l.discovered_at,
       l.phone, l.email, l.address, l.lat, l.lon,
       p.final_url, p.platform, p.responsive, p.https, p.copyright_year,
       p.status_code, p.ttfb_ms,
       p.found_email, p.found_phone, p.found_whats,
       x.perf AS psi_perf, x.seo AS psi_seo,
       COALESCE(t.status, 'novo') AS status, t.notes
"""

# Mesmo FROM para a pagina e para a contagem: os filtros referenciam l., s. e t.,
# entao a contagem precisa exatamente dos mesmos JOINs.
LEADS_FROM = """
FROM scores s
JOIN leads l ON l.id = s.lead_id
LEFT JOIN probes p ON p.lead_id = s.lead_id
LEFT JOIN psi x ON x.lead_id = s.lead_id
LEFT JOIN lead_status t ON t.lead_id = s.lead_id
"""

MAX_PAGE_SIZE = 200


def _rows_to_leads(rows):
    for row in rows:
        row["reasons"] = json.loads(row["reasons"]) if row.get("reasons") else []
        row["maps_url"] = (
            f"https://www.google.com/maps/search/?api=1&query={row['lat']},{row['lon']}"
            if row.get("lat") else ""
        )
    return rows


def _build_where(params):
    """Traduz os filtros da querystring em (clausulas, argumentos)."""
    where, args = [], []

    def one(key):
        value = (params.get(key) or [""])[0].strip()
        return value

    for key, column in (("city", "l.city"), ("category", "l.category"),
                        ("tier", "s.tier"), ("country", "l.country")):
        value = one(key)
        if value and value != "all":
            where.append(f"{column} = ?")
            args.append(value)

    status = one("status")
    if status and status != "all":
        where.append("COALESCE(t.status, 'novo') = ?")
        args.append(status)

    # aceita lista: lead_type=site_down,dns_fail,site_error (filtro "site quebrado")
    lead_type = one("lead_type")
    if lead_type and lead_type != "all":
        kinds = [k.strip() for k in lead_type.split(",") if k.strip()]
        where.append("s.lead_type IN (%s)" % ",".join("?" for _ in kinds))
        args += kinds

    search = one("q")
    if search:
        where.append("(LOWER(l.name) LIKE ? OR LOWER(l.website) LIKE ?)")
        needle = f"%{search.lower()}%"
        args += [needle, needle]

    min_score = one("min_score")
    where.append("s.score >= ?")
    args.append(float(min_score) if min_score else 0.0)

    return where, args


def _clamp_int(raw, default, low, high):
    try:
        return max(low, min(high, int(raw)))
    except (TypeError, ValueError):
        return default


def query_leads(db, params):
    """Devolve uma pagina de leads + quantos existem no filtro inteiro."""
    def one(key):
        return (params.get(key) or [""])[0].strip()

    where, args = _build_where(params)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = db.query("SELECT COUNT(*) AS n" + LEADS_FROM + clause, tuple(args))[0]["n"]

    limit = _clamp_int(one("limit"), 50, 1, MAX_PAGE_SIZE)
    offset = _clamp_int(one("offset"), 0, 0, 10_000_000)
    # Se o filtro encolheu e o offset ficou alem do fim, volta para a ultima pagina
    # cheia em vez de devolver uma lista vazia sem explicacao.
    if offset >= total:
        offset = max(0, ((total - 1) // limit) * limit) if total else 0

    # O desempate por id e obrigatorio: muitos leads empatam em score, e sem
    # ordem estavel o OFFSET repetiria ou pularia linhas entre paginas.
    sql = ("SELECT" + LEAD_COLUMNS + LEADS_FROM + clause
           + " ORDER BY s.score DESC, l.id ASC LIMIT ? OFFSET ?")

    rows = db.query(sql, tuple(args) + (limit, offset))
    return {
        "leads": _rows_to_leads(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def build_summary(db):
    def scalar(sql, default=0):
        rows = db.query(sql)
        return (rows[0].get("n") if rows else default) or default

    total = scalar("SELECT COUNT(*) AS n FROM leads")
    scored = scalar("SELECT COUNT(*) AS n FROM scores")
    no_site = scalar("SELECT COUNT(*) AS n FROM leads WHERE website = ''")
    hot = scalar("SELECT COUNT(*) AS n FROM scores WHERE tier IN ('A','B')")
    avg = db.query("SELECT AVG(score) AS n FROM scores")
    avg_score = round(avg[0]["n"], 1) if avg and avg[0]["n"] is not None else 0.0
    probed = scalar("SELECT COUNT(*) AS n FROM probes")
    psi_done = scalar("SELECT COUNT(*) AS n FROM psi")

    return {
        "total": total,
        "scored": scored,
        "no_site": no_site,
        "hot": hot,
        "avg_score": avg_score,
        "probed": probed,
        "psi": psi_done,
        "tiers": db.query("SELECT tier, COUNT(*) AS n FROM scores GROUP BY tier ORDER BY tier"),
        "cities": db.query("""SELECT l.city, l.country, COUNT(*) AS n,
                                     SUM(CASE WHEN s.tier IN ('A','B') THEN 1 ELSE 0 END) AS hot
                              FROM leads l LEFT JOIN scores s ON s.lead_id = l.id
                              GROUP BY l.city, l.country ORDER BY n DESC"""),
        "categories": db.query("""SELECT l.category, COUNT(*) AS n,
                                         AVG(s.score) AS avg_score,
                                         SUM(CASE WHEN s.tier IN ('A','B') THEN 1 ELSE 0 END) AS hot
                                  FROM leads l LEFT JOIN scores s ON s.lead_id = l.id
                                  GROUP BY l.category ORDER BY n DESC"""),
        "lead_types": db.query("""SELECT lead_type, COUNT(*) AS n FROM scores
                                  GROUP BY lead_type ORDER BY n DESC"""),
        "statuses": db.query("""SELECT COALESCE(status,'novo') AS status, COUNT(*) AS n
                                FROM lead_status GROUP BY status"""),
    }


def set_status(db, lead_id, status, notes):
    db.execute(
        """INSERT INTO lead_status (lead_id, status, notes, updated_at) VALUES (?,?,?,?)
           ON CONFLICT (lead_id) DO UPDATE SET status=EXCLUDED.status,
                                               notes=EXCLUDED.notes,
                                               updated_at=EXCLUDED.updated_at""",
        (lead_id, status, notes or "", datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


def export_by_category(db, min_score=40.0):
    """Salva um CSV por categoria em out/por-categoria/."""
    rows = export_mod.fetch_ranked(db, min_score)
    buckets = {}
    for row in rows:
        buckets.setdefault(row["category"] or "sem-categoria", []).append(row)

    outdir = os.path.join(ROOT, "out", "por-categoria")
    written = []
    for category, items in buckets.items():
        path = os.path.join(outdir, f"{category}.csv")
        export_mod.to_csv(items, path)
        written.append({"category": category, "count": len(items), "path": path})
    return written


class Handler(BaseHTTPRequestHandler):
    server_version = "proof-n-brand"

    def log_message(self, fmt, *args):  # silencia o log linha-a-linha
        pass

    # ---------- helpers ----------

    def _send(self, payload, status=200, content_type="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        rel = posixpath.normpath(path.lstrip("/")) or "index.html"
        if rel.startswith(".."):
            return self._send({"error": "not found"}, 404)
        full = os.path.join(WEB_DIR, rel.replace("/", os.sep))
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.exists(full):
            full = os.path.join(WEB_DIR, "index.html")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(fh.read(), 200, ctype)

    # ---------- rotas ----------

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        if not route.startswith("/api/"):
            return self._static(route)

        db = Database()
        try:
            if route == "/api/summary":
                return self._send(build_summary(db))
            if route == "/api/leads":
                return self._send(query_leads(db, params))
            if route == "/api/export":
                rows = export_mod.fetch_ranked(db, float((params.get("min_score") or ["40"])[0]))
                csv_path = export_mod.to_csv(rows, os.path.join(ROOT, "out", "leads.csv"))
                md_path = export_mod.to_markdown(rows, os.path.join(ROOT, "out", "leads.md"))
                return self._send({"count": len(rows), "csv": csv_path, "md": md_path})
            if route == "/api/export-by-category":
                written = export_by_category(db, float((params.get("min_score") or ["40"])[0]))
                return self._send({"files": written,
                                   "dir": os.path.join(ROOT, "out", "por-categoria")})
            return self._send({"error": "rota desconhecida"}, 404)
        except Exception as exc:
            return self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)
        finally:
            db.close()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send({"error": "json invalido"}, 400)

        if parsed.path != "/api/status":
            return self._send({"error": "rota desconhecida"}, 404)

        lead_id = payload.get("lead_id")
        status = payload.get("status")
        if not lead_id or status not in STATUSES:
            return self._send({"error": f"status precisa ser um de {STATUSES}"}, 400)

        db = Database()
        try:
            if not db.query("SELECT 1 AS x FROM leads WHERE id = ?", (lead_id,)):
                return self._send({"error": f"lead '{lead_id}' nao existe"}, 404)
            set_status(db, lead_id, status, payload.get("notes"))
            return self._send({"ok": True, "lead_id": lead_id, "status": status})
        except Exception as exc:
            return self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)
        finally:
            db.close()


def serve(host="127.0.0.1", port=8787, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Painel em {url}   (Ctrl+C para parar)", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        httpd.server_close()
