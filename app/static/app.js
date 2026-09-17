const state = {
  activeTab: "dashboard",
  municipalities: [],
  years: [],
  // Registros
  recordsTotal: 0,
  recordsLimit: 50,
  recordsOffset: 0,
  recordsAbortController: null,
  recordsDebounceTimer: null,
  // Atenção
  attentionTotal: 0,
  attentionLimit: 20,
  attentionOffset: 0,
  attentionAbortController: null,
  attentionDebounceTimer: null,
  // Fornecedores
  suppliersAbortController: null,
  suppliersDebounceTimer: null,
};

const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCurrency(val) {
  if (val === null || val === undefined || val === "") return "R$ 0,00";
  if (typeof val === "number") {
    return val.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  const s = String(val).trim();
  if (!s) return "R$ 0,00";

  const isNeg = s.includes("-") || s.startsWith("(");
  const clean = s.replace(/[^\d.,]/g, "");
  if (!clean) return escapeHtml(s);

  let num;
  if (clean.includes(",")) {
    // Formato brasileiro: '20.000,00' -> pontos são milhares, vírgula é decimal
    num = parseFloat(clean.replace(/\./g, "").replace(",", "."));
  } else {
    // Formato decimal padrão: '20000.00' -> ponto é decimal
    // Se houver mais de um ponto (ex: '1.000.000'), são milhares sem vírgula
    if ((clean.match(/\./g) || []).length > 1) {
      num = parseFloat(clean.replace(/\./g, ""));
    } else {
      num = parseFloat(clean);
    }
  }

  if (isNaN(num)) return escapeHtml(s);
  if (isNeg && num > 0) num = -num;
  return num.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatNumber(val) {
  if (val === null || val === undefined) return "0";
  const num = Number(val);
  return isNaN(num) ? String(val) : num.toLocaleString("pt-BR");
}

async function getJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Falha ao consultar ${path}`);
  return response.json();
}

function formatKind(kind) {
  if (kind === "licitacao") return "Licitação";
  if (kind === "despesa") return "Despesa";
  if (kind === "contrato") return "Contrato";
  return kind || "-";
}

function isDirectDetailUrl(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    if (u.searchParams.has("id") || u.searchParams.has("codigo") || u.searchParams.has("processo")) {
      return true;
    }
    const genericEndpoints = [
      "/cidadao/transparencia/sgdespesas",
      "/cidadao/transparencia/mgdespesas",
      "/cidadao/transparencia/sglicitacoes",
      "/cidadao/transparencia/mglicitacoes",
      "/cidadao/transparencia/sgcontratos",
      "/cidadao/transparencia/contratos_mg",
      "/sgdespesas",
      "/mgdespesas",
      "/sglicitacoes",
      "/mglicitacoes",
      "/sgcontratos",
      "/contratos_mg",
    ];
    const path = u.pathname.replace(/\/+$/, "");
    if (genericEndpoints.some((ep) => path.endsWith(ep))) {
      return false;
    }
    return true;
  } catch (e) {
    return false;
  }
}

function formatCleanMoneyForPortal(val) {
  if (val === null || val === undefined || val === "") return "";
  const s = String(val).trim();
  if (!s) return "";
  const clean = s.replace(/[^\d.,]/g, "");
  if (!clean) return "";
  let num;
  if (clean.includes(",")) {
    num = parseFloat(clean.replace(/\./g, "").replace(",", "."));
  } else {
    num = parseFloat(clean);
  }
  if (isNaN(num)) return s;
  return num.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function renderSourceAction(record) {
  let url = record.detail_url || record.source_url;
  if (!url && record.municipality) {
    if (record.municipality.toLowerCase().includes("ceres")) {
      url = "https://acessoainformacao.ceres.go.gov.br/cidadao/transparencia/sgdespesas";
    } else if (record.municipality.toLowerCase().includes("rialma")) {
      url = "https://acessoainformacao.rialma.go.gov.br/cidadao/transparencia/sgdespesas";
    }
  }
  if (!url) return "-";
  const isDirect = isDirectDetailUrl(url);

  const chips = [];

  // 1. Favorecido
  if (record.favored) {
    const cleanFav = record.favored.trim();
    chips.push(
      `<button type="button" class="btn-copy-chip" data-copy="${escapeHtml(cleanFav)}" title="Copiar favorecido: ${escapeHtml(cleanFav)}">Favorecido</button>`
    );
  }

  // 2. Valor
  const valField = record.committed_value ?? record.value ?? record.paid_value;
  const cleanVal = formatCleanMoneyForPortal(valField);
  if (cleanVal) {
    chips.push(
      `<button type="button" class="btn-copy-chip" data-copy="${escapeHtml(cleanVal)}" title="Copiar valor monetário: ${escapeHtml(cleanVal)}">Valor</button>`
    );
  }

  // 3. Número de movimento ou processo
  const numMov = (record.movement_number || "").trim();
  const numProc = (record.process_number || "").trim();
  if (numMov) {
    chips.push(
      `<button type="button" class="btn-copy-chip" data-copy="${escapeHtml(numMov)}" title="Copiar nº do empenho: ${escapeHtml(numMov)}">Nº Empenho</button>`
    );
  } else if (numProc) {
    chips.push(
      `<button type="button" class="btn-copy-chip" data-copy="${escapeHtml(numProc)}" title="Copiar processo: ${escapeHtml(numProc)}">Processo</button>`
    );
  }

  const chipsHtml = chips.length ? `<div class="copy-actions-group">${chips.join("")}</div>` : "";

  if (isDirect) {
    return `
      <div class="source-cell">
        <a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Abrir direto ↗</a>
        ${chipsHtml}
      </div>
    `;
  }

  return `
    <div class="source-cell">
      <a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer" title="Abrir portal da prefeitura em nova aba">Abrir portal ↗</a>
      ${chipsHtml}
    </div>
  `;
}

// -------------------------------------------------------------
// NAVEGAÇÃO ENTRE ABAS
// -------------------------------------------------------------

function getCurrentTab() {
  const hash = window.location.hash.replace("#", "").trim().toLowerCase();
  const validTabs = ["dashboard", "records", "attention", "suppliers"];
  return validTabs.includes(hash) ? hash : "dashboard";
}

function switchTab(tabName) {
  state.activeTab = tabName;

  // Atualiza botões no topo
  document.querySelectorAll("#topbar-nav .nav-tab").forEach((tab) => {
    if (tab.getAttribute("data-tab") === tabName) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });

  // Alterna seções de visualização
  document.querySelectorAll(".tab-view").forEach((view) => {
    view.style.display = "none";
    view.classList.remove("active");
  });

  const activeView = byId(`view-${tabName}`);
  if (activeView) {
    activeView.style.display = "block";
    activeView.classList.add("active");
  }

  // Carrega conteúdo específico da aba ativada
  if (tabName === "dashboard") {
    loadDashboardView();
  } else if (tabName === "records") {
    loadRecordsView();
  } else if (tabName === "attention") {
    loadAttentionView();
  } else if (tabName === "suppliers") {
    loadSuppliersView();
  }
}

window.addEventListener("hashchange", () => {
  switchTab(getCurrentTab());
});

// -------------------------------------------------------------
// METADADOS (MUNICÍPIOS E ANOS)
// -------------------------------------------------------------

function populateSelect(selectId, options, defaultLabel, currentValue) {
  const el = byId(selectId);
  if (!el) return;
  const val = currentValue !== undefined ? currentValue : el.value;
  el.innerHTML = `<option value="">${escapeHtml(defaultLabel)}</option>`;
  options.forEach((opt) => {
    const isSelected = String(opt) === String(val) ? " selected" : "";
    el.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(opt)}"${isSelected}>${escapeHtml(opt)}</option>`);
  });
}

async function loadMetadata() {
  try {
    const [municipalities, years] = await Promise.all([
      getJson("/api/municipalities"),
      getJson("/api/years"),
    ]);
    state.municipalities = [...new Set(municipalities)].sort();
    state.years = [...new Set(years)].filter(Boolean).sort((a, b) => b - a);

    const munSelects = ["dash-municipality", "records-municipality", "att-municipality", "supp-municipality"];
    munSelects.forEach((id) => populateSelect(id, state.municipalities, "Todos (Ceres e Rialma)"));

    const yearSelects = ["dash-year", "records-year", "att-year", "supp-year"];
    yearSelects.forEach((id) => populateSelect(id, state.years, "Todos os anos"));
  } catch (err) {
    console.error("Falha ao carregar metadados:", err);
  }
}

// -------------------------------------------------------------
// ABA 1: DASHBOARD
// -------------------------------------------------------------

function navigateToRecords(municipality, year, kind) {
  if (byId("records-municipality")) byId("records-municipality").value = municipality || "";
  if (byId("records-year")) byId("records-year").value = year || "";
  if (byId("records-kind")) byId("records-kind").value = kind || "";
  if (byId("records-status")) byId("records-status").value = "";
  if (byId("records-query")) byId("records-query").value = "";
  state.recordsOffset = 0;
  window.location.hash = "#records";
}

function renderDashboardSummaryCards(summary, selectedKind = "") {
  const byKind = summary.totals_by_kind || summary.records_by_kind || {};
  const totalDespesas = byKind.despesa || 0;
  const totalLicitacoes = byKind.licitacao || 0;
  const totalContratos = byKind.contrato || 0;

  const fin = summary.expenses_financial_totals || {};
  const emp = fin.total_empenhado || 0;
  const liq = fin.total_liquidado || 0;
  const pag = fin.total_pago || 0;

  const attentionCount = summary.attention_count_limited ?? summary.attention_count ?? 0;

  let cardsHtml = "";

  if (selectedKind === "licitacao") {
    // 3 cards: Registros Totais (licitações), Licitações, Pontos Priorizados
    cardsHtml = `
      <article class="summary-card">
        <span class="card-label">Registros Totais</span>
        <strong>${formatNumber(totalLicitacoes)}</strong>
        <small>processos licitatórios filtrados</small>
      </article>
      <article class="summary-card">
        <span class="card-label">Licitações <span class="badge-partial" title="Amostra preliminar coletada no MVP">coleta parcial</span></span>
        <strong>${formatNumber(totalLicitacoes)}</strong>
        <small>processos de compras (amostra preliminar)</small>
      </article>
      <article class="summary-card card-attention card-clickable" id="card-attention-summary" role="button" tabindex="0" title="Ver pontos de atenção relacionados a licitações">
        <span class="card-label">Pontos Priorizados ↗</span>
        <strong>${formatNumber(attentionCount)}</strong>
        <small>em processos licitatórios (ver aba)</small>
      </article>
    `;
  } else if (selectedKind === "contrato") {
    // 3 cards: Registros Totais (contratos), Contratos, Pontos Priorizados
    cardsHtml = `
      <article class="summary-card">
        <span class="card-label">Registros Totais</span>
        <strong>${formatNumber(totalContratos)}</strong>
        <small>instrumentos contratuais filtrados</small>
      </article>
      <article class="summary-card">
        <span class="card-label">Contratos <span class="badge-partial" title="Amostra preliminar coletada no MVP">coleta parcial</span></span>
        <strong>${formatNumber(totalContratos)}</strong>
        <small>instrumentos firmados (amostra preliminar)</small>
      </article>
      <article class="summary-card card-attention card-clickable" id="card-attention-summary" role="button" tabindex="0" title="Ver pontos de atenção relacionados a contratos">
        <span class="card-label">Pontos Priorizados ↗</span>
        <strong>${formatNumber(attentionCount)}</strong>
        <small>em contratos públicos (ver aba)</small>
      </article>
    `;
  } else if (selectedKind === "despesa") {
    // 6 cards: Registros Totais (despesas), Despesas, Empenhado, Liquidado, Pago, Pontos Priorizados
    cardsHtml = `
      <article class="summary-card">
        <span class="card-label">Registros Totais</span>
        <strong>${formatNumber(totalDespesas)}</strong>
        <small>despesas públicas filtradas</small>
      </article>
      <article class="summary-card">
        <span class="card-label">Despesas</span>
        <strong>${formatNumber(totalDespesas)}</strong>
        <small>coleta completa (2025–2026)</small>
      </article>
      <article class="summary-card card-empenhado">
        <span class="card-label">Total Empenhado</span>
        <strong class="currency-strong">${formatCurrency(emp)}</strong>
        <small>reserva orçamentária prévia</small>
      </article>
      <article class="summary-card card-liquidado">
        <span class="card-label">Total Liquidado</span>
        <strong class="currency-strong">${formatCurrency(liq)}</strong>
        <small>serviços e bens atestados</small>
      </article>
      <article class="summary-card card-pago">
        <span class="card-label">Total Pago</span>
        <strong class="currency-strong">${formatCurrency(pag)}</strong>
        <small>ordens bancárias quitadas</small>
      </article>
      <article class="summary-card card-attention card-clickable" id="card-attention-summary" role="button" tabindex="0" title="Ver pontos de atenção relacionados a despesas">
        <span class="card-label">Pontos Priorizados ↗</span>
        <strong>${formatNumber(attentionCount)}</strong>
        <small>em despesas públicas (ver aba)</small>
      </article>
    `;
  } else {
    // Todos os tipos (""): 8 cards
    const totalRegistros = Object.values(byKind).reduce((a, b) => a + b, 0);
    cardsHtml = `
      <article class="summary-card">
        <span class="card-label">Registros Totais</span>
        <strong>${formatNumber(totalRegistros)}</strong>
        <small>base orçamentária selecionada</small>
      </article>
      <article class="summary-card">
        <span class="card-label">Despesas</span>
        <strong>${formatNumber(totalDespesas)}</strong>
        <small>coleta completa (2025–2026)</small>
      </article>
      <article class="summary-card">
        <span class="card-label">Licitações <span class="badge-partial" title="Amostra preliminar coletada no MVP">coleta parcial</span></span>
        <strong>${formatNumber(totalLicitacoes)}</strong>
        <small>processos de compras (amostra preliminar)</small>
      </article>
      <article class="summary-card">
        <span class="card-label">Contratos <span class="badge-partial" title="Amostra preliminar coletada no MVP">coleta parcial</span></span>
        <strong>${formatNumber(totalContratos)}</strong>
        <small>instrumentos firmados (amostra preliminar)</small>
      </article>
      <article class="summary-card card-empenhado">
        <span class="card-label">Total Empenhado</span>
        <strong class="currency-strong">${formatCurrency(emp)}</strong>
        <small>reserva orçamentária prévia</small>
      </article>
      <article class="summary-card card-liquidado">
        <span class="card-label">Total Liquidado</span>
        <strong class="currency-strong">${formatCurrency(liq)}</strong>
        <small>serviços e bens atestados</small>
      </article>
      <article class="summary-card card-pago">
        <span class="card-label">Total Pago</span>
        <strong class="currency-strong">${formatCurrency(pag)}</strong>
        <small>ordens bancárias quitadas</small>
      </article>
      <article class="summary-card card-attention card-clickable" id="card-attention-summary" role="button" tabindex="0" title="Clique para abrir a investigação detalhada na aba Atenção">
        <span class="card-label">Pontos Priorizados ↗</span>
        <strong>${formatNumber(attentionCount)}</strong>
        <small>termos de relevância contextual (ver aba)</small>
      </article>
    `;
  }

  const container = byId("summary-cards");
  if (container) {
    container.innerHTML = cardsHtml;
    const attCard = byId("card-attention-summary");
    if (attCard) {
      attCard.addEventListener("click", () => {
        const mun = byId("dash-municipality")?.value || "";
        const yr = byId("dash-year")?.value || "";
        if (byId("att-municipality")) byId("att-municipality").value = mun;
        if (byId("att-year")) byId("att-year").value = yr;
        if (byId("att-kind")) byId("att-kind").value = selectedKind;
        window.location.hash = "#attention";
      });
      attCard.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          window.location.hash = "#attention";
        }
      });
    }
  }
}

function renderDashboardFavoredTable(favoredList) {
  const body = byId("favored-body");
  if (!body) return;
  if (!favoredList || !favoredList.length) {
    body.innerHTML = '<tr><td class="empty-state" colspan="7">Nenhum fornecedor encontrado para estes filtros.</td></tr>';
    return;
  }
  body.innerHTML = favoredList.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.favored)}</strong></td>
      <td>${escapeHtml(item.municipality)}</td>
      <td>${escapeHtml(item.year || "-")}</td>
      <td class="td-num">${formatNumber(item.movements_count)}</td>
      <td class="td-num">${formatCurrency(item.total_empenhado)}</td>
      <td class="td-num">${formatCurrency(item.total_liquidado)}</td>
      <td class="td-num"><strong>${formatCurrency(item.total_pago)}</strong></td>
    </tr>
  `).join("");
}

async function loadDashboardKindPreview(kind, municipality, year) {
  const eyebrowEl = byId("dash-kind-eyebrow");
  const titleEl = byId("dash-kind-title");
  const ctaEl = byId("dash-kind-cta");
  const contentEl = byId("dash-kind-content");
  if (!contentEl) return;

  const isLic = kind === "licitacao";
  const kindLabel = isLic ? "Licitações" : "Contratos";
  const kindSingular = isLic ? "licitação" : "contrato";

  if (eyebrowEl) eyebrowEl.textContent = isLic ? "Processos licitatórios" : "Instrumentos contratuais";
  if (titleEl) titleEl.textContent = `${kindLabel} coletadas`;
  if (ctaEl) {
    ctaEl.textContent = `Ver todas as ${kindLabel.toLowerCase()} na aba Registros →`;
    ctaEl.onclick = (e) => {
      e.preventDefault();
      navigateToRecords(municipality, year, kind);
    };
  }

  contentEl.innerHTML = `<div class="empty-state">Carregando dados de ${escapeHtml(kindLabel.toLowerCase())}...</div>`;

  const params = new URLSearchParams({
    kind,
    limit: "10",
    offset: "0",
  });
  if (municipality) params.set("municipality", municipality);
  if (year) params.set("year", year);

  try {
    const payload = await getJson(`/api/records?${params.toString()}`);
    const items = payload.items || [];
    const total = payload.total || 0;

    if (total === 0) {
      let filterDesc = [];
      if (municipality) filterDesc.push(municipality);
      if (year) filterDesc.push(`ano ${year}`);
      const filterText = filterDesc.length ? ` para ${filterDesc.join(" · ")}` : "";

      let sampleNotice = "";
      if (year === "2025") {
        sampleNotice = `<br>Nota: As ${kindLabel.toLowerCase()} disponíveis no observatório pertencem ao exercício de 2026 (amostra preliminar coletada no MVP).`;
      }

      contentEl.innerHTML = `
        <div class="empty-state-box">
          <p class="empty-state-title">Nenhuma ${kindSingular} coletada para estes filtros.</p>
          <p class="empty-state-desc">
            Não foram encontrados registros de ${escapeHtml(kindLabel.toLowerCase())}${escapeHtml(filterText)}.
            ${sampleNotice}
          </p>
          <button type="button" class="btn-cta-link" id="btn-empty-goto-records">
            Ver todas as ${escapeHtml(kindLabel.toLowerCase())} na aba Registros →
          </button>
        </div>
      `;
      byId("btn-empty-goto-records")?.addEventListener("click", () => {
        navigateToRecords(municipality, year === "2025" ? "" : year, kind);
      });
      return;
    }

    contentEl.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Município</th>
              <th>Ano</th>
              <th>${isLic ? "Processo / Modalidade" : "Processo"}</th>
              <th>${isLic ? "Título / Objeto" : "Contratado / Objeto"}</th>
              <th>${isLic ? "Status" : "Data Publicação"}</th>
              <th class="th-num">Valor</th>
              <th class="link-column">Fonte</th>
            </tr>
          </thead>
          <tbody>
            ${items.map((r) => `
              <tr>
                <td>${escapeHtml(r.municipality || "-")}</td>
                <td><strong>${escapeHtml(r.year || "-")}</strong></td>
                <td>
                  <strong>${escapeHtml(r.process_number || "-")}</strong>
                  ${r.modality ? `<br><small class="type-badge">${escapeHtml(r.modality)}</small>` : ""}
                </td>
                <td class="td-title">
                  ${isLic ? escapeHtml(r.title || r.object || "-") : `<strong>${escapeHtml(r.favored || "")}</strong><br><small>${escapeHtml(r.title || r.object || "-")}</small>`}
                </td>
                <td>
                  ${isLic ? (r.status ? `<span class="status-badge">${escapeHtml(r.status)}</span>` : "-") : escapeHtml(r.published_at || "-")}
                </td>
                <td class="td-num">${r.value ? formatCurrency(r.value) : "Não informado"}</td>
                <td class="link-column">${renderSourceAction(r)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
      <div style="margin-top: 14px; display: flex; justify-content: space-between; align-items: center;">
        <span class="section-note">Exibindo os ${items.length} primeiros registros de ${formatNumber(total)} coletados</span>
        <button type="button" class="btn-cta-link" id="btn-table-goto-records">
          Ver todas as ${total} ${kindLabel.toLowerCase()} na aba Registros →
        </button>
      </div>
    `;
    byId("btn-table-goto-records")?.addEventListener("click", () => {
      navigateToRecords(municipality, year, kind);
    });
  } catch (err) {
    contentEl.innerHTML = `<div class="empty-state">Erro ao consultar registros de ${escapeHtml(kindLabel.toLowerCase())}.</div>`;
  }
}

async function loadDashboardView() {
  const municipality = (byId("dash-municipality")?.value || "").trim();
  const year = (byId("dash-year")?.value || "").trim();
  const kind = (byId("dash-kind")?.value || "").trim().toLowerCase();

  const params = new URLSearchParams();
  if (municipality) params.set("municipality", municipality);
  if (year) params.set("year", year);
  if (kind) params.set("kind", kind);

  // 1. Carregar Summary
  try {
    const summary = await getJson(`/api/summary?${params.toString()}`);
    renderDashboardSummaryCards(summary, kind);
  } catch (err) {
    const container = byId("summary-cards");
    if (container) container.innerHTML = '<article class="summary-card"><span class="card-label">Erro ao carregar</span><strong>—</strong><small>tente atualizar</small></article>';
  }

  // 2. Seção inferior (Fornecedores vs Licitações/Contratos)
  const favoredSection = byId("dashboard-favored-section");
  const kindSection = byId("dashboard-kind-section");

  if (kind === "licitacao" || kind === "contrato") {
    if (favoredSection) favoredSection.style.display = "none";
    if (kindSection) kindSection.style.display = "block";
    loadDashboardKindPreview(kind, municipality, year);
  } else {
    if (kindSection) kindSection.style.display = "none";
    if (favoredSection) favoredSection.style.display = "block";

    // Top 10 Favorecidos (apenas para Todos ou Despesas)
    const expParams = new URLSearchParams();
    if (municipality) expParams.set("municipality", municipality);
    if (year) expParams.set("year", year);
    expParams.set("kind", "despesa");
    expParams.set("limit", "10");

    try {
      const expSummary = await getJson(`/api/expenses/summary?${expParams.toString()}`);
      renderDashboardFavoredTable(expSummary.top_favored || []);
    } catch (err) {
      const body = byId("favored-body");
      if (body) body.innerHTML = '<tr><td class="empty-state" colspan="7">Não foi possível carregar o resumo de fornecedores.</td></tr>';
    }
  }
}

// -------------------------------------------------------------
// ABA 2: REGISTROS PÚBLICOS
// -------------------------------------------------------------

function renderRecordsTable(records, total) {
  state.recordsTotal = total;
  const countEl = byId("records-count");
  if (countEl) {
    countEl.textContent = `${formatNumber(total)} registro${total === 1 ? "" : "s"} encontrado${total === 1 ? "" : "s"}`;
  }

  const thead = byId("records-table-headers");
  const tbody = byId("records-body");
  if (!thead || !tbody) return;

  const kind = byId("records-kind")?.value.trim() || "";

  if (kind === "despesa") {
    thead.innerHTML = `
      <tr>
        <th>Município</th>
        <th>Ano</th>
        <th>Favorecido</th>
        <th>Data</th>
        <th>Descrição</th>
        <th class="th-num">Empenhado</th>
        <th class="th-num">Liquidado</th>
        <th class="th-num">Pago</th>
        <th class="link-column">Fonte</th>
      </tr>
    `;
    if (!records.length) {
      tbody.innerHTML = '<tr><td class="empty-state" colspan="9">Nenhuma despesa encontrada para estes filtros.</td></tr>';
      updateRecordsPagination(0, 0, state.recordsLimit);
      return;
    }
    tbody.innerHTML = records.map((r) => `
      <tr>
        <td>${escapeHtml(r.municipality || "-")}</td>
        <td><strong>${escapeHtml(r.year || "-")}</strong></td>
        <td><strong>${escapeHtml(r.favored || "-")}</strong></td>
        <td>${escapeHtml(r.movement_date || "-")}</td>
        <td class="td-title">${escapeHtml(r.description || r.title || "-")}</td>
        <td class="td-num">${formatCurrency(r.committed_value)}</td>
        <td class="td-num">${formatCurrency(r.liquidated_value)}</td>
        <td class="td-num"><strong>${formatCurrency(r.paid_value)}</strong></td>
        <td class="link-column">${renderSourceAction(r)}</td>
      </tr>
    `).join("");
  } else if (kind === "licitacao" || kind === "contrato") {
    thead.innerHTML = `
      <tr>
        <th>Município</th>
        <th>Ano</th>
        <th>Tipo</th>
        <th>Título / Objeto</th>
        <th>Status</th>
        <th class="th-num">Valor</th>
        <th class="link-column">Fonte</th>
      </tr>
    `;
    if (!records.length) {
      tbody.innerHTML = '<tr><td class="empty-state" colspan="7">Nenhum registro encontrado para estes filtros.</td></tr>';
      updateRecordsPagination(0, 0, state.recordsLimit);
      return;
    }
    tbody.innerHTML = records.map((r) => `
      <tr>
        <td>${escapeHtml(r.municipality || "-")}</td>
        <td><strong>${escapeHtml(r.year || "-")}</strong></td>
        <td><span class="type-badge">${formatKind(r.kind)}</span></td>
        <td class="td-title">${escapeHtml(r.title || r.object || "-")}</td>
        <td>${r.status ? `<span class="status-badge">${escapeHtml(r.status)}</span>` : "-"}</td>
        <td class="td-num">${r.value ? formatCurrency(r.value) : "Não informado"}</td>
        <td class="link-column">${renderSourceAction(r)}</td>
      </tr>
    `).join("");
  } else {
    // Geral (Todos)
    thead.innerHTML = `
      <tr>
        <th>Município</th>
        <th>Ano</th>
        <th>Tipo</th>
        <th>Favorecido / Título</th>
        <th>Data</th>
        <th class="th-num">Valor Financeiro</th>
        <th class="link-column">Fonte</th>
      </tr>
    `;
    if (!records.length) {
      tbody.innerHTML = '<tr><td class="empty-state" colspan="7">Nenhum registro encontrado para estes filtros.</td></tr>';
      updateRecordsPagination(0, 0, state.recordsLimit);
      return;
    }
    tbody.innerHTML = records.map((r) => {
      let finText = "-";
      if (r.kind === "despesa") {
        const emp = r.committed_value ? formatCurrency(r.committed_value) : "-";
        const pag = r.paid_value ? formatCurrency(r.paid_value) : "-";
        finText = `<span title="Empenhado: ${emp} | Pago: ${pag}">Emp: ${emp}<br><small style="color:var(--muted)">Pago: ${pag}</small></span>`;
      } else {
        finText = r.value ? formatCurrency(r.value) : "Não informado";
      }

      return `
        <tr>
          <td>${escapeHtml(r.municipality || "-")}</td>
          <td><strong>${escapeHtml(r.year || "-")}</strong></td>
          <td><span class="type-badge">${formatKind(r.kind)}</span></td>
          <td class="td-title">${escapeHtml(r.favored || r.title || "-")}</td>
          <td>${escapeHtml(r.movement_date || r.published_at || r.opening_date || "-")}</td>
          <td class="td-num">${finText}</td>
          <td class="link-column">${renderSourceAction(r)}</td>
        </tr>
      `;
    }).join("");
  }

  updateRecordsPagination(total, state.recordsOffset, state.recordsLimit);
}

function updateRecordsPagination(total, offset, limit) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  const infoEl = byId("records-pagination-info");
  if (infoEl) {
    infoEl.textContent = `Mostrando ${formatNumber(start)}–${formatNumber(end)} de ${formatNumber(total)} registros`;
  }

  const indicatorEl = byId("records-page-indicator");
  if (indicatorEl) {
    indicatorEl.textContent = `Página ${page} de ${totalPages}`;
  }

  const btnPrev = byId("records-btn-prev");
  if (btnPrev) btnPrev.disabled = offset <= 0;

  const btnNext = byId("records-btn-next");
  if (btnNext) btnNext.disabled = end >= total;
}

async function loadRecordsView() {
  if (state.recordsAbortController) {
    state.recordsAbortController.abort();
  }
  state.recordsAbortController = new AbortController();
  const signal = state.recordsAbortController.signal;

  const municipality = byId("records-municipality")?.value.trim() || "";
  const year = byId("records-year")?.value.trim() || "";
  const kind = byId("records-kind")?.value.trim() || "";
  const status = byId("records-status")?.value.trim() || "";
  const q = byId("records-query")?.value.trim() || "";

  const params = new URLSearchParams({
    limit: String(state.recordsLimit),
    offset: String(state.recordsOffset),
  });
  if (municipality) params.set("municipality", municipality);
  if (year) params.set("year", year);
  if (kind) params.set("kind", kind);
  if (status) params.set("status", status);
  if (q) params.set("q", q);

  try {
    const payload = await getJson(`/api/records?${params.toString()}`, { signal });
    if (payload.error) throw new Error(payload.error);
    renderRecordsTable(payload.items || [], payload.total || 0);
  } catch (err) {
    if (err.name === "AbortError") return;
    const body = byId("records-body");
    if (body) body.innerHTML = `<tr><td class="empty-state" colspan="7">${escapeHtml(err.message || "Erro ao consultar registros.")}</td></tr>`;
    const countEl = byId("records-count");
    if (countEl) countEl.textContent = "Dados indisponíveis";
  }
}

// -------------------------------------------------------------
// ABA 3: PONTOS DE REVISÃO (ANOMALIAS ESTATÍSTICAS)
// -------------------------------------------------------------

function formatAnomalyCategory(cat) {
  const map = {
    value_outlier: "Outlier de Valor (IQR)",
    supplier_concentration: "Concentração em Fornecedor",
    recurring_payments: "Pagamentos Recorrentes",
    payment_flow_inconsistency: "Divergência Contábil",
    possible_fragmentation: "Possível Agrupamento",
    repeated_description: "Descrição Padronizada",
    new_supplier_high_value: "Fornecedor Novo",
  };
  return map[cat] || cat || "Geral";
}

function renderAttentionTable(items, total) {
  state.attentionTotal = total;
  const countEl = byId("att-count");
  if (countEl) {
    countEl.textContent = `${formatNumber(total)} ponto${total === 1 ? "" : "s"} de revisão identificado${total === 1 ? "" : "s"}`;
  }

  const tbody = byId("attention-body");
  if (!tbody) return;

  if (!items || !items.length) {
    tbody.innerHTML = '<tr><td class="empty-state" colspan="8">Nenhum ponto de revisão encontrado para estes filtros.</td></tr>';
    updateAttentionPagination(0, 0, state.attentionLimit);
    return;
  }

  tbody.innerHTML = items.map((item) => {
    const sevClass = `sev-${(item.severity || "baixa").toLowerCase()}`;
    const formattedCat = formatAnomalyCategory(item.category);
    const finVal = item.value ? formatCurrency(item.value) : "-";

    const hasEvidence = item.evidence && Object.keys(item.evidence).length > 0;
    const evidenceHtml = hasEvidence
      ? `<details class="evidence-details">
           <summary>Ver evidências técnicas (auditável)</summary>
           <pre class="evidence-pre">${escapeHtml(JSON.stringify(item.evidence, null, 2))}</pre>
         </details>`
      : "";

    const movInfo = item.movement_number
      ? `<br><small class="mono-meta" title="Identificador de empenho/processo">Emp/Proc: ${escapeHtml(item.movement_number)}</small>`
      : "";

    return `
      <tr>
        <td>${escapeHtml(item.municipality || "-")}</td>
        <td><strong>${escapeHtml(item.year || "-")}</strong></td>
        <td><span class="cat-badge cat-${escapeHtml(item.category)}">${escapeHtml(formattedCat)}</span></td>
        <td class="th-num">
          <span class="sev-badge ${sevClass}">
            ${escapeHtml((item.severity || "").toUpperCase())}
            <span class="score-sub">(${item.score}/10)</span>
          </span>
        </td>
        <td class="td-title">
          <strong>${escapeHtml(item.favored || "Não identificado")}</strong>
          ${movInfo}
        </td>
        <td>
          <div style="font-weight: 600; margin-bottom: 4px; color: var(--ink);">${escapeHtml(item.title || "-")}</div>
          <p class="audit-explanation">${escapeHtml(item.explanation || "-")}</p>
          ${evidenceHtml}
        </td>
        <td class="td-num"><strong>${finVal}</strong></td>
        <td class="link-column">${renderSourceAction(item)}</td>
      </tr>
    `;
  }).join("");

  updateAttentionPagination(total, state.attentionOffset, state.attentionLimit);
}

function updateAttentionPagination(total, offset, limit) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  const infoEl = byId("att-pagination-info");
  if (infoEl) {
    infoEl.textContent = `Mostrando ${formatNumber(start)}–${formatNumber(end)} de ${formatNumber(total)} pontos`;
  }

  const indicatorEl = byId("att-page-indicator");
  if (indicatorEl) {
    indicatorEl.textContent = `Página ${page} de ${totalPages}`;
  }

  const btnPrev = byId("att-btn-prev");
  if (btnPrev) btnPrev.disabled = offset <= 0;

  const btnNext = byId("att-btn-next");
  if (btnNext) btnNext.disabled = end >= total;
}

async function loadAttentionView() {
  if (state.attentionAbortController) {
    state.attentionAbortController.abort();
  }
  state.attentionAbortController = new AbortController();
  const signal = state.attentionAbortController.signal;

  const municipality = byId("att-municipality")?.value.trim() || "";
  const year = byId("att-year")?.value.trim() || "";
  const category = byId("att-category")?.value.trim() || "";
  const severity = byId("att-severity")?.value.trim() || "";
  const q = byId("att-query")?.value.trim() || "";

  const params = new URLSearchParams({
    limit: String(state.attentionLimit),
    offset: String(state.attentionOffset),
  });
  if (municipality) params.set("municipality", municipality);
  if (year) params.set("year", year);
  if (category) params.set("category", category);
  if (severity) params.set("severity", severity);
  if (q) params.set("q", q);

  try {
    const payload = await getJson(`/api/anomalies?${params.toString()}`, { signal });
    if (payload.error) throw new Error(payload.error);
    const items = payload.items || [];
    const total = payload.total ?? items.length;
    renderAttentionTable(items, total);
  } catch (err) {
    if (err.name === "AbortError") return;
    const body = byId("attention-body");
    if (body) body.innerHTML = `<tr><td class="empty-state" colspan="8">${escapeHtml(err.message || "Erro ao consultar pontos de revisão.")}</td></tr>`;
    const countEl = byId("att-count");
    if (countEl) countEl.textContent = "Dados indisponíveis";
  }
}

// -------------------------------------------------------------
// ABA 4: FORNECEDORES
// -------------------------------------------------------------

function renderSuppliersTable(favoredList) {
  const body = byId("suppliers-body");
  if (!body) return;
  if (!favoredList || !favoredList.length) {
    body.innerHTML = '<tr><td class="empty-state" colspan="7">Nenhum fornecedor encontrado para estes filtros.</td></tr>';
    return;
  }
  body.innerHTML = favoredList.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.favored)}</strong></td>
      <td>${escapeHtml(item.municipality)}</td>
      <td>${escapeHtml(item.year || "-")}</td>
      <td class="td-num">${formatNumber(item.movements_count)}</td>
      <td class="td-num">${formatCurrency(item.total_empenhado)}</td>
      <td class="td-num">${formatCurrency(item.total_liquidado)}</td>
      <td class="td-num"><strong>${formatCurrency(item.total_pago)}</strong></td>
    </tr>
  `).join("");
}

async function loadSuppliersView() {
  if (state.suppliersAbortController) {
    state.suppliersAbortController.abort();
  }
  state.suppliersAbortController = new AbortController();
  const signal = state.suppliersAbortController.signal;

  const municipality = byId("supp-municipality")?.value.trim() || "";
  const year = byId("supp-year")?.value.trim() || "";
  const q = byId("supp-query")?.value.trim() || "";

  const params = new URLSearchParams({ limit: "50" });
  if (municipality) params.set("municipality", municipality);
  if (year) params.set("year", year);
  if (q) params.set("q", q);

  try {
    const data = await getJson(`/api/expenses/summary?${params.toString()}`, { signal });
    renderSuppliersTable(data.top_favored || []);
    const countEl = byId("supp-count");
    if (countEl) {
      const len = (data.top_favored || []).length;
      countEl.textContent = `Exibindo os ${len} maiores fornecedores por volume empenhado`;
    }
  } catch (err) {
    if (err.name === "AbortError") return;
    const body = byId("suppliers-body");
    if (body) body.innerHTML = '<tr><td class="empty-state" colspan="7">Não foi possível carregar a lista de fornecedores.</td></tr>';
  }
}

// -------------------------------------------------------------
// EVENT LISTENERS E CONTROLES
// -------------------------------------------------------------

// Dashboard
byId("dash-refresh")?.addEventListener("click", loadDashboardView);
["dash-municipality", "dash-year", "dash-kind"].forEach((id) => {
  byId(id)?.addEventListener("change", loadDashboardView);
});
byId("dash-clear")?.addEventListener("click", () => {
  if (byId("dash-municipality")) byId("dash-municipality").value = "";
  if (byId("dash-year")) byId("dash-year").value = "";
  if (byId("dash-kind")) byId("dash-kind").value = "";
  loadDashboardView();
});

// Registros
byId("records-refresh")?.addEventListener("click", () => {
  state.recordsOffset = 0;
  loadRecordsView();
});
["records-municipality", "records-year", "records-kind"].forEach((id) => {
  byId(id)?.addEventListener("change", () => {
    state.recordsOffset = 0;
    loadRecordsView();
  });
});
["records-status", "records-query"].forEach((id) => {
  byId(id)?.addEventListener("input", () => {
    const spinner = byId("records-spinner");
    if (spinner) spinner.style.display = "inline";
    clearTimeout(state.recordsDebounceTimer);
    state.recordsDebounceTimer = setTimeout(() => {
      state.recordsOffset = 0;
      loadRecordsView().finally(() => {
        if (spinner) spinner.style.display = "none";
      });
    }, 300);
  });
});
byId("records-clear")?.addEventListener("click", () => {
  if (byId("records-municipality")) byId("records-municipality").value = "";
  if (byId("records-year")) byId("records-year").value = "";
  if (byId("records-kind")) byId("records-kind").value = "";
  if (byId("records-status")) byId("records-status").value = "";
  if (byId("records-query")) byId("records-query").value = "";
  state.recordsOffset = 0;
  loadRecordsView();
});
byId("records-btn-prev")?.addEventListener("click", () => {
  if (state.recordsOffset > 0) {
    state.recordsOffset = Math.max(0, state.recordsOffset - state.recordsLimit);
    loadRecordsView();
  }
});
byId("records-btn-next")?.addEventListener("click", () => {
  if (state.recordsOffset + state.recordsLimit < state.recordsTotal) {
    state.recordsOffset += state.recordsLimit;
    loadRecordsView();
  }
});

// Atenção
byId("att-refresh")?.addEventListener("click", () => {
  state.attentionOffset = 0;
  loadAttentionView();
});
["att-municipality", "att-year", "att-category", "att-severity"].forEach((id) => {
  byId(id)?.addEventListener("change", () => {
    state.attentionOffset = 0;
    loadAttentionView();
  });
});
byId("att-query")?.addEventListener("input", () => {
  const spinner = byId("att-spinner");
  if (spinner) spinner.style.display = "inline";
  clearTimeout(state.attentionDebounceTimer);
  state.attentionDebounceTimer = setTimeout(() => {
    state.attentionOffset = 0;
    loadAttentionView().finally(() => {
      if (spinner) spinner.style.display = "none";
    });
  }, 300);
});
byId("att-clear")?.addEventListener("click", () => {
  if (byId("att-municipality")) byId("att-municipality").value = "";
  if (byId("att-year")) byId("att-year").value = "";
  if (byId("att-category")) byId("att-category").value = "";
  if (byId("att-severity")) byId("att-severity").value = "";
  if (byId("att-query")) byId("att-query").value = "";
  state.attentionOffset = 0;
  loadAttentionView();
});
byId("att-btn-prev")?.addEventListener("click", () => {
  if (state.attentionOffset > 0) {
    state.attentionOffset = Math.max(0, state.attentionOffset - state.attentionLimit);
    loadAttentionView();
  }
});
byId("att-btn-next")?.addEventListener("click", () => {
  if (state.attentionOffset + state.attentionLimit < state.attentionTotal) {
    state.attentionOffset += state.attentionLimit;
    loadAttentionView();
  }
});

// Fornecedores
byId("supp-refresh")?.addEventListener("click", loadSuppliersView);
["supp-municipality", "supp-year"].forEach((id) => {
  byId(id)?.addEventListener("change", loadSuppliersView);
});
byId("supp-query")?.addEventListener("input", () => {
  const spinner = byId("supp-spinner");
  if (spinner) spinner.style.display = "inline";
  clearTimeout(state.suppliersDebounceTimer);
  state.suppliersDebounceTimer = setTimeout(() => {
    loadSuppliersView().finally(() => {
      if (spinner) spinner.style.display = "none";
    });
  }, 300);
});
byId("supp-clear")?.addEventListener("click", () => {
  if (byId("supp-municipality")) byId("supp-municipality").value = "";
  if (byId("supp-year")) byId("supp-year").value = "";
  if (byId("supp-query")) byId("supp-query").value = "";
  loadSuppliersView();
});

// Delegador global de cópia (chips e botões)
document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".btn-copy-chip, .copy-identifier-btn");
  if (!btn) return;
  const text = btn.getAttribute("data-copy");
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    const originalText = btn.textContent.trim();
    btn.classList.add("copied");
    btn.textContent = "✓ Copiado";
    setTimeout(() => {
      btn.classList.remove("copied");
      btn.textContent = originalText;
    }, 1500);
  } catch (err) {
    console.error("Falha ao copiar:", err);
  }
});

// -------------------------------------------------------------
// INICIALIZAÇÃO
// -------------------------------------------------------------
async function initApp() {
  await loadMetadata();
  switchTab(getCurrentTab());
}

initApp();
