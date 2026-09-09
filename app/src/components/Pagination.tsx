import { ChevronLeft, ChevronRight } from 'lucide-react'
import { PAGE_SIZES } from '../lib/api'
import { Dropdown } from './Dropdown'

/* Janela de páginas com reticências: sempre mostra a primeira, a última,
   a atual e uma vizinha de cada lado. Evita uma régua de 40 botões. */
function pageWindow(current: number, last: number): (number | '…')[] {
  if (last <= 7) return Array.from({ length: last }, (_, i) => i + 1)

  const out: (number | '…')[] = [1]
  const from = Math.max(2, current - 1)
  const to = Math.min(last - 1, current + 1)

  if (from > 2) out.push('…')
  for (let p = from; p <= to; p++) out.push(p)
  if (to < last - 1) out.push('…')
  out.push(last)
  return out
}

interface Props {
  total: number
  limit: number
  offset: number
  onOffset: (offset: number) => void
  onLimit: (limit: number) => void
}

export function Pagination({ total, limit, offset, onOffset, onLimit }: Props) {
  const last = Math.max(1, Math.ceil(total / limit))
  const current = Math.floor(offset / limit) + 1
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)

  const go = (page: number) => onOffset((Math.min(last, Math.max(1, page)) - 1) * limit)

  const arrow =
    'grid size-9 place-items-center rounded-full border border-line-strong transition-colors duration-150 ' +
    'enabled:cursor-pointer enabled:hover:border-ink enabled:hover:bg-[#fafafa] ' +
    'disabled:cursor-default disabled:border-line disabled:text-[#d2d2d2]'

  return (
    <nav
      className="mt-3.5 flex flex-wrap items-center gap-3 rounded-[26px] border border-line bg-card px-4 py-3"
      aria-label="Paginação dos leads"
    >
      <p className="text-[13px] text-muted">
        <strong className="tnum font-semibold text-body">{from}–{to}</strong> de{' '}
        <strong className="tnum font-semibold text-body">{total}</strong>
      </p>

      <div className="flex items-center gap-2">
        <span className="text-[13px] text-muted">por página</span>
        <Dropdown
          label="Por página"
          value={String(limit)}
          compact
          options={PAGE_SIZES.map((n) => ({ value: String(n), label: String(n) }))}
          onChange={(v) => onLimit(Number(v))}
        />
      </div>

      <div className="flex w-full flex-wrap items-center justify-center gap-1.5 sm:ml-auto sm:w-auto sm:justify-end">
        <button
          type="button"
          className={arrow}
          onClick={() => go(current - 1)}
          disabled={current <= 1}
          aria-label="Página anterior"
        >
          <ChevronLeft size={16} aria-hidden />
        </button>

        {pageWindow(current, last).map((page, i) =>
          page === '…' ? (
            <span key={`gap-${i}`} className="px-1 text-muted" aria-hidden>…</span>
          ) : (
            <button
              key={page}
              type="button"
              onClick={() => go(page)}
              aria-label={`Página ${page}`}
              aria-current={page === current ? 'page' : undefined}
              className={`tnum h-9 min-w-9 cursor-pointer rounded-full px-2.5 text-[13px] font-semibold transition-colors duration-150 ${
                page === current
                  ? 'bg-ink text-white'
                  : 'border border-line-strong hover:bg-[#fafafa]'
              }`}
            >
              {page}
            </button>
          ),
        )}

        <button
          type="button"
          className={arrow}
          onClick={() => go(current + 1)}
          disabled={current >= last}
          aria-label="Próxima página"
        >
          <ChevronRight size={16} aria-hidden />
        </button>
      </div>
    </nav>
  )
}
