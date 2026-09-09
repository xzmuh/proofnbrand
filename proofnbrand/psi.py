"""PageSpeed Insights (Lighthouse na nuvem do Google). Gratuito e sem cartao.

Sem chave a API funciona mas devolve 429 com frequencia. A chave e gratuita:
console.cloud.google.com > APIs e servicos > ativar "PageSpeed Insights API" > criar chave.
Nenhuma cobranca, nenhum billing account necessario.

Custo real: ~15-25s por site. Por isso so os finalistas passam por aqui.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = ("PERFORMANCE", "SEO", "ACCESSIBILITY", "BEST_PRACTICES")


def _blank(error=""):
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "perf": None, "seo": None, "a11y": None, "best": None,
        "lcp_ms": None, "cls": None, "tbt_ms": None, "error": error,
    }


def run_psi(url, api_key=None, strategy="mobile", retries=2):
    """Roda o Lighthouse mobile num site. Nunca levanta excecao."""
    api_key = api_key or os.environ.get("PSI_API_KEY") or ""
    params = [("url", url), ("strategy", strategy)]
    params += [("category", c) for c in CATEGORIES]
    if api_key:
        params.append(("key", api_key))

    last = "unknown"
    for attempt in range(retries + 1):
        try:
            resp = requests.get(ENDPOINT, params=params, timeout=120)
            if resp.status_code == 429:
                last = "rate_limited"
                time.sleep(20 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = resp.json().get("error", {}).get("message", "")[:120]
                except Exception:
                    pass
                return _blank(f"http_{resp.status_code}:{detail}")

            lh = resp.json().get("lighthouseResult", {})
            cats = lh.get("categories", {})
            audits = lh.get("audits", {})

            def cat(name):
                score = (cats.get(name) or {}).get("score")
                return round(score * 100, 1) if score is not None else None

            def num(name):
                return (audits.get(name) or {}).get("numericValue")

            out = _blank()
            out["perf"] = cat("performance")
            out["seo"] = cat("seo")
            out["a11y"] = cat("accessibility")
            out["best"] = cat("best-practices")
            out["lcp_ms"] = num("largest-contentful-paint")
            out["cls"] = num("cumulative-layout-shift")
            out["tbt_ms"] = num("total-blocking-time")
            return out
        except Exception as exc:
            last = "err_" + type(exc).__name__
            time.sleep(6 * (attempt + 1))

    return _blank(last)


def run_many(urls, api_key=None, workers=4, on_result=None):
    """PSI em paralelo, com folga para nao levar 429."""
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_psi, u, api_key): u for u in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                results[url] = fut.result()
            except Exception as exc:
                results[url] = _blank("crash_" + type(exc).__name__)
            if on_result:
                on_result(url, results[url])
    return results
