"""Exporta os leads pontuados: CSV para trabalhar e Markdown para ler."""
import csv
import json
import os
from datetime import datetime, timezone

COLUMNS = [
    "score", "tier", "lead_type", "name", "category", "city", "country", "currency",
    "website", "final_url", "phone", "email", "address", "psi_perf", "psi_seo",
    "platform", "responsive", "https", "copyright_year", "pitch", "reasons",
    "maps_url", "lead_id",
]

QUERY = """
SELECT s.score, s.tier, s.lead_type, s.reasons, s.pitch,
       l.id AS lead_id, l.name, l.category, l.city, l.country, l.currency,
       l.website, l.phone, l.email, l.address, l.lat, l.lon,
       p.final_url, p.platform, p.responsive, p.https, p.copyright_year,
       x.perf AS psi_perf, x.seo AS psi_seo
FROM scores s
JOIN leads l ON l.id = s.lead_id
LEFT JOIN probes p ON p.lead_id = s.lead_id
LEFT JOIN psi x ON x.lead_id = s.lead_id
WHERE s.score >= ?
ORDER BY s.score DESC
LIMIT ?
"""


def fetch_ranked(db, min_score=0, limit=100000):
    rows = db.query(QUERY, (min_score, limit))
    for row in rows:
        row["reasons"] = json.loads(row["reasons"]) if row.get("reasons") else []
        row["maps_url"] = (
            f"https://www.google.com/maps/search/?api=1&query={row['lat']},{row['lon']}"
            if row.get("lat") else ""
        )
    return rows


def to_csv(rows, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["reasons"] = " | ".join(row["reasons"])
            writer.writerow(out)
    return path


TYPE_LABEL = {
    "no_site": "SEM SITE",
    "social_only": "SÓ REDE SOCIAL",
    "dns_fail": "DOMÍNIO MORTO",
    "site_down": "SITE FORA DO AR",
    "site_error": "SITE COM ERRO",
    "timeout": "SITE TRAVANDO",
    "parked_or_empty": "PÁGINA VAZIA",
    "outdated": "SITE DESATUALIZADO",
    "ok": "SITE OK",
}


def to_markdown(rows, path, top=60):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Leads - proof-n-brand",
        "",
        f"Gerado em {now}  |  {len(rows)} leads pontuados  |  mostrando os {min(top, len(rows))} melhores",
        "",
        "Tier A = ataca hoje. Tier B = fila. C/D = so se sobrar tempo.",
        "",
    ]

    for row in rows[:top]:
        flag = {"US": "USD", "IE": "EUR", "NL": "EUR", "PT": "EUR", "ES": "EUR", "IT": "EUR"}
        cur = row.get("currency") or flag.get(row.get("country"), "")
        site = row.get("website") or "(nenhum)"

        lines.append(f"### {row['score']:.0f} · [{row['tier']}] {row['name']}")
        lines.append(
            f"`{TYPE_LABEL.get(row['lead_type'], row['lead_type'])}` · "
            f"{row['category']} · {row['city']}, {row['country']} · {cur}"
        )
        lines.append("")
        lines.append(f"- **Site:** {site}")
        if row.get("phone"):
            lines.append(f"- **Tel:** {row['phone']}")
        if row.get("email"):
            lines.append(f"- **E-mail:** {row['email']}")
        if row.get("psi_perf") is not None:
            lines.append(f"- **PageSpeed mobile:** {row['psi_perf']:.0f}/100")
        if row.get("reasons"):
            lines.append("- **Problemas:** " + "; ".join(row["reasons"][:6]))
        if row.get("pitch"):
            lines.append(f"- **Angulo (EN):** _{row['pitch']}_")
        if row.get("maps_url"):
            lines.append(f"- [Ver no mapa]({row['maps_url']})")
        lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path
