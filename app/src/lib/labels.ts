import type { LeadType, Status, Tier } from './api'

export const CATEGORY_LABEL: Record<string, string> = {
  dentist: 'Odontologia', estetica: 'Estética/Beleza', clinic: 'Clínicas',
  architect: 'Arquitetura', photographer: 'Fotografia', veterinary: 'Veterinária',
  physio: 'Fisioterapia', tattoo: 'Tatuagem', salon: 'Salão/Barbearia',
  gym: 'Academia', hotel: 'Hotéis', lawyer: 'Advocacia',
  accountant: 'Contabilidade', estate_agent: 'Imobiliárias',
  restaurant: 'Restaurantes', car_repair: 'Oficinas',
}

export const catName = (key: string) => CATEGORY_LABEL[key] ?? key ?? 'sem categoria'

/* Estado do site. `tone` alimenta o badge — nunca é a única pista:
   o texto do rótulo carrega o significado sozinho. */
export const TYPE_LABEL: Record<LeadType, { text: string; tone: 'critical' | 'warning' | 'neutral' }> = {
  no_site:         { text: 'SEM SITE',        tone: 'critical' },
  site_unknown:    { text: 'NÃO VERIFICADO',  tone: 'warning'  },
  social_only:     { text: 'SÓ REDE SOCIAL',  tone: 'critical' },
  dns_fail:        { text: 'DOMÍNIO MORTO',   tone: 'critical' },
  site_down:       { text: 'FORA DO AR',      tone: 'critical' },
  site_error:      { text: 'SITE COM ERRO',   tone: 'critical' },
  parked_or_empty: { text: 'PÁGINA VAZIA',    tone: 'critical' },
  timeout:         { text: 'SITE TRAVANDO',   tone: 'warning'  },
  outdated:        { text: 'DESATUALIZADO',   tone: 'warning'  },
  ok:              { text: 'SITE OK',         tone: 'neutral'  },
}

export const STATUS_LABEL: Record<Status, string> = {
  novo: 'Novo', contatado: 'Contatado', respondeu: 'Respondeu',
  fechado: 'Fechado', descartado: 'Descartado',
}

export const STATUS_DOT: Record<Status, string> = {
  novo: 'var(--color-muted-soft)',
  contatado: 'var(--color-warning)',
  respondeu: 'var(--color-series-1)',
  fechado: 'var(--color-good)',
  descartado: 'var(--color-critical)',
}

/* Tipos que significam "o site existe mas não entrega nada ao visitante".
   Vale tanto quanto não ter site — é o mesmo argumento de venda. */
export const BROKEN_TYPES: LeadType[] = [
  'site_down', 'dns_fail', 'site_error', 'parked_or_empty', 'timeout',
]

/* Rampa ordinal validada (--ordinal PASS). Mais escuro = score mais alto. */
export const TIER_COLOR: Record<Tier, string> = {
  D: 'var(--color-tier-d)',
  C: 'var(--color-tier-c)',
  B: 'var(--color-tier-b)',
  A: 'var(--color-tier-a)',
}

/* Composição da base: 5 fatias, slots categóricos 1–5 documentados.
   Ordem fixa e ligada à entidade — filtrar não repinta os sobreviventes. */
export const COMPOSITION = [
  { key: 'no_site',  label: 'Sem site',        color: 'var(--color-series-1)' },
  { key: 'broken',   label: 'Site quebrado',   color: 'var(--color-series-2)' },
  { key: 'social',   label: 'Só rede social',  color: 'var(--color-series-3)' },
  { key: 'outdated', label: 'Desatualizado',   color: 'var(--color-series-4)' },
  { key: 'ok',       label: 'Site OK',         color: 'var(--color-series-5)' },
] as const

export function compositionBucket(type: LeadType): string {
  if (type === 'no_site') return 'no_site'
  if (type === 'social_only') return 'social'
  if (BROKEN_TYPES.includes(type)) return 'broken'
  if (type === 'ok') return 'ok'
  return 'outdated'
}

/* Busca manual: 2 segundos para confirmar antes de abordar. A OSM erra, e
   afirmar "você não tem site" para quem tem queima o lead na primeira frase. */
export const googleSearch = (name: string, city: string) =>
  'https://www.google.com/search?q=' + encodeURIComponent(`"${name}" ${city}`)

export const hostOf = (url: string | null) =>
  (url ?? '').replace(/^https?:\/\//, '').replace(/\/$/, '')
