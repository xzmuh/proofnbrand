# Proof ’n Brand

Encontra negócios cujo site está ruim, quebrado ou não existe — nos EUA, na zona do
euro e no Brasil — e entrega, para cada um, **o ângulo de venda pronto**.

Custo de operação: **US$ 0**. Nenhuma API deste projeto pede cartão de crédito.

```
harvest          probe            score         psi              export
OpenStreetMap →  GET no HTML   →  nota 0-100 →  PageSpeed nos →  CSV + Markdown
(Overpass)       (heurísticas)     + pitch      ~40 finalistas   + painel web
```

---

## Começar

```bash
pip install -r requirements.txt
python -m proofnbrand.cli run     # pipeline completo
python -m proofnbrand.cli web     # abre o painel em localhost:8787
```

O primeiro `run` leva ~20-40 min com o config de fábrica (6 cidades × 6 categorias),
quase tudo esperando o Overpass. Os comandos são idempotentes: rodar de novo só
colhe o que mudou e audita quem ainda não foi auditado.

---

## Comandos

| Comando | O que faz |
|---|---|
| `run` | pipeline inteiro, ponta a ponta |
| `harvest` | colhe empresas da OpenStreetMap (`--city Boise` para uma só) |
| `probe` | auditoria HTTP dos sites (`--refresh` reaudita tudo) |
| `score` | recalcula as notas |
| `psi` | PageSpeed nos finalistas (`--limit`, `--min-score`) |
| `export` | gera `out/leads.csv` e `out/leads.md` |
| `web` | painel no navegador (porta 8787) |
| `stats` | resumo do banco |

---

## Como o score funciona

`score = OPORTUNIDADE + ALCANCE + VALOR`, teto em 100.

**Oportunidade** — o site é um problema. Um sinal de *estado* (o pior deles conta sozinho):

| Estado | Peso |
|---|---|
| Não tem site | 48 |
| Só rede social (Facebook no lugar de site) | 46 |
| Domínio não resolve | 44 |
| Site fora do ar | 42 |
| Página vazia / em construção | 40 |
| Site devolve erro ao visitante (401, 403, 500…) | 38 |
| Site trava e estoura o tempo | 34 |

Mais defeitos acumulativos (teto 42): não responsivo (20), sem HTTPS (16),
HTML dos anos 2000 (12), template de construtor (8), servidor lento (8),
rodapé desatualizado (2/ano), lacunas de SEO (2-6 cada).
Quando há PageSpeed, ele soma até 18 e substitui o palpite de lentidão.

**Alcance** (até 16) — e-mail público 8, telefone 6, horário de funcionamento 2.
*Sem nenhum contato o score é cortado em 55%*: lead que você não consegue abordar não vale nada.

**Valor** (até 14) — categorias de ticket alto (dentista, advogado, empreiteiro,
imobiliária, veterinário) valem 14; médio (restaurante, salão, academia) vale 8.

**Tiers:** A ≥ 72 · B ≥ 58 · C ≥ 44 · D abaixo disso.

---

## Configuração

`config/targets.json` controla tudo. `enabled: false` desliga uma cidade sem apagá-la;
`enabled_categories` escolhe os nichos.

Semente de fábrica: **EUA** (Tampa, Sarasota, Charlotte, Boise), **zona do euro**
(Dublin, Amsterdã) e **Brasil** (Curitiba, Florianópolis), com Lisboa, Porto, Valência,
Milão, Goiânia, Campinas, Porto Alegre e BH prontos para ligar.

> São Paulo e Rio ficam desligados por padrão: a bounding box é enorme e o Overpass
> costuma estourar o timeout. Rode `--city "Sao Paulo"` sozinho se quiser.

**Brasil não é o mesmo jogo.** Ticket em BRL é 3-5x menor que em USD, mas a taxa de
fechamento é muito maior: mesma língua, mesmo fuso, dá pra fazer call e o WhatsApp
funciona de verdade (nos EUA quase nenhum negócio local usa). A LGPD trata contato
comercial publicado como legítimo interesse, mas WhatsApp frio irrita e derruba número
— prefira e-mail ou ligação. O uso mais inteligente do Brasil aqui é montar portfólio
e prova social rápido, que é justamente o que falta pra fechar gringo.

> **Alemanha e Áustria ficam de fora de propósito.** São as jurisdições mais duras
> do mundo para e-mail frio B2B (UWG + GDPR — lá o padrão é opt-in prévio). Os EUA
> seguem CAN-SPAM, bem mais permissivo: basta identificar-se, dar opt-out real e
> incluir um endereço físico. Irlanda e Holanda ficam no meio-termo, com legítimo
> interesse B2B geralmente aceito. Ligue Alemanha só quando tiver um processo de opt-in.

---

## Variáveis de ambiente

Copie `.env.example` para `.env`. Tudo é opcional.

| Variável | Para quê |
|---|---|
| `PSI_API_KEY` | PageSpeed sem tomar 429. Chave gratuita, **não precisa de cartão**: Google Cloud Console → ativar "PageSpeed Insights API" → criar chave |
| `PNB_DB_URL` | vazio = SQLite local. Cole a string do Neon para migrar (`pip install 'psycopg[binary]'`) |
| `PNB_UA` | User-Agent enviado ao Nominatim/Overpass. Coloque seu e-mail — é boa prática e evita bloqueio |

---

## Painel

```bash
python -m proofnbrand.cli web        # localhost:8787 — serve o painel já compilado
```

Para mexer no visual, com hot reload:

```bash
python -m proofnbrand.cli web --no-browser   # backend numa aba
cd app && npm run dev                      # front noutra → localhost:5173
```

O `npm run build` gera `web/dist`, que o `web.py` passa a servir sozinho.

**Stack:** React 19 + Vite + Tailwind v4 + Recharts + Lucide, em `app/`.

**O que tem:** KPIs com meters, filtros rápidos (*Sem site*, *Site quebrado*,
*Tier A+B*, *Não contatados*), dropdowns navegáveis por teclado, leads agrupados
por categoria, ângulo de venda com botão de copiar, status por lead gravado no
banco, e **Salvar por categoria** (um CSV por nicho em `out/por-categoria/`).

### Decisões de design que não são gosto

O acento lime `#C6F73E` é **cor de marca, nunca cor de dado**: ele tem 1.09:1
contra branco, ou seja, é ilegível como preenchimento. Então:

- **Distribuição de score** usa uma rampa ordinal de um hue só, mais escuro =
  score mais alto — validada (L monotônica, gaps ≥ 0.06, ponta clara 2.12:1).
- **Composição da base** é barra empilhada, não rosca: rosca só funciona com
  poucas fatias e valores distantes, e aqui é o contrário. Usa a paleta
  categórica validada para daltonismo (ΔE 9.1 protanopia / 19.6 visão normal).
  Três slots ficam abaixo de 3:1, então cada fatia carrega rótulo e número
  visíveis — cor nunca é a única pista.
- **Leads por categoria** usa uma cor só para todas as barras. Categorias são
  nominais; colorir por valor gastaria o canal de identidade re-codificando o
  que o comprimento da barra já mostra.
- Não há sparkline nos KPIs porque o banco não guarda série temporal. Uma linha
  inventada seria decoração mentindo sobre os dados; virou meter.

Testado sem scroll horizontal em 390, 768, 1024 e 1440px.

### Fallback sem Node

Existe um painel em HTML/CSS/JS puro em `web/` (sem build). Se `web/dist` não
existir, o `web.py` serve esse. Útil em máquina sem Node.

## Automação

`.github/workflows/harvest.yml` roda a colheita todo dia às 03:10 (Brasília),
guarda o banco no cache entre execuções, publica `out/` como artefato e commita
o CSV. Grátis: ilimitado em repositório público, 2.000 min/mês no privado —
este pipeline usa uns 100.

Configure o secret `PSI_API_KEY` (e `PNB_DB_URL`, se migrar para o Neon).

---

## Limites que valem conhecer

**"Sem site" quer dizer "sem site no OpenStreetMap".** O OSM não é um cadastro
completo de empresas — muita gente tem site sem que o OSM saiba. Por isso o
ângulo desses leads é escrito de forma honesta: *"fui procurar e não achei um
site — se você tem um, ele não está aparecendo onde seus clientes procuram"*.
É verdadeiro nos dois casos e continua sendo um gancho forte. **Confira o site
antes de mandar o e-mail.**

**O probe lê só o HTML inicial.** Um site 100% renderizado por JavaScript pode
ser marcado como vazio. O sinal `parked_or_empty` merece uma olhada manual.

**Gerar lead não é o gargalo.** O Overpass entrega dezenas de milhares numa
tarde. O que trava a venda é entregabilidade de e-mail, portfólio e prova social.
O valor real deste projeto é trocar o e-mail frio genérico por *"olhei o SEU site
e ele tem ESTE problema"* — o que muda a taxa de resposta de ~1% para ~5-10%.
