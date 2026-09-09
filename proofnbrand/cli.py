"""proof-n-brand - encontra negocios estrangeiros com site ruim para prospectar.

Pipeline:  harvest (OSM) -> probe (HTTP) -> score -> psi (so os finalistas) -> score -> export

Uso rapido:
    python -m proofnbrand.cli run
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import export as export_mod
from . import discover as discover_mod, geo, overpass
from . import psi as psi_mod, probe as probe_mod, score as score_mod
from .db import Database

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "targets.json")


def load_env():
    """Le .env sem depender de biblioteca externa."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cities = [c for c in cfg["cities"] if c.get("enabled")]
    enabled = set(cfg.get("enabled_categories") or [])
    cats = [c for c in cfg["categories"] if not enabled or c["key"] in enabled]
    value_tiers = {c["key"]: c.get("value_tier", "mid") for c in cfg["categories"]}
    return cities, cats, value_tiers


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- harvest

def cmd_harvest(db, args):
    cities, cats, _ = load_config()
    if args.city:
        wanted = args.city.lower()
        cities = [c for c in cities if c["name"].lower() == wanted]
        if not cities:
            log(f"Cidade '{args.city}' nao esta ativa em config/targets.json")
            return

    log(f"Colhendo {len(cities)} cidade(s) x {len(cats)} categoria(s) na OpenStreetMap...")
    total = 0
    for city in cities:
        bbox = geo.bbox_for_city(db, city)
        if not bbox:
            log(f"  ! {city['name']}: Nominatim nao encontrou. Pulando.")
            continue
        for cat in cats:
            try:
                found = overpass.harvest_city_category(db, city, cat, bbox)
                total += found
                log(f"  {city['name']:<12} {cat['label']:<22} {found:>5} leads")
            except Exception as exc:
                log(f"  ! {city['name']} / {cat['key']}: {exc}")

    log(f"\nTotal colhido/atualizado: {total}")


# ---------------------------------------------------------------- probe

PROBE_UPSERT = """
INSERT INTO probes (lead_id, checked_at, final_url, status_code, reachable, error,
                    ttfb_ms, html_bytes, https, responsive, platform, copyright_year,
                    has_title, has_meta_desc, has_og, has_schema, has_favicon,
                    legacy_html, signals, found_email, found_phone, found_whats)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT (lead_id) DO UPDATE SET
    found_email=EXCLUDED.found_email, found_phone=EXCLUDED.found_phone,
    found_whats=EXCLUDED.found_whats,
    checked_at=EXCLUDED.checked_at, final_url=EXCLUDED.final_url,
    status_code=EXCLUDED.status_code, reachable=EXCLUDED.reachable,
    error=EXCLUDED.error, ttfb_ms=EXCLUDED.ttfb_ms, html_bytes=EXCLUDED.html_bytes,
    https=EXCLUDED.https, responsive=EXCLUDED.responsive, platform=EXCLUDED.platform,
    copyright_year=EXCLUDED.copyright_year, has_title=EXCLUDED.has_title,
    has_meta_desc=EXCLUDED.has_meta_desc, has_og=EXCLUDED.has_og,
    has_schema=EXCLUDED.has_schema, has_favicon=EXCLUDED.has_favicon,
    legacy_html=EXCLUDED.legacy_html, signals=EXCLUDED.signals
"""


def cmd_probe(db, args):
    sql = """SELECT l.id, l.website FROM leads l
             LEFT JOIN probes p ON p.lead_id = l.id
             WHERE l.website <> '' AND (p.lead_id IS NULL OR ? = 1)
             LIMIT ?"""
    rows = db.query(sql, (1 if args.refresh else 0, args.limit))
    if not rows:
        log("Nada para auditar (todos os sites ja foram checados). Use --refresh para refazer.")
        return

    log(f"Auditando {len(rows)} sites com {args.workers} workers...")
    by_url = {}
    for row in rows:
        by_url.setdefault(row["website"], []).append(row["id"])

    done = [0]

    def on_result(url, result):
        done[0] += 1
        if done[0] % 25 == 0 or done[0] == len(by_url):
            log(f"  {done[0]}/{len(by_url)}")
        for lead_id in by_url[url]:
            db.execute(PROBE_UPSERT, (
                lead_id, result["checked_at"], result["final_url"], result["status_code"],
                result["reachable"], result["error"], result["ttfb_ms"], result["html_bytes"],
                result["https"], result["responsive"], result["platform"],
                result["copyright_year"], result["has_title"], result["has_meta_desc"],
                result["has_og"], result["has_schema"], result["has_favicon"],
                result["legacy_html"], json.dumps(result["signals"]),
                result["found_email"], result["found_phone"], result["found_whats"],
            ))

    probe_mod.probe_many(list(by_url), workers=args.workers, on_result=on_result)
    db.commit()
    log("Auditoria concluida.")


# ---------------------------------------------------------------- psi

PSI_UPSERT = """
INSERT INTO psi (lead_id, checked_at, perf, seo, a11y, best, lcp_ms, cls, tbt_ms, error)
VALUES (?,?,?,?,?,?,?,?,?,?)
ON CONFLICT (lead_id) DO UPDATE SET
    checked_at=EXCLUDED.checked_at, perf=EXCLUDED.perf, seo=EXCLUDED.seo,
    a11y=EXCLUDED.a11y, best=EXCLUDED.best, lcp_ms=EXCLUDED.lcp_ms,
    cls=EXCLUDED.cls, tbt_ms=EXCLUDED.tbt_ms, error=EXCLUDED.error
"""


def cmd_psi(db, args):
    sql = """SELECT l.id, COALESCE(NULLIF(p.final_url,''), l.website) AS url, s.score
             FROM leads l
             JOIN scores s ON s.lead_id = l.id
             JOIN probes p ON p.lead_id = l.id
             LEFT JOIN psi x ON x.lead_id = l.id
             WHERE p.reachable = 1 AND s.score >= ?
               AND (x.lead_id IS NULL OR (x.perf IS NULL AND x.error <> ''))
             ORDER BY s.score DESC
             LIMIT ?"""
    rows = db.query(sql, (args.min_score, args.limit))
    if not rows:
        log("Nenhum finalista pendente de PageSpeed.")
        return

    if not os.environ.get("PSI_API_KEY"):
        log("Aviso: sem PSI_API_KEY. A API funciona, mas costuma devolver 429. "
            "Chave gratuita e sem cartao - veja .env.example")

    log(f"Rodando PageSpeed em {len(rows)} finalistas (~20s cada, {args.workers} em paralelo)...")
    by_url = {r["url"]: r["id"] for r in rows}
    done = [0]

    def on_result(url, result):
        done[0] += 1
        perf = result.get("perf")
        label = f"{perf:.0f}/100" if perf is not None else (result.get("error") or "erro")
        log(f"  {done[0]}/{len(by_url)}  {label:<12} {url[:60]}")
        db.execute(PSI_UPSERT, (
            by_url[url], result["checked_at"], result["perf"], result["seo"],
            result["a11y"], result["best"], result["lcp_ms"], result["cls"],
            result["tbt_ms"], result["error"],
        ))

    psi_mod.run_many(list(by_url), workers=args.workers, on_result=on_result)
    db.commit()
    log("PageSpeed concluido.")


# ---------------------------------------------------------------- score

SCORE_UPSERT = """
INSERT INTO scores (lead_id, score, tier, lead_type, reasons, pitch, computed_at)
VALUES (?,?,?,?,?,?,?)
ON CONFLICT (lead_id) DO UPDATE SET
    score=EXCLUDED.score, tier=EXCLUDED.tier, lead_type=EXCLUDED.lead_type,
    reasons=EXCLUDED.reasons, pitch=EXCLUDED.pitch, computed_at=EXCLUDED.computed_at
"""


def cmd_score(db, args=None):
    _, _, value_tiers = load_config()
    rows = db.query("""
        SELECT l.id, l.name, l.category, l.website, l.phone, l.email, l.tags,
               l.discovered_at,
               p.signals, p.lead_id AS probed, p.reachable,
               p.found_email, p.found_phone, p.found_whats,
               x.perf, x.seo
        FROM leads l
        LEFT JOIN probes p ON p.lead_id = l.id
        LEFT JOIN psi x ON x.lead_id = l.id
    """)

    now = datetime.now(timezone.utc).isoformat()
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    dropped = {"rede": 0, "publico": 0, "sem_contato": 0}

    for row in rows:
        lead = {
            "name": row["name"], "website": row["website"] or "",
            "phone": row["phone"] or "", "email": row["email"] or "",
            "tags": json.loads(row["tags"]) if row["tags"] else {},
            "discovered_at": row.get("discovered_at"),
        }
        probe = None
        if row.get("probed"):
            probe = {
                "signals": json.loads(row["signals"]) if row.get("signals") else [],
                "reachable": row.get("reachable"),
                "found_email": row.get("found_email") or "",
                "found_phone": row.get("found_phone") or "",
                "found_whats": row.get("found_whats") or "",
            }
        # Site declarado mas ainda nao auditado: nao da pra pontuar honestamente.
        if lead["website"] and not row.get("probed"):
            continue
        psi_data = {"perf": row["perf"], "seo": row["seo"]} if row.get("perf") is not None else None

        result = score_mod.score_lead(lead, probe, psi_data, value_tiers.get(row["category"], "mid"))

        if result is None:
            # Rede/franquia ou ninguem com quem falar: fora da lista. Apaga um
            # score antigo, senao o lead ficaria fantasma no painel.
            if score_mod.is_chain(lead["tags"], lead["name"]):
                key = "rede"
            elif score_mod.is_public(lead["tags"], lead["name"]):
                key = "publico"
            else:
                key = "sem_contato"
            dropped[key] += 1
            db.execute("DELETE FROM scores WHERE lead_id = ?", (row["id"],))
            continue

        counts[result["tier"]] += 1
        db.execute(SCORE_UPSERT, (
            row["id"], result["score"], result["tier"], result["lead_type"],
            json.dumps(result["reasons"], ensure_ascii=False), result["pitch"], now,
        ))

    db.commit()
    log(f"Pontuados: A={counts['A']}  B={counts['B']}  C={counts['C']}  D={counts['D']}")
    log(f"Descartados: {dropped['rede']} rede/franquia · {dropped['publico']} orgao publico"
        f" · {dropped['sem_contato']} sem canal de contato")


# ---------------------------------------------------------------- discover

def cmd_discover(db, args):
    """Procura o site dos leads que a OSM diz nao ter site.

    A OSM nao e cadastro de empresas: 'sem tag website' significa 'ninguem
    mapeou'. Aqui tentamos dominios plausiveis a partir do nome e so aceitamos
    quando a pagina confirma que e o negocio certo.
    """
    sql = """SELECT id, name, country, city FROM leads
             WHERE website = '' AND (discovered_at IS NULL OR ? = 1)
             LIMIT ?"""
    rows = db.query(sql, (1 if args.refresh else 0, args.limit))
    if not rows:
        log("Nenhum lead pendente de busca. Use --refresh para tentar de novo.")
        return

    log(f"Procurando site de {len(rows)} leads ({args.workers} em paralelo)...")
    now = datetime.now(timezone.utc).isoformat()
    hits = [0]
    done = [0]

    def on_result(lead_id, url):
        done[0] += 1
        if url:
            hits[0] += 1
            db.execute(
                "UPDATE leads SET website = ?, website_source = 'descoberto', "
                "discovered_at = ? WHERE id = ?", (url, now, lead_id))
            log(f"  [{done[0]}/{len(rows)}] achou: {url[:64]}")
        else:
            db.execute("UPDATE leads SET discovered_at = ? WHERE id = ?", (now, lead_id))
        if done[0] % 25 == 0:
            db.commit()

    discover_mod.find_many(
        [(r["id"], r["name"], r["country"], r["city"]) for r in rows],
        workers=args.workers, on_result=on_result)
    db.commit()

    pct = round(100 * hits[0] / max(1, len(rows)))
    log(f"\n{hits[0]} sites encontrados em {len(rows)} leads ({pct}%).")
    log("Os demais ficam marcados como 'busca automática falhou' — o que NÃO prova")
    log("que não existe site. Confira no Google antes de abordar.")


# ---------------------------------------------------------------- prune

CHILD_TABLES = ("probes", "psi", "scores", "lead_status")


def cmd_prune(db, args):
    """Apaga do banco o que nunca vai virar cliente.

    Tres alvos: categoria desligada no config, rede/franquia e orgao publico.
    Rede e publico ja sao barrados na colheita — isto aqui limpa o passivo.
    """
    _, cats, _ = load_config()
    enabled = {c["key"] for c in cats}

    rows = db.query("SELECT id, name, category, tags FROM leads")
    doomed, why = [], {"categoria": 0, "rede": 0, "publico": 0}
    samples = {"categoria": [], "rede": [], "publico": []}

    for row in rows:
        tags = json.loads(row["tags"]) if row["tags"] else {}
        name = row["name"] or ""
        if row["category"] not in enabled:
            reason = "categoria"
        elif score_mod.is_chain(tags, name):
            reason = "rede"
        elif score_mod.is_public(tags, name):
            reason = "publico"
        else:
            continue
        doomed.append(row["id"])
        why[reason] += 1
        if len(samples[reason]) < 4:
            samples[reason].append(f"{name[:32]} ({row['category']})")

    if not doomed:
        log("Nada a apagar: o banco ja esta limpo.")
        return

    log(f"Categorias ativas: {', '.join(sorted(enabled))}")
    for reason, count in why.items():
        if count:
            log(f"  {count:>5} por {reason}")
            for sample in samples[reason]:
                log(f"          - {sample}")

    if args.dry_run:
        log(f"\n[dry-run] {len(doomed)} leads seriam apagados. Rode sem --dry-run para confirmar.")
        return

    for i in range(0, len(doomed), 400):  # SQLite limita variaveis por statement
        chunk = doomed[i:i + 400]
        marks = ",".join("?" for _ in chunk)
        for table in CHILD_TABLES:
            db.execute(f"DELETE FROM {table} WHERE lead_id IN ({marks})", tuple(chunk))
        db.execute(f"DELETE FROM leads WHERE id IN ({marks})", tuple(chunk))
    db.commit()

    remaining = db.query("SELECT COUNT(*) AS n FROM leads")[0]["n"]
    log(f"\n{len(doomed)} leads apagados. Restam {remaining} no banco.")


# ---------------------------------------------------------------- export / stats

def cmd_export(db, args):
    rows = export_mod.fetch_ranked(db, args.min_score)
    if not rows:
        log("Nenhum lead pontuado ainda. Rode 'harvest' e 'probe' antes.")
        return
    csv_path = export_mod.to_csv(rows, os.path.join(ROOT, "out", "leads.csv"))
    md_path = export_mod.to_markdown(rows, os.path.join(ROOT, "out", "leads.md"), top=args.top)
    log(f"{len(rows)} leads exportados:\n  {csv_path}\n  {md_path}")


def cmd_stats(db, args=None):
    total = db.query("SELECT COUNT(*) AS n FROM leads")[0]["n"]
    no_site = db.query("SELECT COUNT(*) AS n FROM leads WHERE website = ''")[0]["n"]
    probed = db.query("SELECT COUNT(*) AS n FROM probes")[0]["n"]
    psi_done = db.query("SELECT COUNT(*) AS n FROM psi")[0]["n"]
    log(f"leads: {total}   sem site: {no_site}   auditados: {probed}   pagespeed: {psi_done}")
    for row in db.query("SELECT tier, COUNT(*) AS n FROM scores GROUP BY tier ORDER BY tier"):
        log(f"  tier {row['tier']}: {row['n']}")
    for row in db.query("""SELECT city, COUNT(*) AS n FROM leads
                           GROUP BY city ORDER BY n DESC"""):
        log(f"  {row['city']}: {row['n']}")


def cmd_web(db, args):
    from . import web as web_mod
    db.close()  # o servidor abre uma conexao por requisicao
    web_mod.serve(args.host, args.port, not args.no_browser)


def cmd_run(db, args):
    cmd_harvest(db, args)
    # Antes de auditar: descobrir o site de quem a OSM acha que nao tem.
    cmd_discover(db, argparse.Namespace(limit=5000, workers=10, refresh=False))
    cmd_probe(db, args)
    cmd_score(db, args)

    # PageSpeed usa limites proprios: e lento, entao so os finalistas entram.
    psi_args = argparse.Namespace(limit=args.psi_limit, min_score=args.psi_min_score,
                                  workers=4)
    cmd_psi(db, psi_args)

    cmd_score(db, args)
    cmd_export(db, args)
    log("")
    cmd_stats(db, args)


# ---------------------------------------------------------------- main

def main(argv=None):
    load_env()
    parser = argparse.ArgumentParser(prog="proofnbrand", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=None, help="caminho SQLite ou URL Postgres")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("harvest", help="colhe empresas da OpenStreetMap")
    p.add_argument("--city", help="roda so uma cidade")
    p.set_defaults(func=cmd_harvest)

    p = sub.add_parser("probe", help="auditoria HTTP dos sites (gratis)")
    p.add_argument("--limit", type=int, default=2000)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--refresh", action="store_true", help="reaudita quem ja foi checado")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("psi", help="PageSpeed nos finalistas")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--min-score", type=float, default=50.0)
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=cmd_psi)

    p = sub.add_parser("score", help="recalcula o score de todos")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("export", help="gera out/leads.csv e out/leads.md")
    p.add_argument("--min-score", type=float, default=40.0)
    p.add_argument("--top", type=int, default=60)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("stats", help="resumo do banco")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("discover", help="procura o site de quem a OSM diz nao ter")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--refresh", action="store_true", help="tenta de novo quem ja falhou")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("prune", help="apaga categorias desligadas, redes e orgaos publicos")
    p.add_argument("--dry-run", action="store_true", help="so mostra o que seria apagado")
    p.set_defaults(func=cmd_prune)

    p = sub.add_parser("web", help="abre o painel no navegador")
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("run", help="pipeline completo")
    p.add_argument("--city")
    p.add_argument("--limit", type=int, default=2000)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--min-score", type=float, default=40.0)
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--psi-limit", type=int, default=40, help="quantos finalistas vao ao PageSpeed")
    p.add_argument("--psi-min-score", type=float, default=50.0)
    p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)

    # 'run' reaproveita os args de varios subcomandos; preenche o que falta.
    for name, default in (("limit", 2000), ("workers", 12), ("refresh", False),
                          ("min_score", 40.0), ("top", 60), ("city", None)):
        if not hasattr(args, name):
            setattr(args, name, default)

    db = Database(args.db)
    try:
        args.func(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
