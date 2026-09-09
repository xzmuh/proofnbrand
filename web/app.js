/* proof-n-brand - painel. Sem framework, sem build: e servido direto pelo web.py. */

const TYPE_LABEL = {
  no_site:         { text: 'SEM SITE',        cls: 'hot'   },
  social_only:     { text: 'SÓ REDE SOCIAL',  cls: 'hot'   },
  dns_fail:        { text: 'DOMÍNIO MORTO',   cls: 'hot'   },
  site_down:       { text: 'SITE FORA DO AR', cls: 'hot'   },
  site_error:      { text: 'SITE COM ERRO',   cls: 'hot'   },
  parked_or_empty: { text: 'PÁGINA VAZIA',    cls: 'hot'   },
  timeout:         { text: 'SITE TRAVANDO',   cls: 'warn'  },
  outdated:        { text: 'DESATUALIZADO',   cls: 'warn'  },
  ok:              { text: 'SITE OK',         cls: 'plain' },
};

const CATEGORY_LABEL = {
  dentist: 'Dentistas', lawyer: 'Advogados', accountant: 'Contadores',
  estate_agent: 'Imobiliárias', veterinary: 'Veterinários', clinic: 'Clínicas',
  contractor: 'Empreiteiros', car_repair: 'Oficinas', physio: 'Fisioterapia',
  jewelry: 'Joalherias', hotel: 'Hotéis', restaurant: 'Restaurantes',
  salon: 'Salões', gym: 'Academias', bakery: 'Padarias',
};

const STATUS_LABEL = {
  novo: 'Novo', contatado: 'Contatado', respondeu: 'Respondeu',
  fechado: 'Fechado', descartado: 'Descartado',
};

// "Site quebrado" agrupa tudo que esta no ar mas nao entrega nada ao visitante.
const BROKEN = 'site_down,dns_fail,site_error,parked_or_empty,timeout';

const QUICK = [
  { key: 'all',     label: 'Todos',        filters: {} },
  { key: 'hot',     label: 'Tier A + B',   filters: { min_score: '58' } },
  { key: 'nosite',  label: 'Sem site',     filters: { lead_type: 'no_site' } },
  { key: 'broken',  label: 'Site quebrado', filters: { lead_type: BROKEN } },
  { key: 'social',  label: 'Só rede social', filters: { lead_type: 'social_only' } },
  { key: 'todo',    label: 'Não contatados', filters: { status: 'novo' } },
];

const state = {
  tab: 'leads',
  quick: 'all',
  city: 'all',
  category: 'all',
  status: 'all',
  q: '',
  summary: null,
  leads: [],
};

const $  = (sel, root = document) => root.querySelector(sel);
const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const catName = (k) => CATEGORY_LABEL[k] || k || 'sem categoria';

function toast(msg) {
  const node = $('#toast');
  node.textContent = msg;
  node.classList.add('show');
  clearTimeout(node._t);
  node._t = setTimeout(() => node.classList.remove('show'), 2600);
}

/* ------------------------------------------------------------ dados */

function currentFilters() {
  const quick = QUICK.find((q) => q.key === state.quick) || QUICK[0];
  return {
    city: state.city, category: state.category, status: state.status,
    q: state.q, limit: '400', ...quick.filters,
  };
}

async function load() {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(currentFilters())) {
    if (v && v !== 'all') params.set(k, v);
  }
  const [summary, leads] = await Promise.all([
    fetch('/api/summary').then((r) => r.json()),
    fetch('/api/leads?' + params).then((r) => r.json()),
  ]);
  state.summary = summary;
  state.leads = leads.leads || [];
  render();
}

/* ------------------------------------------------------------ dropdown */

const CHEVRON = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;

function dropdown(node, { label, value, options, onPick }) {
  const chosen = options.find((o) => o.value === value) || options[0];
  node.innerHTML = `
    <button class="dd-btn">
      <span class="label">${esc(label)}</span>
      <span class="val">${esc(chosen ? chosen.label : '—')}</span>
      ${CHEVRON}
    </button>
    <div class="dd-menu">
      ${options.map((o) => `
        <button data-value="${esc(o.value)}" class="${o.value === value ? 'sel' : ''}">
          <span>${esc(o.label)}</span>${o.n != null ? `<span class="n">${o.n}</span>` : ''}
        </button>`).join('')}
    </div>`;

  $('.dd-btn', node).onclick = (ev) => {
    ev.stopPropagation();
    const wasOpen = node.classList.contains('open');
    document.querySelectorAll('.dd.open').forEach((d) => d.classList.remove('open'));
    node.classList.toggle('open', !wasOpen);
  };
  node.querySelectorAll('.dd-menu button').forEach((btn) => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      node.classList.remove('open');
      onPick(btn.dataset.value);
    };
  });
}

document.addEventListener('click', () => {
  document.querySelectorAll('.dd.open').forEach((d) => d.classList.remove('open'));
});

/* ------------------------------------------------------------ render */

function miniBars(values, highlightLast = true) {
  const max = Math.max(1, ...values);
  return `<div class="bars">${values.map((v, i) => {
    const h = Math.max(4, Math.round((v / max) * 46));
    const dim = highlightLast && i < values.length - 3 ? ' class="dim"' : '';
    return `<i${dim} style="height:${h}px"></i>`;
  }).join('')}</div>`;
}

function renderKpis() {
  const s = state.summary;
  if (!s) return;
  const tiers = Object.fromEntries((s.tiers || []).map((t) => [t.tier, t.n]));
  const broken = (s.lead_types || [])
    .filter((t) => BROKEN.split(',').includes(t.lead_type))
    .reduce((sum, t) => sum + t.n, 0);
  const cityCounts = (s.cities || []).map((c) => c.n).slice(0, 7).reverse();

  const pct = (n) => (s.scored ? Math.round((n / s.scored) * 100) : 0);

  $('#kpis').innerHTML = `
    <div class="card kpi">
      <h3>Total de leads</h3>
      <div class="row">
        <span class="value">${s.total}</span>
        <span class="chip-delta">${s.scored} pontuados</span>
        ${miniBars(cityCounts.length ? cityCounts : [3, 5, 4, 8, 6, 9, 12])}
      </div>
      <div class="sub">${(s.cities || []).length} cidade(s) · ${(s.categories || []).length} categoria(s)</div>
    </div>

    <div class="card kpi">
      <h3>Prontos para atacar</h3>
      <div class="row">
        <span class="value">${s.hot}</span>
        <span class="chip-delta">${pct(s.hot)}% da base</span>
        ${miniBars([tiers.D || 0, tiers.C || 0, tiers.B || 0, tiers.A || 0])}
      </div>
      <div class="sub">Tier A: ${tiers.A || 0} · B: ${tiers.B || 0} · C: ${tiers.C || 0} · D: ${tiers.D || 0}</div>
    </div>

    <div class="card kpi">
      <h3>Sem site ou quebrado</h3>
      <div class="row">
        <span class="value">${s.no_site + broken}</span>
        <span class="chip-delta">venda do zero</span>
        ${miniBars([s.no_site, broken, Math.max(1, s.scored - s.no_site - broken)])}
      </div>
      <div class="sub">${s.no_site} sem site · ${broken} com site quebrado</div>
    </div>

    <div class="card kpi">
      <h3>Score médio</h3>
      <div class="row">
        <span class="value">${s.avg_score}</span>
        <span class="chip-delta neutral">de 100</span>
        ${miniBars([tiers.D || 0, tiers.C || 0, tiers.B || 0, tiers.A || 0])}
      </div>
      <div class="sub">${s.probed} sites auditados · ${s.psi} no PageSpeed</div>
    </div>`;
}

function renderQuick() {
  $('#quick').innerHTML = QUICK
    .map((q) => `<button data-key="${q.key}" class="${state.quick === q.key ? 'on' : ''}">${esc(q.label)}</button>`)
    .join('');
  $('#quick').querySelectorAll('button').forEach((btn) => {
    btn.onclick = () => { state.quick = btn.dataset.key; load(); };
  });
}

function renderFilters() {
  const s = state.summary || {};
  const cities = [{ value: 'all', label: 'Todas', n: s.total }]
    .concat((s.cities || []).map((c) => ({ value: c.city, label: `${c.city}, ${c.country}`, n: c.n })));
  const cats = [{ value: 'all', label: 'Todas', n: s.total }]
    .concat((s.categories || []).map((c) => ({ value: c.category, label: catName(c.category), n: c.n })));
  const statuses = [{ value: 'all', label: 'Todos' }]
    .concat(Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label })));

  dropdown($('.dd[data-key="city"]'), {
    label: 'Cidade', value: state.city, options: cities,
    onPick: (v) => { state.city = v; load(); },
  });
  dropdown($('.dd[data-key="category"]'), {
    label: 'Categoria', value: state.category, options: cats,
    onPick: (v) => { state.category = v; load(); },
  });
  dropdown($('.dd[data-key="status"]'), {
    label: 'Status', value: state.status, options: statuses,
    onPick: (v) => { state.status = v; load(); },
  });
}

function leadCard(lead) {
  const type = TYPE_LABEL[lead.lead_type] || { text: lead.lead_type, cls: 'plain' };
  const site = lead.website || '';
  const host = site.replace(/^https?:\/\//, '').replace(/\/$/, '');
  const done = ['fechado', 'descartado'].includes(lead.status);

  return `
  <article class="lead ${done ? 'done' : ''}" data-id="${esc(lead.lead_id)}">
    <div class="score t-${esc(lead.tier)}">
      ${Math.round(lead.score)}
      <small>TIER ${esc(lead.tier)}</small>
    </div>

    <div class="lead-main">
      <div class="lead-title">
        <h3>${esc(lead.name)}</h3>
        <span class="tag ${type.cls}">${esc(type.text)}</span>
        <span class="tag">${esc(catName(lead.category))}</span>
        ${lead.psi_perf != null ? `<span class="tag ${lead.psi_perf < 50 ? 'hot' : 'plain'}">PSI ${Math.round(lead.psi_perf)}</span>` : ''}
      </div>

      <div class="meta">
        <span>${esc(lead.city)}, ${esc(lead.country)} · ${esc(lead.currency || '')}</span>
        ${host ? `<a href="${esc(site)}" target="_blank" rel="noopener">${esc(host)}</a>` : '<span>sem site</span>'}
        ${lead.phone ? `<span>${esc(lead.phone)}</span>` : ''}
        ${lead.email ? `<a href="mailto:${esc(lead.email)}">${esc(lead.email)}</a>` : ''}
      </div>

      ${lead.reasons && lead.reasons.length
        ? `<div class="reasons">${lead.reasons.slice(0, 7).map((r) => `<span>${esc(r)}</span>`).join('')}</div>`
        : ''}

      ${lead.pitch ? `
        <div class="pitch">
          <p>${esc(lead.pitch)}</p>
          <button data-copy="${esc(lead.pitch)}">Copiar</button>
        </div>` : ''}
    </div>

    <div class="lead-side">
      <div class="dd" data-status-for="${esc(lead.lead_id)}"></div>
      <div class="link-row">
        ${lead.maps_url ? `<a href="${esc(lead.maps_url)}" target="_blank" rel="noopener">Mapa</a>` : ''}
        ${site ? `<a href="https://pagespeed.web.dev/analysis?url=${encodeURIComponent(site)}" target="_blank" rel="noopener">PageSpeed</a>` : ''}
      </div>
    </div>
  </article>`;
}

function wireLeadCards(root) {
  root.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.onclick = async () => {
      await navigator.clipboard.writeText(btn.dataset.copy);
      btn.textContent = 'Copiado';
      toast('Ângulo copiado — cole no e-mail');
      setTimeout(() => { btn.textContent = 'Copiar'; }, 1800);
    };
  });

  root.querySelectorAll('[data-status-for]').forEach((node) => {
    const id = node.dataset.statusFor;
    const lead = state.leads.find((l) => l.lead_id === id);
    if (!lead) return;
    node.innerHTML = `
      <button class="dd-btn status-pill" data-status="${esc(lead.status)}">
        <span class="dot"></span><span>${esc(STATUS_LABEL[lead.status] || lead.status)}</span>${CHEVRON}
      </button>
      <div class="dd-menu" style="right:0;left:auto">
        ${Object.entries(STATUS_LABEL).map(([v, l]) =>
          `<button data-value="${v}" class="${v === lead.status ? 'sel' : ''}">${l}</button>`).join('')}
      </div>`;

    $('.dd-btn', node).onclick = (ev) => {
      ev.stopPropagation();
      const wasOpen = node.classList.contains('open');
      document.querySelectorAll('.dd.open').forEach((d) => d.classList.remove('open'));
      node.classList.toggle('open', !wasOpen);
    };
    node.querySelectorAll('.dd-menu button').forEach((btn) => {
      btn.onclick = async (ev) => {
        ev.stopPropagation();
        node.classList.remove('open');
        const status = btn.dataset.value;
        const resp = await fetch('/api/status', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lead_id: id, status }),
        }).then((r) => r.json());
        if (resp.error) return toast('Erro: ' + resp.error);
        lead.status = status;
        toast(`${lead.name} → ${STATUS_LABEL[status]}`);
        renderContent();
      };
    });
  });
}

function renderLeads() {
  const content = $('#content');
  $('#nav-count').textContent = state.leads.length;

  if (!state.leads.length) {
    const empty = state.summary && state.summary.total === 0;
    content.innerHTML = `
      <div class="empty">
        <h3>${empty ? 'Banco vazio' : 'Nenhum lead com esses filtros'}</h3>
        <p>${empty ? 'Rode o motor para colher e auditar negócios.' : 'Afrouxe os filtros ou colha mais cidades.'}</p>
        ${empty ? '<code>python -m proofnbrand.cli run</code>' : ''}
      </div>`;
    return;
  }

  // Agrupa por categoria, a menos que o usuario ja tenha filtrado uma.
  if (state.category !== 'all') {
    content.innerHTML = `<div class="leads">${state.leads.map(leadCard).join('')}</div>`;
  } else {
    const groups = new Map();
    for (const lead of state.leads) {
      if (!groups.has(lead.category)) groups.set(lead.category, []);
      groups.get(lead.category).push(lead);
    }
    content.innerHTML = [...groups.entries()]
      .sort((a, b) => b[1].length - a[1].length)
      .map(([cat, items]) => `
        <div class="group-head">
          <h2>${esc(catName(cat))}</h2>
          <span class="n">${items.length}</span>
          <span class="line"></span>
        </div>
        <div class="leads">${items.map(leadCard).join('')}</div>`)
      .join('');
  }
  wireLeadCards(content);
}

function renderTable(rows, columns, title) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  $('#content').innerHTML = `
    <div class="card" style="padding:8px 8px 4px">
      <table class="table">
        <thead><tr>${columns.map((c) => `<th>${c}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map((r) => `
            <tr>
              <td style="font-weight:600">${esc(r.label)}</td>
              <td>${r.n}</td>
              <td>${r.hot || 0}</td>
              <td>${r.avg != null ? r.avg.toFixed(1) : '—'}</td>
              <td class="barcell"><div class="meter"><i style="width:${(r.n / max) * 100}%"></i></div></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function renderContent() {
  const s = state.summary || {};
  if (state.tab === 'leads') {
    $('#filters').style.display = '';
    $('#page-title').textContent = 'Leads';
    $('#page-sub').textContent = 'Negócios com site ruim, prontos para abordagem';
    return renderLeads();
  }
  $('#filters').style.display = 'none';

  if (state.tab === 'cidades') {
    $('#page-title').textContent = 'Cidades';
    $('#page-sub').textContent = 'Onde a base está concentrada';
    return renderTable(
      (s.cities || []).map((c) => ({ label: `${c.city}, ${c.country}`, n: c.n, hot: c.hot, avg: null })),
      ['Cidade', 'Leads', 'Tier A+B', 'Score médio', ''],
    );
  }

  $('#page-title').textContent = 'Categorias';
  $('#page-sub').textContent = 'Quais nichos rendem mais leads quentes';
  renderTable(
    (s.categories || []).map((c) => ({
      label: catName(c.category), n: c.n, hot: c.hot,
      avg: c.avg_score != null ? c.avg_score : null,
    })),
    ['Categoria', 'Leads', 'Tier A+B', 'Score médio', ''],
  );
}

function render() {
  renderKpis();
  renderQuick();
  renderFilters();
  renderContent();
}

/* ------------------------------------------------------------ eventos */

$('#nav').querySelectorAll('button').forEach((btn) => {
  btn.onclick = () => {
    state.tab = btn.dataset.tab;
    $('#nav').querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
    renderContent();
  };
});

let searchTimer;
$('#q').oninput = (ev) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = ev.target.value.trim(); load(); }, 280);
};

$('#refresh').onclick = () => load().then(() => toast('Atualizado'));

$('#export').onclick = async () => {
  const r = await fetch('/api/export').then((x) => x.json());
  toast(r.error ? 'Erro: ' + r.error : `${r.count} leads em out/leads.csv`);
};

$('#export-cat').onclick = async () => {
  const r = await fetch('/api/export-by-category').then((x) => x.json());
  toast(r.error ? 'Erro: ' + r.error : `${r.files.length} arquivos em out/por-categoria/`);
};

load();
