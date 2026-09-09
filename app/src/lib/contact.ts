/* Links de contato a partir do que a OSM entrega. */

/* DDI por país das cidades semeadas — usado só quando o telefone vem sem "+".
   Sem isso, um número local viraria um wa.me apontando para o país errado. */
const DIAL_CODE: Record<string, string> = {
  BR: '55', US: '1', CA: '1', IE: '353', NL: '31', PT: '351',
  ES: '34', IT: '39', DE: '49', GB: '44', FR: '33',
}

export function phoneDigits(phone: string | null, country: string | null): string | null {
  if (!phone) return null
  const raw = phone.trim()
  const digits = raw.replace(/\D/g, '')
  if (digits.length < 7) return null

  // Já veio internacional: confia no que está lá.
  if (raw.startsWith('+') || raw.startsWith('00')) {
    return digits.replace(/^00/, '')
  }

  const code = DIAL_CODE[country ?? '']
  if (!code) return null
  // Tira o zero-tronco nacional (comum na Europa) antes de prefixar o DDI.
  return code + digits.replace(/^0/, '')
}

export function whatsappLink(phone: string | null, country: string | null): string | null {
  const digits = phoneDigits(phone, country)
  return digits ? `https://wa.me/${digits}` : null
}

export function telLink(phone: string | null): string | null {
  if (!phone) return null
  const cleaned = phone.trim().replace(/[^\d+]/g, '')
  return cleaned.length >= 7 ? `tel:${cleaned}` : null
}

/* Assunto e corpo já preenchidos com o ângulo de venda daquele lead. */
export function mailtoLink(email: string | null, name: string, pitch: string): string | null {
  if (!email) return null
  const subject = `Quick note about ${name}'s website`
  const body = pitch
    ? `Hi,\n\nI came across ${name} and noticed something: ${pitch}\n\nHappy to show you what a fix would look like — no charge for the mockup.\n\nBest,\n`
    : ''
  return `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}
