"""Algoritmo de score: quao vendavel e este lead.

score = OPORTUNIDADE (o site e ruim) + ALCANCE (da pra falar com ele) + VALOR (ele paga)

A ideia nao e achar o pior site do mundo: e achar o dono que TEM problema visivel,
TEM como ser contatado e TEM dinheiro pra resolver. Site horrivel de quiosque sem
telefone vale zero.
"""
import re
from datetime import datetime, timezone

# --- OPORTUNIDADE: o quanto o site atual e um problema (max ~70) ---
# Sinais exclusivos de "estado do site". So o maior deles conta, para nao somar
# 'site morto' com 'sem https' e estourar a nota.
STATE_SIGNALS = {
    # A busca automatica nao acha tudo (eurodenture.com nao sai de "European
    # Denture Center"), entao isto nunca vale tanto quanto um site ruim que
    # auditamos de verdade. Confirmado-ruim vem sempre antes de nao-encontrado.
    "no_site": (38, "Nenhum site encontrado (busca automática falhou)"),
    "site_unknown": (26, "Site não verificado — confira antes de abordar"),
    "social_only": (46, "Usa perfil social no lugar de site próprio"),
    "dns_fail": (44, "Domínio não resolve (site fora do ar)"),
    "site_down": (42, "Site não respondeu"),
    "timeout": (34, "Site demorou demais e estourou o tempo"),
    "parked_or_empty": (40, "Página vazia / em construção / domínio estacionado"),
    "site_error": (38, "Site devolve página de erro ao visitante"),
}

# Sinais acumulativos: cada um soma.
DEFECT_WEIGHTS = {
    "not_responsive": (20, "Não é responsivo (quebra no celular)"),
    "no_ssl": (16, "Sem HTTPS - Chrome mostra 'Not secure'"),
    "legacy_html": (12, "HTML dos anos 2000 (tabelas, <font>)"),
    "http_no_redirect": (6, "HTTP não redireciona para HTTPS"),
    "ancient_jquery": (6, "jQuery de 2013 ou mais velho"),
    "ancient_server": (5, "Servidor sem atualização há anos"),
    "mixed_content": (5, "Conteúdo misto quebra o cadeado"),
    "diy_builder": (8, "Template padrão de construtor (feito pelo dono)"),
    "very_slow_ttfb": (8, "Servidor muito lento (>1.5s)"),
    "slow_ttfb": (4, "Servidor lento (>0.8s)"),
    "bloated_html": (4, "HTML pesado demais"),
    "no_meta_description": (4, "Sem meta description (SEO)"),
    "no_schema_org": (4, "Sem dados estruturados (SEO local)"),
    "no_open_graph": (3, "Link feio quando compartilhado"),
    "no_title": (6, "Sem <title>"),
    "generic_title": (4, "Title genérico ('Home', 'Untitled')"),
    "no_favicon": (2, "Sem favicon"),
}
DEFECT_CAP = 42  # teto para a soma dos acumulativos

# --- ALCANCE: da pra chegar nessa pessoa? (max 21) ---
REACH_EMAIL = 8
REACH_PHONE = 6
REACH_WHATS = 5
REACH_HOURS = 2

# --- VALOR: ticket provavel do cliente (max 14) ---
VALUE_TIER = {"high": 14, "mid": 8, "low": 3}

TIERS = ((72, "A"), (58, "B"), (44, "C"))

# Angulos de abordagem, em ingles, prontos para o primeiro e-mail.
PITCH = {
    "no_site": "I went looking for {name} online and couldn't find a website - if you have one, "
               "it isn't showing up where your customers are searching",
    "site_unknown": "I had trouble finding a website for {name} - if you have one, "
                    "it isn't easy to find where your customers are looking",
    "social_only": "{name} sends customers to a social profile instead of a site you actually own",
    "dns_fail": "your domain didn't resolve when I checked it - the site is effectively offline",
    "site_down": "your website didn't load for me at all",
    "timeout": "your site took so long to load that my browser gave up",
    "parked_or_empty": "your domain currently shows a placeholder page, not a real site",
    "site_error": "your website answers with an error page instead of loading",
    "not_responsive": "your site doesn't adapt to phones, and most local searches happen on a phone",
    "no_ssl": "Chrome flags your site as 'Not secure' to every single visitor",
    "legacy_html": "your site is built on markup from the early 2000s",
    "diy_builder": "your site is running a stock template that looks like a hundred others",
    "stale_copyright": "your footer still reads (c) {year}",
    "very_slow_ttfb": "your server takes over a second and a half just to start answering",
    "psi_slow": "Google scores your mobile site {perf}/100 for speed",
    "no_schema_org": "you're missing the structured data Google uses to rank local businesses",
    "no_meta_description": "your pages have no meta description, so Google writes your search snippet for you",
}
PITCH_ORDER = (
    "no_site", "site_unknown", "social_only", "dns_fail", "site_down", "site_error", "parked_or_empty", "timeout",
    "psi_slow", "not_responsive", "no_ssl", "legacy_html", "stale_copyright",
    "diy_builder", "very_slow_ttfb", "no_schema_org", "no_meta_description",
)


def _stale_copyright(signals):
    for s in signals:
        if s.startswith("stale_copyright_"):
            return int(s.rsplit("_", 1)[1])
    return None


# Valores de "brand" que nao sao marca nenhuma, so descricao do sortimento.
GENERIC_BRANDS = {"multimarca", "multimarcas", "diversas", "varias", "independente"}


def is_chain(tags, name=""):
    """Concessionaria de montadora, franquia, rede: nao contrata freelancer.

    O site dela e decidido na matriz. O sinal confiavel e o wikidata da marca —
    so marca de verdade tem verbete. A tag `operator` NAO serve aqui: na OSM ela
    costuma trazer o nome do dono ("Wilson Dental", operator="Gregg A. Wilson"),
    que e exatamente o perfil que queremos, nao o que queremos descartar.
    """
    tags = tags or {}
    if tags.get("brand:wikidata") or tags.get("operator:wikidata"):
        return True
    brand = (tags.get("brand") or "").strip()
    if not brand or brand.lower() in GENERIC_BRANDS:
        return False
    return brand.lower() != (name or "").strip().lower()


RE_PUBLIC = re.compile(
    r"\b(unidade de sa[uú]de|posto de sa[uú]de|ubs|usf|caps|upa|prefeitura|"
    r"municipal|estadual|federal|secretaria|hospital universit[aá]rio|"
    r"minist[eé]rio|public health|city of|county)\b", re.I)


def is_public(tags, name=""):
    """Posto de saude, orgao publico, universidade: nao contrata site privado."""
    tags = tags or {}
    if (tags.get("operator:type") or "").lower() in ("government", "public"):
        return True
    if (tags.get("amenity") or "") in ("public_building", "townhall"):
        return True
    return bool(RE_PUBLIC.search(name or "")) or bool(RE_PUBLIC.search(tags.get("operator") or ""))


def contact_channels(lead, probe):
    """Por onde da para falar com esse negocio, hoje."""
    probe = probe or {}
    channels = []
    if (lead.get("phone") or "").strip():
        channels.append("telefone")
    if (lead.get("email") or "").strip() or probe.get("found_email"):
        channels.append("e-mail")
    if probe.get("found_whats"):
        channels.append("whatsapp")
    if not channels and probe.get("reachable"):
        # Sem telefone nem e-mail, mas o site abre: sobra o formulario de contato.
        channels.append("formulario do site")
    return channels


def score_lead(lead, probe, psi, value_tier="mid"):
    """Devolve dict com score, tier, lead_type, reasons (PT) e pitch (EN).

    Devolve None quando o lead nao vale a pena existir na lista: rede/franquia,
    ou ninguem com quem falar.
    """
    if is_chain(lead.get("tags"), lead.get("name", "")):
        return None
    if is_public(lead.get("tags"), lead.get("name", "")):
        return None
    channels = contact_channels(lead, probe)
    if not channels:
        return None

    reasons = []
    points = 0.0
    signals = list((probe or {}).get("signals") or [])
    has_site = bool((lead.get("website") or "").strip())

    if not has_site:
        # So afirmamos "sem site" depois que a busca por dominio rodou e falhou.
        signals.insert(0, "no_site" if lead.get("discovered_at") else "site_unknown")

    # --- oportunidade: estado do site (pega so o pior) ---
    state = None
    for name in STATE_SIGNALS:
        if name in signals:
            if state is None or STATE_SIGNALS[name][0] > STATE_SIGNALS[state][0]:
                state = name
    if state:
        weight, label = STATE_SIGNALS[state]
        points += weight
        reasons.append(label)

    lead_type = state or ("outdated" if signals else "ok")

    # --- oportunidade: defeitos acumulativos ---
    # Se o site nem carrega, nao faz sentido somar 'sem favicon'.
    if state not in ("no_site", "site_unknown", "social_only", "dns_fail",
                     "site_down", "timeout", "site_error"):
        defects = 0.0
        for name in signals:
            if name in DEFECT_WEIGHTS:
                weight, label = DEFECT_WEIGHTS[name]
                defects += weight
                reasons.append(label)
        year = _stale_copyright(signals)
        if year:
            age = datetime.now(timezone.utc).year - year
            bump = min(10, 2 * age)
            defects += bump
            reasons.append(f"Rodapé parado em {year} ({age} anos)")
        points += min(DEFECT_CAP, defects)

    # --- oportunidade: PageSpeed (substitui o palpite de lentidao) ---
    perf = (psi or {}).get("perf")
    if perf is not None:
        if perf < 30:
            points += 18
            reasons.append(f"PageSpeed mobile {int(perf)}/100 (crítico)")
        elif perf < 50:
            points += 12
            reasons.append(f"PageSpeed mobile {int(perf)}/100 (ruim)")
        elif perf < 70:
            points += 5
            reasons.append(f"PageSpeed mobile {int(perf)}/100")
        seo = (psi or {}).get("seo")
        if seo is not None and seo < 80:
            points += 6
            reasons.append(f"SEO técnico {int(seo)}/100")

    # --- alcance ---
    # Chegar ate aqui ja garante pelo menos um canal; o peso e sobre quantos.
    probe_data = probe or {}
    reach = 0
    if (lead.get("email") or "").strip() or probe_data.get("found_email"):
        reach += REACH_EMAIL
    if (lead.get("phone") or "").strip() or probe_data.get("found_phone"):
        reach += REACH_PHONE
    if probe_data.get("found_whats"):
        reach += REACH_WHATS
    if (lead.get("tags") or {}).get("opening_hours"):
        reach += REACH_HOURS
    points += reach
    reasons.append("Contato: " + ", ".join(channels))

    # --- valor ---
    points += VALUE_TIER.get(value_tier, 8)

    score = round(max(0.0, min(100.0, points)), 1)
    tier = next((t for cutoff, t in TIERS if score >= cutoff), "D")

    return {
        "score": score,
        "tier": tier,
        "lead_type": lead_type,
        "reasons": reasons,
        "pitch": build_pitch(lead, signals, psi),
    }


def build_pitch(lead, signals, psi):
    """Monta a frase de abertura do e-mail frio, em ingles."""
    perf = (psi or {}).get("perf")
    available = set(signals)
    if perf is not None and perf < 50:
        available.add("psi_slow")

    year = _stale_copyright(signals)
    if year:
        available.add("stale_copyright")

    picked = [s for s in PITCH_ORDER if s in available][:2]
    if not picked:
        return ""

    parts = []
    for name in picked:
        parts.append(
            PITCH[name].format(
                name=lead.get("name", "your business"),
                year=year or "",
                perf=int(perf) if perf is not None else "",
            )
        )
    return " - and ".join(parts) + "."
