/* Cliente da API Python (proofnbrand/web.py). */

export type Tier = 'A' | 'B' | 'C' | 'D'

export type LeadType =
  | 'no_site' | 'social_only' | 'dns_fail' | 'site_down'
  | 'site_error' | 'parked_or_empty' | 'timeout' | 'outdated' | 'ok'
  | 'site_unknown'

export type Status = 'novo' | 'contatado' | 'respondeu' | 'fechado' | 'descartado'

export interface Lead {
  lead_id: string
  name: string
  score: number
  tier: Tier
  lead_type: LeadType
  reasons: string[]
  pitch: string
  category: string
  city: string
  country: string
  currency: string | null
  website: string | null
  website_source: string | null
  discovered_at: string | null
  final_url: string | null
  phone: string | null
  email: string | null
  address: string | null
  platform: string | null
  responsive: number | null
  https: number | null
  copyright_year: number | null
  status_code: number | null
  ttfb_ms: number | null
  found_email: string | null
  found_phone: string | null
  found_whats: string | null
  psi_perf: number | null
  psi_seo: number | null
  status: Status
  notes: string | null
  maps_url: string
}

export interface Summary {
  total: number
  scored: number
  no_site: number
  hot: number
  avg_score: number
  probed: number
  psi: number
  tiers: { tier: Tier; n: number }[]
  cities: { city: string; country: string; n: number; hot: number }[]
  categories: { category: string; n: number; avg_score: number | null; hot: number }[]
  lead_types: { lead_type: LeadType; n: number }[]
  statuses: { status: Status; n: number }[]
}

export interface Filters {
  city: string
  category: string
  status: string
  lead_type: string
  min_score: string
  q: string
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(path)
  if (!resp.ok) throw new Error(`${resp.status} em ${path}`)
  const data = await resp.json()
  if (data && typeof data === 'object' && 'error' in data && data.error) {
    throw new Error(String(data.error))
  }
  return data as T
}

export function fetchSummary() {
  return get<Summary>('/api/summary')
}

export interface LeadPage {
  leads: Lead[]
  total: number
  limit: number
  offset: number
}

export const PAGE_SIZES = [25, 50, 100, 200] as const

export function fetchLeads(filters: Partial<Filters>, limit: number, offset: number) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  for (const [key, value] of Object.entries(filters)) {
    if (value && value !== 'all') params.set(key, value)
  }
  return get<LeadPage>('/api/leads?' + params)
}

export async function setStatus(leadId: string, status: Status) {
  const resp = await fetch('/api/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lead_id: leadId, status }),
  })
  const data = await resp.json()
  if (data.error) throw new Error(data.error)
  return data as { ok: true; lead_id: string; status: Status }
}

export function exportCsv() {
  return get<{ count: number; csv: string; md: string }>('/api/export')
}

export function exportByCategory() {
  return get<{ files: { category: string; count: number }[]; dir: string }>(
    '/api/export-by-category',
  )
}
