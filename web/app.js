const state = {
  page: 1,
  pageSize: 50,
  totalRows: 0,
  map: null,
  markers: null,
  radiusLayer: null,
  optionsInitialized: false,
  selectedMarker: null,
  selectedLocation: null,
  radiusCenter: null,
  radiusRows: [],
  drawerView: null,
  mapRows: [],
  radiusMeters: 1000,
  refreshId: 0,
  rowsRefreshId: 0,
};

const $ = (selector) => document.querySelector(selector);
const fmt = new Intl.NumberFormat("pt-BR");

function paramsFromFilters() {
  const form = new FormData($("#filters"));
  const params = {};
  for (const [key, value] of form.entries()) {
    const text = String(value).trim();
    if (text) params[key] = text;
  }
  return params;
}

async function api(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "")
      url.searchParams.set(key, value);
  });
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Erro na consulta");
  return payload;
}

function normalizeText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

const combos = new Map();

function setupCombo(name) {
  const root = document.querySelector(`[data-combo="${name}"]`);
  const input = root.querySelector(".combo-input");
  const hidden = root.querySelector('input[type="hidden"]');
  const list = root.querySelector(".combo-list");
  const combo = {
    root,
    input,
    hidden,
    list,
    options: [],
    filtered: [],
    active: -1,
    emptyLabel: "",
  };
  combos.set(name, combo);

  input.addEventListener("input", () => {
    openCombo(combo, input.value);
  });
  input.addEventListener("focus", () => openCombo(combo, ""));
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveComboActive(combo, event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Enter") {
      if (!list.hidden && combo.active >= 0) {
        event.preventDefault();
        selectComboValue(combo, combo.filtered[combo.active].value);
      }
    } else if (event.key === "Escape") {
      closeCombo(combo);
      syncComboText(combo);
    }
  });
  input.addEventListener("click", () => openCombo(combo, ""));
  input.addEventListener("blur", () => {
    setTimeout(() => {
      closeCombo(combo);
      syncComboText(combo);
    }, 150);
  });
  list.addEventListener("mousedown", (event) => {
    const button = event.target.closest("[data-value]");
    if (!button) return;
    event.preventDefault();
    selectComboValue(combo, button.dataset.value);
  });
  return combo;
}

function setupCombos() {
  ["cargo", "municipio", "bairro", "candidato", "tipo"].forEach(setupCombo);
}

function syncComboText(combo) {
  const match = combo.options.find((item) => item.value === combo.hidden.value);
  combo.input.value = match ? match.label : "";
  combo.input.placeholder = combo.emptyLabel;
}

function closeCombo(combo) {
  combo.list.hidden = true;
  combo.list.innerHTML = "";
  combo.active = -1;
}

function openCombo(combo, query) {
  const text = normalizeText(query);
  const matches = text
    ? combo.options.filter((item) => normalizeText(item.label).includes(text))
    : [{ value: "", label: combo.emptyLabel }].concat(combo.options);
  const capped = matches.slice(0, 300);
  combo.filtered = capped;
  combo.active = -1;

  if (!capped.length) {
    combo.list.innerHTML =
      '<div class="combo-empty">Nenhuma opção encontrada.</div>';
    combo.list.hidden = false;
    return;
  }

  combo.list.innerHTML = capped
    .map(
      (item, index) => `
        <button type="button" class="combo-option${index === 0 ? " active" : ""}" data-value="${escapeHtml(item.value)}">
          ${escapeHtml(item.label)}
        </button>`,
    )
    .join("");
  combo.active = 0;
  combo.list.hidden = false;
}

function moveComboActive(combo, delta) {
  if (combo.list.hidden) {
    openCombo(combo, combo.input.value);
    return;
  }
  if (!combo.filtered.length) return;
  combo.active =
    (combo.active + delta + combo.filtered.length) % combo.filtered.length;
  combo.list.querySelectorAll(".combo-option").forEach((element, index) => {
    element.classList.toggle("active", index === combo.active);
    if (index === combo.active) element.scrollIntoView({ block: "nearest" });
  });
}

function selectComboValue(combo, value) {
  if (value !== combo.hidden.value) {
    combo.hidden.value = value;
    combo.hidden.dispatchEvent(new Event("change", { bubbles: true }));
  }
  syncComboText(combo);
  closeCombo(combo);
}

function fillCombo(name, rows, emptyLabel, getValue, getLabel) {
  const combo = combos.get(name);
  combo.emptyLabel = emptyLabel;
  combo.options = rows.map((row) => ({
    value: String(getValue(row)),
    label: String(getLabel(row)),
  }));
  const current = combo.hidden.value;
  const match = combo.options.find((item) => item.value === current);
  if (!match) combo.hidden.value = "";
  combo.input.placeholder = emptyLabel;
  syncComboText(combo);
}

function setComboValue(name, value) {
  const combo = combos.get(name);
  combo.hidden.value = value;
  syncComboText(combo);
}

function renderCards(totals) {
  const cards = [
    ["Votos", totals.votos],
    ["Linhas", totals.linhas],
    ["Municípios", totals.municipios],
    ["Locais", totals.locais],
    ["Seções", totals.secoes],
  ];
  $("#cards").innerHTML = cards
    .map(
      ([label, value]) =>
        `<article class="card"><span>${label}</span><strong>${fmt.format(value || 0)}</strong></article>`,
    )
    .join("");
}

function rankTitle(row, group) {
  if (group === "candidato")
    return `${row.nome || "Sem nome"} ${row.numero ? `(${row.numero})` : ""}`;
  if (group === "bairro") return row.bairro || "Sem bairro";
  if (group === "local") return row.local_nome || "Sem local";
  if (group === "secao")
    return `Zona ${row.zona || "-"} / Seção ${row.secao || "-"}`;
  if (group === "tipo") return row.tipo_voto || "Sem tipo";
  return row.municipio || "Sem município";
}

function rankSubtitle(row, group) {
  const pieces = [];
  if (group === "candidato") pieces.push(row.cargo, row.partido, row.tipo_voto);
  if (group === "bairro") pieces.push(row.municipio);
  if (group === "local") pieces.push(row.municipio, row.bairro, row.endereco);
  if (group === "secao") pieces.push(row.municipio, row.bairro, row.local_nome);
  return pieces.filter(Boolean).join(" · ");
}

function renderRanking(payload) {
  const rows = payload.rows || [];
  const max = Math.max(...rows.map((row) => row.votos || 0), 1);
  if (!rows.length) {
    $("#ranking").innerHTML =
      '<div class="empty">Nenhum resultado para os filtros atuais.</div>';
    return;
  }
  $("#ranking").innerHTML = rows
    .map((row) => {
      const width = Math.max(2, ((row.votos || 0) / max) * 100);
      return `
        <div class="rank-row">
          <div class="rank-label">
            <strong>${escapeHtml(rankTitle(row, payload.group))}</strong>
            <span>${escapeHtml(rankSubtitle(row, payload.group))}</span>
          </div>
          <strong>${fmt.format(row.votos || 0)}</strong>
          <div class="bar"><i style="width:${width}%"></i></div>
        </div>`;
    })
    .join("");
}

function renderRows(payload) {
  state.totalRows = payload.total || 0;
  const totalPages = Math.max(1, Math.ceil(state.totalRows / state.pageSize));
  $("#pageInfo").textContent =
    `Página ${state.page} de ${fmt.format(totalPages)} · ${fmt.format(state.totalRows)} linhas`;
  $("#prevPage").disabled = state.page <= 1;
  $("#nextPage").disabled = state.page >= totalPages;

  $("#rows").innerHTML = (payload.rows || [])
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.cargo)}</td>
        <td><strong>${escapeHtml(row.nome || "")}</strong><small>${escapeHtml([row.numero, row.partido, row.tipo_voto].filter(Boolean).join(" · "))}</small></td>
        <td><strong>${fmt.format(row.votos || 0)}</strong></td>
        <td>${escapeHtml(row.municipio)}</td>
        <td>${escapeHtml(row.bairro)}</td>
        <td>${escapeHtml(row.local_nome)}<small>${escapeHtml(row.endereco || "")}</small></td>
        <td>${escapeHtml(row.zona || "-")} / ${escapeHtml(row.secao || "-")}</td>
      </tr>`,
    )
    .join("");
}

function setRowsLoading(isLoading) {
  $(".table-panel").classList.toggle("table-loading", isLoading);
  $("#prevPage").disabled = isLoading || state.page <= 1;
  const totalPages = Math.max(1, Math.ceil(state.totalRows / state.pageSize));
  $("#nextPage").disabled = isLoading || state.page >= totalPages;
}

async function refreshRowsOnly() {
  const params = paramsFromFilters();
  const rowsRefreshId = ++state.rowsRefreshId;
  setRowsLoading(true);

  try {
    const rows = await api("/api/rows", {
      ...params,
      page: state.page,
      page_size: state.pageSize,
    });
    if (rowsRefreshId !== state.rowsRefreshId) return;
    renderRows(rows);
  } catch (error) {
    if (rowsRefreshId !== state.rowsRefreshId) return;
    $("#pageInfo").textContent = error.message;
  } finally {
    if (rowsRefreshId === state.rowsRefreshId) setRowsLoading(false);
  }
}

function setupMap() {
  if (!window.L || state.map) return;
  state.map = L.map("map", { scrollWheelZoom: true }).setView(
    [-22.9, -43.2],
    8,
  );
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "&copy; OpenStreetMap",
  }).addTo(state.map);
  state.markers = L.layerGroup().addTo(state.map);
  state.radiusLayer = L.layerGroup().addTo(state.map);
  state.map.on("click", (event) => openRadiusAt(event.latlng));
}

function renderMap(payload) {
  setupMap();
  const rows = payload.rows || [];
  state.mapRows = rows;
  $("#mapStatus").textContent = `${fmt.format(rows.length)} pontos`;
  if (!state.map || !state.markers) {
    $("#mapStatus").textContent = "Mapa indisponível";
    return;
  }
  state.markers.clearLayers();
  state.radiusLayer.clearLayers();
  state.selectedMarker = null;
  state.selectedLocation = null;
  state.radiusCenter = null;
  state.radiusRows = [];
  state.drawerView = null;
  const bounds = [];
  const max = Math.max(...rows.map((row) => row.votos || 0), 1);

  rows.forEach((row) => {
    if (row.latitude == null || row.longitude == null) return;
    const radius = markerBaseRadius(row, max);
    const marker = L.circleMarker([row.latitude, row.longitude], {
      radius,
      color: "#1357a6",
      fillColor: "#1357a6",
      fillOpacity: 0.48,
      weight: 1.5,
    });
    row._marker = marker;
    row._baseRadius = radius;
    row._maxVotes = max;
    marker.on("click", (event) => {
      if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);
      openLocationDetail(row, marker);
    });
    marker.bindTooltip(
      `${row.local_nome || "Local"}<br>${fmt.format(row.votos || 0)} votos`,
      { sticky: true },
    );
    marker.addTo(state.markers);
    bounds.push([row.latitude, row.longitude]);
  });

  if (bounds.length)
    state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
}

function markerBaseRadius(row, maxVotes) {
  return 2.5 + Math.sqrt((row.votos || 0) / maxVotes) * 6;
}

function distanceMeters(a, b) {
  const toRad = (value) => (value * Math.PI) / 180;
  const earth = 6371000;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const lat1 = toRad(a.latitude);
  const lat2 = toRad(b.latitude);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * earth * Math.asin(Math.sqrt(h));
}

function applyRadiusHighlight() {
  if (!state.map || !state.radiusLayer) return [];
  state.radiusLayer.clearLayers();
  const center = state.radiusCenter;
  let inside = 0;
  const insideRows = [];
  if (center) {
    state.radiusLayer.addLayer(
      L.circle([center.latitude, center.longitude], {
        radius: state.radiusMeters,
        color: "#1357a6",
        fillColor: "#1357a6",
        fillOpacity: 0.07,
        dashArray: "8 8",
        weight: 1.5,
        interactive: false,
      }),
    );
  }

  state.mapRows.forEach((row) => {
    if (!row._marker) return;
    const isSelected = row === state.selectedLocation;
    const isInside = center
      ? distanceMeters(center, row) <= state.radiusMeters
      : false;
    if (isInside) {
      inside += 1;
      row.distance = distanceMeters(center, row);
      insideRows.push(row);
    }

    if (isSelected) {
      row._marker.setRadius(10);
      row._marker.setStyle({
        fillColor: "#111",
        color: "#111",
        fillOpacity: 0.9,
        weight: 2,
      });
    } else if (isInside) {
      row._marker.setRadius(Math.max(8, row._baseRadius * 1.8));
      row._marker.setStyle({
        fillColor: "#f28c28",
        color: "#0b3f82",
        fillOpacity: 0.78,
        weight: 2,
      });
    } else {
      row._marker.setRadius(Math.max(2.2, row._baseRadius * 0.72));
      row._marker.setStyle({
        fillColor: "#1357a6",
        color: "#1357a6",
        fillOpacity: 0.28,
        weight: 1,
      });
    }
  });
  $("#mapStatus").textContent = center
    ? `${fmt.format(state.mapRows.length)} pontos · ${fmt.format(inside)} no raio`
    : `${fmt.format(state.mapRows.length)} pontos`;
  return insideRows.sort((a, b) => a.distance - b.distance);
}

function resetRadiusHighlight() {
  if (state.radiusLayer) state.radiusLayer.clearLayers();
  state.mapRows.forEach((row) => {
    if (!row._marker) return;
    row._marker.setRadius(row._baseRadius || 4);
    row._marker.setStyle({
      fillColor: "#1357a6",
      color: "#1357a6",
      fillOpacity: 0.48,
      weight: 1.5,
    });
  });
  $("#mapStatus").textContent = `${fmt.format(state.mapRows.length)} pontos`;
}

function openDrawer() {
  document.body.classList.add("drawer-open");
  $("#locationDrawer").setAttribute("aria-hidden", "false");
}

function openRadiusAt(latlng) {
  state.selectedMarker = null;
  state.selectedLocation = null;
  state.radiusCenter = { latitude: latlng.lat, longitude: latlng.lng };
  const insideRows = applyRadiusHighlight();
  state.drawerView = "radius";
  openDrawer();
  renderRadiusResults(insideRows);
}

async function openLocationDetail(row, marker) {
  state.selectedMarker = marker;
  state.selectedLocation = row;
  if (!state.radiusCenter) {
    state.radiusCenter = { latitude: row.latitude, longitude: row.longitude };
  }
  const insideRows = applyRadiusHighlight();
  if (state.drawerView === "radius") state.radiusRows = insideRows;
  state.drawerView = "detail";
  openDrawer();
  $("#locationDetail").innerHTML =
    '<div class="empty">Carregando local...</div>';

  try {
    const payload = await api("/api/location", {
      cargo: "Governador",
      supported: "55",
      municipio: row.municipio,
      local_votacao: row.local_votacao,
      local_nome: row.local_nome,
    });
    renderLocationDetail(payload);
  } catch (error) {
    $("#locationDetail").innerHTML =
      `<div class="error">${escapeHtml(error.message)}</div>`;
  }
}

function closeLocationDetail() {
  document.body.classList.remove("drawer-open");
  $("#locationDrawer").setAttribute("aria-hidden", "true");
  resetRadiusHighlight();
  state.selectedMarker = null;
  state.selectedLocation = null;
  state.radiusCenter = null;
  state.radiusRows = [];
  state.drawerView = null;
}

function renderRadiusResults(rows) {
  state.radiusRows = rows;
  state.drawerView = "radius";
  const totalVotes = rows.reduce((sum, row) => sum + (row.votos || 0), 0);
  $("#locationDetail").innerHTML = `
    <button type="button" class="back-link" id="backToMap">‹ Limpar raio</button>
    <h2 class="drawer-title">Locais dentro do raio</h2>
    <p class="drawer-address">Raio atual: ${fmt.format(state.radiusMeters)} metros.</p>
    <p class="big-number"><strong>${fmt.format(rows.length)}</strong> locais de votação encontrados.</p>
    <div class="callout">
      <p>Esses locais somam <strong>${fmt.format(totalVotes)}</strong> votos no filtro atual. Clique em um local da lista ou em um ponto do mapa para trocar automaticamente o detalhe lateral.</p>
    </div>
    <div class="radius-list">
      ${rows.slice(0, 80).map(renderRadiusLocation).join("") || '<div class="empty">Nenhum local encontrado dentro deste raio.</div>'}
    </div>
  `;
  $("#backToMap").addEventListener("click", closeLocationDetail);
  document.querySelectorAll("[data-location-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = rows[Number(button.dataset.locationIndex)];
      if (row) openLocationDetail(row, row._marker);
    });
  });
}

function renderRadiusLocation(row, index) {
  return `
    <button type="button" class="radius-location" data-location-index="${index}">
      <strong>${escapeHtml(row.local_nome || "Local de votação")}</strong>
      <span>${escapeHtml([row.bairro, row.municipio].filter(Boolean).join(" · "))}</span>
      <small>${fmt.format(Math.round(row.distance || 0))} m · ${fmt.format(row.votos || 0)} votos</small>
    </button>
  `;
}

function renderLocationDetail(payload) {
  const info = payload.info || {};
  const supported = payload.supported || {};
  const opponent = payload.main_opponent;
  const totals = payload.totals || {};
  const margin = totals.margem || 0;
  const marginText =
    margin >= 0
      ? `${fmt.format(margin)} votos de vantagem`
      : `${fmt.format(Math.abs(margin))} votos atrás`;
  const opponentText = opponent
    ? `${escapeHtml(opponent.nome)} (${opponent.numero}) tem ${fmt.format(opponent.votos || 0)} votos, ${fmt.format(Math.abs(margin))} ${margin >= 0 ? "a menos" : "a mais"}.`
    : "Não há adversário nominal neste local.";
  const share = Number(supported.share || 0).toLocaleString("pt-BR", {
    maximumFractionDigits: 1,
  });
  const progress = Math.max(1, Math.min(100, supported.share || 0));

  const backTarget = state.radiusRows.length
    ? `<button type="button" class="back-link" id="backToMap">‹ Voltar para locais do raio</button>`
    : `<button type="button" class="back-link" id="backToMap">‹ Voltar para o mapa</button>`;

  $("#locationDetail").innerHTML = `
    ${backTarget}
    <h2 class="drawer-title">${escapeHtml(info.local_nome || "Local de votação")}</h2>
    <p class="drawer-address">${escapeHtml([info.bairro, info.municipio, "RJ"].filter(Boolean).join(", "))}${info.endereco ? ` · ${escapeHtml(info.endereco)}` : ""}</p>

    <p class="big-number"><strong>${fmt.format(totals.votos || 0)}</strong> votos para governador nessas seções.</p>

    <h3>Dá pra tentar virar até <em>${fmt.format(totals.conversaveis || 0)} votos</em> para Eduardo Paes.</h3>
    <p class="summary-line">${fmt.format(totals.nulos || 0)} nulos, ${fmt.format(totals.brancos || 0)} em branco e ${fmt.format(totals.outros_candidatos || 0)} em outros candidatos fora do principal adversário.</p>

    <div class="share-block">
      <strong>Eduardo Paes neste local teve <em>${share}%</em> <span>(${fmt.format(supported.votos || 0)} votos)</span></strong>
      <div class="share-track"><i style="width:${progress}%"></i></div>
      <small>votos válidos e não válidos registrados no CSV para governador.</small>
    </div>

    <div class="callout">
      <p>No primeiro turno, Eduardo Paes ficou com <strong>${marginText}</strong> aqui. ${opponentText}</p>
    </div>

    <p class="drawer-note">Local com ${fmt.format(totals.secoes || 0)} seções agregadas no arquivo.</p>

    <h3>O que dá pra conversar aqui</h3>
    <div class="conversation-list">
      ${(payload.conversations || []).slice(0, 10).map(renderConversation).join("") || '<div class="empty">Sem grupos relevantes fora do Paes neste local.</div>'}
    </div>

    <h3>Resultado por candidato</h3>
    <div class="mini-results">
      ${(payload.candidates || [])
        .slice(0, 12)
        .map((candidate) => renderCandidateLine(candidate, totals.votos || 1))
        .join("")}
    </div>
  `;
  $("#backToMap").addEventListener("click", () => {
    if (state.radiusRows.length) {
      state.selectedMarker = null;
      state.selectedLocation = null;
      applyRadiusHighlight();
      renderRadiusResults(state.radiusRows);
    } else {
      closeLocationDetail();
    }
  });
}

function renderConversation(item) {
  return `
    <details class="conversation-card">
      <summary><strong>${escapeHtml(item.title)}</strong> <span>(${fmt.format(item.votes || 0)})</span></summary>
      <p>Grupo priorizado para abordagem local. Cada voto convertido soma para Eduardo Paes e reduz o espaço dos adversários.</p>
    </details>
  `;
}

function renderCandidateLine(candidate, total) {
  const votes = candidate.votos || 0;
  const pct = Math.max(1, (votes / total) * 100);
  const label =
    candidate.tipo_voto === "nominal"
      ? `${candidate.nome || "Sem nome"} ${candidate.numero ? `(${candidate.numero})` : ""}`
      : candidate.nome;
  return `
    <div class="candidate-line">
      <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml([candidate.partido, candidate.tipo_voto].filter(Boolean).join(" · "))}</span></div>
      <b>${fmt.format(votes)}</b>
      <i style="width:${pct}%"></i>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadOptions() {
  const params = paramsFromFilters();
  const payload = await api("/api/options", {
    cargo: params.cargo,
    municipio: params.municipio,
  });
  fillCombo(
    "cargo",
    payload.cargos,
    "Todos os cargos",
    (row) => row.cargo,
    (row) => `${row.cargo} · ${fmt.format(row.votos)} votos`,
  );
  if (!state.optionsInitialized && !params.cargo) {
    const defaultCargo =
      payload.cargos.find((row) => row.cargo === "Governador") ||
      payload.cargos[0];
    if (defaultCargo) setComboValue("cargo", defaultCargo.cargo);
  }
  fillCombo(
    "municipio",
    payload.municipios,
    "Todos os municípios",
    (row) => row,
    (row) => row,
  );
  fillCombo(
    "bairro",
    payload.bairros,
    "Todos os bairros",
    (row) => row,
    (row) => row,
  );
  fillCombo(
    "candidato",
    payload.candidatos,
    "Todos os candidatos",
    (row) => row.numero,
    (row) =>
      `${row.nome || "Sem nome"} (${row.numero})${row.partido ? ` · ${row.partido}` : ""}`,
  );
  fillCombo(
    "tipo",
    payload.tipos,
    "Todos os tipos",
    (row) => row,
    (row) => row,
  );
  state.optionsInitialized = true;
}

async function refreshAll() {
  const params = paramsFromFilters();
  const group = $("#group").value;
  const refreshId = ++state.refreshId;
  state.rowsRefreshId += 1;
  $("#ranking").innerHTML = '<div class="empty">Carregando ranking...</div>';
  $("#mapStatus").textContent = "Carregando...";

  try {
    const mapPromise = api("/api/map", { ...params, limit: 6000 });
    const [overview, ranking, rows] = await Promise.all([
      api("/api/overview", params),
      api("/api/summary", { ...params, group, limit: 25 }),
      api("/api/rows", {
        ...params,
        page: state.page,
        page_size: state.pageSize,
      }),
    ]);
    if (refreshId !== state.refreshId) return;
    renderCards(overview.totals);
    renderRanking(ranking);
    renderRows(rows);

    const map = await mapPromise;
    if (refreshId !== state.refreshId) return;
    renderMap(map);
  } catch (error) {
    if (refreshId !== state.refreshId) return;
    $("#ranking").innerHTML =
      `<div class="error">${escapeHtml(error.message)}</div>`;
    $("#cards").innerHTML = "";
    $("#rows").innerHTML = "";
    $("#mapStatus").textContent = "Erro";
  }
}

async function init() {
  setupCombos();
  setupMap();
  await loadOptions();
  await loadOptions();
  await refreshAll();

  $("#filters").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.page = 1;
    await loadOptions();
    await refreshAll();
  });

  ["#cargo", "#municipio"].forEach((selector) => {
    $(selector).addEventListener("change", async () => {
      state.page = 1;
      await loadOptions();
      await refreshAll();
    });
  });

  ["#bairro", "#candidato", "#tipo"].forEach((selector) => {
    $(selector).addEventListener("change", async () => {
      state.page = 1;
      await refreshAll();
    });
  });

  $("#group").addEventListener("change", refreshAll);
  $("#clearFilters").addEventListener("click", async () => {
    $("#filters").reset();
    state.optionsInitialized = false;
    state.page = 1;
    await loadOptions();
    await loadOptions();
    await refreshAll();
  });
  $("#radiusMeters").addEventListener("change", () => {
    state.radiusMeters = Number($("#radiusMeters").value) || 1000;
    if (!state.radiusCenter) return;
    const insideRows = applyRadiusHighlight();
    if (state.drawerView === "radius") renderRadiusResults(insideRows);
    else state.radiusRows = insideRows;
  });
  $("#closeDrawer").addEventListener("click", closeLocationDetail);
  $("#prevPage").addEventListener("click", async () => {
    state.page = Math.max(1, state.page - 1);
    await refreshRowsOnly();
  });
  $("#nextPage").addEventListener("click", async () => {
    state.page += 1;
    await refreshRowsOnly();
  });
}

init();
