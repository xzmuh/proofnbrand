# Proof 'n Brand

Encontra negócios com site ruim, quebrado ou inexistente e entrega o ângulo de
venda pronto. Nenhuma API usada pede cartão de crédito.

```bash
pip install -r requirements.txt
python -m proofnbrand.cli run     # pipeline completo
python -m proofnbrand.cli web     # painel em localhost:8787
```

| Comando | O que faz |
|---|---|
| `harvest` | colhe empresas da OpenStreetMap |
| `discover` | procura o site de quem a OSM diz não ter |
| `probe` | auditoria HTTP dos sites |
| `score` | calcula as notas |
| `psi` | PageSpeed nos finalistas |
| `export` | gera `out/leads.csv` e `out/leads.md` |
| `prune` | apaga categorias desligadas, redes e órgãos públicos |
| `web` | painel no navegador |
| `stats` | resumo do banco |

Alvos em `config/targets.json`. Variáveis opcionais em `.env.example`.
Front em `app/` (React + Vite): `npm run build` gera `web/dist`.

Os leads coletados não são versionados — contato de empresa real não vira
histórico público.
