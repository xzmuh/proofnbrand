import { useEffect, useId, useRef, useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'

export interface Option {
  value: string
  label: string
  n?: number
  dot?: string
}

interface Props {
  label: string
  value: string
  options: Option[]
  onChange: (value: string) => void
  align?: 'left' | 'right'
  compact?: boolean
}

export function Dropdown({ label, value, options, onChange, align = 'left', compact }: Props) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const listId = useId()

  const chosen = options.find((o) => o.value === value) ?? options[0]

  useEffect(() => {
    if (!open) return
    setActive(Math.max(0, options.findIndex((o) => o.value === value)))

    const onDocDown = (ev: MouseEvent) => {
      if (!root.current?.contains(ev.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [open, options, value])

  const pick = (next: string) => {
    onChange(next)
    setOpen(false)
  }

  const onKeyDown = (ev: React.KeyboardEvent) => {
    if (!open) {
      if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'ArrowDown') {
        ev.preventDefault()
        setOpen(true)
      }
      return
    }
    if (ev.key === 'Escape') { ev.preventDefault(); setOpen(false) }
    else if (ev.key === 'ArrowDown') { ev.preventDefault(); setActive((i) => (i + 1) % options.length) }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); setActive((i) => (i - 1 + options.length) % options.length) }
    else if (ev.key === 'Home') { ev.preventDefault(); setActive(0) }
    else if (ev.key === 'End') { ev.preventDefault(); setActive(options.length - 1) }
    else if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(options[active].value) }
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onKeyDown}
        className={`inline-flex h-10 cursor-pointer items-center gap-2.5 rounded-full border bg-card pr-3.5 pl-4 font-medium whitespace-nowrap transition-colors duration-150 hover:bg-[#fafafa] ${
          open ? 'border-ink' : 'border-line-strong'
        }`}
      >
        {!compact && <span className="text-muted">{label}</span>}
        {chosen?.dot && (
          <span className="size-[7px] rounded-full" style={{ background: chosen.dot }} aria-hidden />
        )}
        <span className="font-semibold">{chosen?.label ?? '—'}</span>
        <ChevronDown
          size={13}
          strokeWidth={2.5}
          aria-hidden
          className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label={label}
          tabIndex={-1}
          className={`absolute top-[calc(100%+8px)] z-50 max-h-[340px] min-w-[220px] overflow-auto rounded-[18px] border border-line bg-card p-1.5 shadow-[0_12px_40px_rgba(20,20,20,0.14)] ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          {options.map((opt, i) => {
            const selected = opt.value === value
            return (
              <li key={opt.value} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(opt.value)}
                  className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3.5 py-2.5 text-left font-medium transition-colors duration-150 ${
                    selected ? 'bg-brand-wash font-semibold' : ''
                  } ${i === active && !selected ? 'bg-[#f6f6f6]' : ''}`}
                >
                  {opt.dot && (
                    <span className="size-[7px] shrink-0 rounded-full" style={{ background: opt.dot }} aria-hidden />
                  )}
                  <span className="flex-1 truncate">{opt.label}</span>
                  {opt.n != null && <span className="tnum text-xs text-muted">{opt.n}</span>}
                  {selected && <Check size={13} strokeWidth={3} aria-hidden />}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
