import { Fragment, useState } from 'react'
import {
  Check, ChevronDown, Copy, Globe, Mail, MapPin, MessageCircle, Phone, Search,
} from 'lucide-react'
import type { Lead, Status } from '../lib/api'
import { STATUS_DOT, STATUS_LABEL, TIER_COLOR, TYPE_LABEL, catName, googleSearch, hostOf } from '../lib/labels'
import { mailtoLink, telLink, whatsappLink } from '../lib/contact'
import { Dropdown } from './Dropdown'

const TIER_TEXT: Record<Lead['tier'], string> = {
  D: 'var(--color-ink)', C: 'var(--color-ink)', B: '#ffffff', A: '#ffffff',
}

const TONE_CLASS = {
  critical: 'bg-[#ffecec] text-[#c62f2f]',
  warning: 'bg-[#fff4e0] text-[#97650b]',
  neutral: 'bg-[#f2f2f2] text-[#5f5f5f]',
} as const

const STATUS_OPTIONS = (Object.keys(STATUS_LABEL) as Status[]).map((value) => ({
  value, label: STATUS_LABEL[value], dot: STATUS_DOT[value],
}))

/* Ação de contato: ícone + rótulo acessível, alvo de 36px com folga.
   Desabilitada vira cinza em vez de sumir, para as linhas não "dançarem". */
function Action({
  href, label, children, tone = 'default',
}: {
  href: string | null
  label: string
  children: React.ReactNode
  tone?: 'default' | 'whatsapp'
}) {
  if (!href) {
    return (
      <span
        className="grid size-9 place-items-center rounded-full border border-line text-[#d2d2d2]"
        title={`${label} indisponível`}
        aria-hidden
      >
        {children}
      </span>
    )
  }
  return (
    <a
      href={href}
      target={href.startsWith('http') ? '_blank' : undefined}
      rel="noopener noreferrer"
      title={label}
      className={`grid size-9 cursor-pointer place-items-center rounded-full border transition-colors duration-150 ${
        tone === 'whatsapp'
          ? 'border-[#c9ecd5] text-[#1f9d52] hover:border-[#25d366] hover:bg-[#eafaf0]'
          : 'border-line-strong text-muted hover:border-ink hover:bg-[#fafafa] hover:text-ink'
      }`}
    >
      {children}
      <span className="sr-only">{label}</span>
    </a>
  )
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text)
        setDone(true)
        setTimeout(() => setDone(false), 1600)
      }}
      className="inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-ink px-3 py-1.5 text-xs font-semibold text-white transition-transform duration-150 hover:-translate-y-px"
    >
      {done ? <Check size={12} aria-hidden /> : <Copy size={12} aria-hidden />}
      {done ? 'Copiado' : label}
    </button>
  )
}

export function LeadTable({
  leads, onStatusChange,
}: {
  leads: Lead[]
  onStatusChange: (leadId: string, status: Status) => void
}) {
  const [open, setOpen] = useState<string | null>(null)

  return (
    <div className="overflow-x-auto rounded-[26px] border border-line bg-card">
      <table className="w-full min-w-[840px] border-collapse">
        <caption className="sr-only">
          Leads ordenados por score, com contato e estado do site
        </caption>
        <thead>
          <tr className="border-b border-line text-left text-[11px] tracking-[0.06em] text-muted uppercase">
            <th scope="col" className="py-3 pr-2 pl-5 font-semibold">Score</th>
            <th scope="col" className="px-2 py-3 font-semibold">Empresa</th>
            <th scope="col" className="px-2 py-3 font-semibold">Problema</th>
            <th scope="col" className="hidden px-2 py-3 font-semibold lg:table-cell">Local</th>
            <th scope="col" className="px-2 py-3 font-semibold">Contato</th>
            <th scope="col" className="px-2 py-3 font-semibold">Status</th>
            <th scope="col" className="w-10 py-3 pr-4 pl-2" />
          </tr>
        </thead>

        <tbody>
          {leads.map((lead) => {
            const type = TYPE_LABEL[lead.lead_type] ?? { text: lead.lead_type, tone: 'neutral' as const }
            const site = lead.website ?? ''
            const host = hostOf(site)
            // Contato da OSM, com o que o probe achou no site como reserva.
            const email = lead.email || lead.found_email || null
            const phone = lead.phone || lead.found_phone || null
            const whats = lead.found_whats
              ? `https://wa.me/${lead.found_whats}`
              : whatsappLink(phone, lead.country)
            const expanded = open === lead.lead_id
            const dimmed = lead.status === 'fechado' || lead.status === 'descartado'

            return (
              <Fragment key={lead.lead_id}>
                <tr
                  className={`border-b border-[#f4f4f4] transition-colors duration-150 hover:bg-[#fafafa] ${
                    expanded ? 'bg-[#fafafa]' : ''
                  } ${dimmed ? 'opacity-55' : ''}`}
                >
                  <td className="py-3 pr-2 pl-5">
                    <span
                      className="grid size-11 place-content-center justify-items-center rounded-[14px]"
                      style={{ background: TIER_COLOR[lead.tier], color: TIER_TEXT[lead.tier] }}
                      title={`Tier ${lead.tier}`}
                    >
                      <span className="hero-num text-[15px] font-extrabold">{Math.round(lead.score)}</span>
                      <span className="text-[8px] font-bold tracking-[0.1em] opacity-75">{lead.tier}</span>
                    </span>
                  </td>

                  <td className="max-w-[300px] px-2 py-3">
                    <div className="truncate text-[14.5px] font-semibold" title={lead.name}>
                      {lead.name}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-muted">
                      {host ? (
                        <>
                          <a href={site} target="_blank" rel="noopener noreferrer"
                             className="text-[#3e63dd] hover:underline" title={site}>
                            {host}
                          </a>
                          {lead.website_source === 'descoberto' && (
                            <span className="ml-1.5 rounded bg-brand-wash px-1.5 py-px text-[10px] font-semibold text-[#5a7010]"
                                  title="A OSM não tinha este site; nós encontramos e confirmamos">
                              achado
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="font-medium text-[#c62f2f]">
                          {lead.discovered_at ? 'site não encontrado' : 'site não verificado'}
                        </span>
                      )}
                      <span className="mx-1.5 text-[#d5d5d5]">·</span>
                      {catName(lead.category)}
                    </div>
                  </td>

                  <td className="px-2 py-3">
                    <span className={`inline-block rounded-full px-2.5 py-1 text-[10.5px] font-bold tracking-[0.03em] whitespace-nowrap ${TONE_CLASS[type.tone]}`}>
                      {type.text}
                    </span>
                    {lead.psi_perf != null && (
                      <span className="tnum ml-1.5 inline-block rounded-full bg-[#f2f2f2] px-2 py-1 text-[10.5px] font-bold text-[#5f5f5f]">
                        PSI {Math.round(lead.psi_perf)}
                      </span>
                    )}
                  </td>

                  <td className="hidden px-2 py-3 text-[13px] whitespace-nowrap text-muted lg:table-cell">
                    {lead.city}, {lead.country}
                    {lead.currency && <span className="ml-1.5 text-[#b8b8b8]">{lead.currency}</span>}
                  </td>

                  <td className="px-2 py-3">
                    <div className="flex items-center gap-1.5">
                      <Action href={site || null} label="Abrir site">
                        <Globe size={15} aria-hidden />
                      </Action>
                      <Action href={whats} label="WhatsApp" tone="whatsapp">
                        <MessageCircle size={15} aria-hidden />
                      </Action>
                      <Action href={mailtoLink(email, lead.name, lead.pitch)} label="Enviar e-mail">
                        <Mail size={15} aria-hidden />
                      </Action>
                      <Action href={telLink(phone)} label={phone ? `Ligar para ${phone}` : 'Ligar'}>
                        <Phone size={15} aria-hidden />
                      </Action>
                      <Action href={lead.maps_url || null} label="Ver no mapa">
                        <MapPin size={15} aria-hidden />
                      </Action>
                      <Action
                        href={googleSearch(lead.name, lead.city)}
                        label="Buscar no Google (confira antes de abordar)"
                      >
                        <Search size={15} aria-hidden />
                      </Action>
                    </div>
                  </td>

                  <td className="px-2 py-3">
                    <Dropdown
                      label="Status"
                      value={lead.status}
                      options={STATUS_OPTIONS}
                      align="right"
                      compact
                      onChange={(next) => onStatusChange(lead.lead_id, next as Status)}
                    />
                  </td>

                  <td className="py-3 pr-4 pl-2">
                    <button
                      type="button"
                      onClick={() => setOpen(expanded ? null : lead.lead_id)}
                      aria-expanded={expanded}
                      aria-label={expanded ? 'Fechar detalhes' : `Ver detalhes de ${lead.name}`}
                      className="grid size-8 cursor-pointer place-items-center rounded-full text-muted transition-colors hover:bg-[#f0f0f0] hover:text-ink"
                    >
                      <ChevronDown
                        size={15}
                        aria-hidden
                        className={`transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
                      />
                    </button>
                  </td>
                </tr>

                {expanded && (
                  <tr className="border-b border-[#f4f4f4] bg-[#fafafa]">
                    <td colSpan={7} className="px-5 pt-1 pb-5">
                      <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
                        {lead.pitch && (
                          <div className="flex items-start gap-3 rounded-[18px] bg-brand-wash p-3.5">
                            <p className="flex-1 text-[13px] leading-snug text-[#3d4a16] italic">
                              {lead.pitch}
                            </p>
                            <CopyButton text={lead.pitch} label="Copiar" />
                          </div>
                        )}

                        <div className="rounded-[18px] border border-line bg-card p-3.5">
                          <h4 className="mb-2 text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
                            O que está errado
                          </h4>
                          <ul className="flex flex-wrap gap-1.5">
                            {lead.reasons.map((reason) => (
                              <li key={reason}
                                  className="rounded-full border border-line bg-[#fafafa] px-2.5 py-1 text-[11.5px] text-[#5a5a5a]">
                                {reason}
                              </li>
                            ))}
                          </ul>

                          <dl className="mt-3 grid gap-1 text-[12.5px] text-muted">
                            {lead.address && (
                              <div className="flex gap-2">
                                <dt className="shrink-0">Endereço:</dt>
                                <dd className="truncate text-body">{lead.address}</dd>
                              </div>
                            )}
                            {phone && (
                              <div className="flex gap-2">
                                <dt className="shrink-0">Telefone:</dt>
                                <dd className="tnum text-body">{phone}</dd>
                              </div>
                            )}
                            {email && (
                              <div className="flex gap-2">
                                <dt className="shrink-0">E-mail:</dt>
                                <dd className="truncate text-body">{email}</dd>
                              </div>
                            )}
                            {lead.platform && (
                              <div className="flex gap-2">
                                <dt className="shrink-0">Plataforma:</dt>
                                <dd className="text-body">{lead.platform}</dd>
                              </div>
                            )}
                          </dl>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
