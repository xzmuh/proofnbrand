import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, FolderDown, RefreshCw, Search } from 'lucide-react'
import {
  exportByCategory, exportCsv, fetchLeads, fetchSummary, setStatus,
  type Filters, type Lead, type Status, type Summary,
} from './lib/api'
import { BROKEN_TYPES, catName } from './lib/labels'
import { Dropdown } from './components/Dropdown'
import { LeadTable } from './components/LeadTable'
import { Pagination } from './components/Pagination'

const QUICK = [
  { key: 'all',    label: 'Todos',          patch: {} },
  { key: 'hot',    label: 'Tier A + B',     patch: { min_score: '58' } },
  { key: 'nosite', label: 'Sem site',       patch: { lead_type: 'no_site' } },
  { key: 'broken', label: 'Site quebrado',  patch: { lead_type: BROKEN_TYPES.join(',') } },
  { key: 'social', label: 'Só rede social', patch: { lead_type: 'social_only' } },
  { key: 'todo',   label: 'Não contatados', patch: { status: 'novo' } },
] as const

const EMPTY: Filters = { city: 'all', category: 'all', status: 'all', lead_type: 'all', min_score: '', q: '' }

export default function App() {
  const [quick, setQuick] = useState<string>('all')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [search, setSearch] = useState('')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [leads, setLeads] = useState<Lead[]>([])
  const [total, setTotal] = useState(0)
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)

  const say = useCallback((message: string) => {
    setToast(message)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2800)
  }, [])

  // Busca é debounced para não disparar uma requisição por tecla.
  useEffect(() => {
    const id = window.setTimeout(() => {
      setFilters((f) => (f.q === search.trim() ? f : { ...f, q: search.trim() }))
      setOffset(0)
    }, 280)
    return () => window.clearTimeout(id)
  }, [search])

  /* Todo filtro volta para a página 1 no mesmo evento que muda o filtro.
     Resetar num efeito separado dispararia duas requisições. */
  const applyFilter = useCallback((patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }))
    setOffset(0)
  }, [])

  const effective = useMemo<Partial<Filters>>(() => {
    const patch = QUICK.find((q) => q.key === quick)?.patch ?? {}
    return { ...filters, ...patch }
  }, [filters, quick])

  const reload = useCallback(async () => {
    setBusy(true)
    try {
      const [nextSummary, page] = await Promise.all([
        fetchSummary(),
        fetchLeads(effective, limit, offset),
      ])
      setSummary(nextSummary)
      setLeads(page.leads)
      setTotal(page.total)
      // O servidor corrige um offset que caiu fora do fim; acompanha ele.
      if (page.offset !== offset) setOffset(page.offset)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }, [effective, limit, offset])

  useEffect(() => { void reload() }, [reload])

  const onStatusChange = async (leadId: string, status: Status) => {
    const previous = leads
    setLeads((rows) => rows.map((l) => (l.lead_id === leadId ? { ...l, status } : l)))
    try {
      await setStatus(leadId, status)
    } catch (err) {
      setLeads(previous) // desfaz o otimismo se o servidor recusar
      say('Não consegui salvar: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  const broken = useMemo(
    () => (summary?.lead_types ?? [])
      .filter((t) => (BROKEN_TYPES as string[]).includes(t.lead_type))
      .reduce((sum, t) => sum + t.n, 0),
    [summary],
  )

  const cityOptions = [{ value: 'all', label: 'Todas', n: summary?.total }]
    .concat((summary?.cities ?? []).map((c) => ({ value: c.city, label: `${c.city}, ${c.country}`, n: c.n })))
  const categoryOptions = [{ value: 'all', label: 'Todas', n: summary?.total }]
    .concat((summary?.categories ?? []).map((c) => ({ value: c.category, label: catName(c.category), n: c.n })))
  const statusOptions = [
    { value: 'all', label: 'Todos' }, { value: 'novo', label: 'Novo' },
    { value: 'contatado', label: 'Contatado' }, { value: 'respondeu', label: 'Respondeu' },
    { value: 'fechado', label: 'Fechado' }, { value: 'descartado', label: 'Descartado' },
  ]

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 flex items-center gap-3 border-b border-line bg-card px-5 py-3.5 sm:px-7">
        <div className="grid size-[34px] shrink-0 place-items-center rounded-[11px] bg-brand text-[15px] font-extrabold text-ink">
          P
        </div>
        <span className="font-display text-[15px] font-bold tracking-[-0.01em]">Proof ’n Brand</span>

        <div className="ml-auto flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => { void reload().then(() => say('Atualizado')) }}
            className="grid size-9 cursor-pointer place-items-center rounded-full border border-line bg-card transition-colors hover:border-line-strong hover:bg-[#fafafa]"
          >
            <RefreshCw size={15} className={busy ? 'animate-spin' : ''} aria-hidden />
            <span className="sr-only">Recarregar</span>
          </button>
          <button
            type="button"
            onClick={() => exportByCategory().then((r) => say(`${r.files.length} arquivos em out/por-categoria/`)).catch((e) => say('Erro: ' + e.message))}
            className="hidden cursor-pointer items-center gap-2 rounded-full border border-line-strong bg-card px-4 py-2 text-[13px] font-medium transition-colors hover:bg-[#fafafa] sm:inline-flex"
          >
            <FolderDown size={14} aria-hidden />Por categoria
          </button>
          <button
            type="button"
            onClick={() => exportCsv().then((r) => say(`${r.count} leads em out/leads.csv`)).catch((e) => say('Erro: ' + e.message))}
            className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-semibold text-white transition-transform duration-150 hover:-translate-y-px"
          >
            <Download size={14} aria-hidden />CSV
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-5 pt-6 pb-16 sm:px-7">
        <h1 className="font-display text-[27px] font-bold tracking-[-0.02em]">Leads</h1>
        <p className="mt-1 text-[13.5px] text-muted">
          {summary ? (
            <>
              <strong className="tnum font-semibold text-body">{summary.total}</strong> no banco ·{' '}
              <strong className="tnum font-semibold text-body">{summary.hot}</strong> tier A/B ·{' '}
              <strong className="tnum font-semibold text-body">{summary.no_site + broken}</strong> sem site ou quebrado ·{' '}
              <strong className="tnum font-semibold text-body">{total}</strong> neste filtro
            </>
          ) : (
            'Carregando…'
          )}
        </p>

        {error && (
          <div className="mt-4 rounded-[18px] border border-[#ffd0d0] bg-[#fff5f5] px-5 py-4 text-sm text-[#a02222]">
            <strong className="font-semibold">Não consegui falar com o servidor.</strong> {error}
            <br />
            <span className="text-[#c25c5c]">
              Rode: <code className="rounded bg-ink px-1.5 py-0.5 text-brand">python -m proofnbrand.cli web</code>
            </span>
          </div>
        )}

        {/* Uma linha de filtros acima de tudo que ela escopa. */}
        <section className="my-4 flex flex-wrap items-center gap-2.5 rounded-[26px] border border-line bg-card p-3.5">
          <div className="flex flex-wrap gap-1.5">
            {QUICK.map((q) => (
              <button
                key={q.key}
                type="button"
                onClick={() => { setQuick(q.key); setOffset(0) }}
                aria-pressed={quick === q.key}
                className={`cursor-pointer rounded-full border px-3.5 py-2 text-[13px] font-medium transition-colors duration-150 ${
                  quick === q.key ? 'border-brand bg-brand font-semibold' : 'border-line-strong hover:bg-[#fafafa]'
                }`}
              >
                {q.label}
              </button>
            ))}
          </div>

          <Dropdown label="Cidade" value={filters.city} options={cityOptions}
                    onChange={(v) => applyFilter({ city: v })} />
          <Dropdown label="Categoria" value={filters.category} options={categoryOptions}
                    onChange={(v) => applyFilter({ category: v })} />
          <Dropdown label="Status" value={filters.status} options={statusOptions}
                    onChange={(v) => applyFilter({ status: v })} />

          <label className="flex h-10 min-w-[200px] flex-1 items-center gap-2 rounded-full border border-line-strong bg-card px-4 focus-within:border-ink">
            <Search size={15} className="shrink-0 text-muted" aria-hidden />
            <input
              type="search"
              value={search}
              onChange={(ev) => setSearch(ev.target.value)}
              placeholder="Buscar por nome ou domínio…"
              className="w-full flex-1 bg-transparent outline-none"
              aria-label="Buscar leads"
            />
          </label>
        </section>

        {/* No refetch o render anterior fica atenuado — sem flash, sem pulo. */}
        <div className={busy ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          {leads.length === 0 && !busy ? (
            <div className="rounded-[26px] border border-dashed border-line-strong bg-card px-6 py-16 text-center">
              <h2 className="text-[17px] font-semibold">
                {summary?.total ? 'Nenhum lead com esses filtros' : 'Banco vazio'}
              </h2>
              <p className="mt-1.5 text-muted">
                {summary?.total ? 'Afrouxe os filtros ou colha mais cidades.' : 'Rode o motor para colher e auditar negócios.'}
              </p>
              {!summary?.total && (
                <code className="mt-3.5 inline-block rounded-xl bg-ink px-4 py-2.5 font-mono text-[12.5px] text-brand">
                  python -m proofnbrand.cli run
                </code>
              )}
            </div>
          ) : (
            <>
              <LeadTable leads={leads} onStatusChange={onStatusChange} />
              <Pagination
                total={total}
                limit={limit}
                offset={offset}
                onOffset={(next) => {
                  setOffset(next)
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                onLimit={(next) => { setLimit(next); setOffset(0) }}
              />
            </>
          )}
        </div>
      </main>

      <div
        role="status"
        aria-live="polite"
        className={`fixed bottom-6 left-1/2 z-90 -translate-x-1/2 rounded-full bg-ink px-5 py-3 font-medium text-white shadow-[0_12px_40px_rgba(20,20,20,0.24)] transition-all duration-200 ${
          toast ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-5 opacity-0'
        }`}
      >
        {toast}
      </div>
    </div>
  )
}
