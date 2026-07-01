const state = {
  markets: [],
  signals: [],
  events: [],
  virtualAccount: null,
  virtualTrades: [],
  selectedSymbol: null,
  brokerEnabled: false,
  candles: [],
};

const els = {
  statusLine: document.querySelector("#statusLine"),
  modePill: document.querySelector("#modePill"),
  publicWs: document.querySelector("#publicWs"),
  brokerState: document.querySelector("#brokerState"),
  supabaseState: document.querySelector("#supabaseState"),
  telegramState: document.querySelector("#telegramState"),
  engineState: document.querySelector("#engineState"),
  virtualBalance: document.querySelector("#virtualBalance"),
  virtualTargets: document.querySelector("#virtualTargets"),
  virtualBankruptcies: document.querySelector("#virtualBankruptcies"),
  marketList: document.querySelector("#marketList"),
  eventList: document.querySelector("#eventList"),
  signalRows: document.querySelector("#signalRows"),
  virtualRows: document.querySelector("#virtualRows"),
  discoverBtn: document.querySelector("#discoverBtn"),
  refreshBtn: document.querySelector("#refreshBtn"),
  telegramBtn: document.querySelector("#telegramBtn"),
  brokerToggleBtn: document.querySelector("#brokerToggleBtn"),
  scanBtn: document.querySelector("#scanBtn"),
  saveVirtualBtn: document.querySelector("#saveVirtualBtn"),
  initialBalanceInput: document.querySelector("#initialBalanceInput"),
  balanceInput: document.querySelector("#balanceInput"),
  stakeInput: document.querySelector("#stakeInput"),
  targetInput: document.querySelector("#targetInput"),
  chartTitle: document.querySelector("#chartTitle"),
  marketSearch: document.querySelector("#marketSearch"),
  marketFilter: document.querySelector("#marketFilter"),
  chart: document.querySelector("#chart"),
};

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function refresh() {
  const [health, appState] = await Promise.all([getJson("/health"), getJson("/api/state")]);
  els.statusLine.textContent = `Versión ${health.version} · estrategia ${health.strategy_version}`;
  els.modePill.textContent = health.deriv_account_mode || "DEMO";
  els.publicWs.textContent = health.public_ws.connected ? `${health.public_ws.latency_ms} ms` : "sin conexión";
  els.brokerState.textContent = health.broker_trading_enabled ? "ON" : "OFF";
  els.supabaseState.textContent = health.supabase.connected ? "remoto" : health.supabase.configured ? "pendiente/local" : "local";
  els.telegramState.textContent = health.telegram.configured ? "configurado" : "sin token";
  els.engineState.textContent = health.live_engine.enabled ? "ON" : "OFF";
  state.brokerEnabled = Boolean(health.broker_trading_enabled);
  els.brokerToggleBtn.textContent = state.brokerEnabled ? "Desactivar broker" : "Activar broker";
  state.markets = appState.markets || [];
  state.signals = appState.signals || [];
  state.events = appState.events || [];
  state.virtualAccount = appState.virtual_account;
  state.virtualTrades = appState.virtual_trades || [];
  if (!state.selectedSymbol && state.markets.length) {
    const enabled = state.markets.find((market) => market.enabled);
    state.selectedSymbol = enabled?.symbol || state.markets[0].symbol;
  }
  updateVirtualControls();
  renderMarkets();
  renderEvents();
  renderSignals();
  renderVirtualTrades();
  await loadCandlesForSelected();
}

function renderMarkets() {
  const query = els.marketSearch.value.trim().toLowerCase();
  const filter = els.marketFilter.value;
  const items = state.markets.filter((market) => {
    const matchesQuery = !query || `${market.symbol} ${market.display_name}`.toLowerCase().includes(query);
    const matchesFilter =
      filter === "all" || (filter === "enabled" && market.enabled) || (filter === "blocked" && !market.enabled);
    return matchesQuery && matchesFilter;
  });
  els.marketList.innerHTML = items.length
    ? items
        .map(
          (market) => `
      <div class="market-item ${market.symbol === state.selectedSymbol ? "selected" : ""}" data-symbol="${escapeHtml(market.symbol)}">
        <strong>${escapeHtml(market.symbol)} · ${escapeHtml(market.display_name || "")}</strong>
        <span class="muted">${escapeHtml(market.market || "")} ${escapeHtml(market.submarket || "")}</span>
        <span class="tag ${market.enabled ? "good" : "bad"}">${market.enabled ? "habilitado" : market.blocked_reason || "bloqueado"}</span>
        <span class="muted">Duración: ${market.duration || "--"}${market.duration_unit || ""} · Mapping: ${
            market.mapping_verified ? "verificado" : "pendiente"
          }</span>
      </div>`,
        )
        .join("")
    : `<div class="muted">Sin catálogo local. Ejecuta descubrimiento de mercados.</div>`;
}

function renderEvents() {
  els.eventList.innerHTML = state.events.length
    ? state.events
        .slice()
        .reverse()
        .map(
          (event) => `
      <div class="event-item">
        <strong>${escapeHtml(event.event_type || "")}</strong>
        <span class="muted">${escapeHtml(event.signal_id || event.asset || "sistema")}</span>
        <span class="muted">${escapeHtml(event.occurred_at || "")}</span>
      </div>`,
        )
        .join("")
    : `<div class="muted">Aún no hay eventos canónicos.</div>`;
}

function renderSignals() {
  els.signalRows.innerHTML = state.signals.length
    ? state.signals
        .slice()
        .reverse()
        .map(
          (signal) => `
      <tr>
        <td>${escapeHtml(signal.signal_id)}</td>
        <td>${escapeHtml(signal.asset)}</td>
        <td>${escapeHtml(signal.direction)}</td>
        <td>${escapeHtml(signal.contract_type)}</td>
        <td>${escapeHtml(signal.status)}</td>
        <td>${escapeHtml(String(signal.score))}</td>
      </tr>`,
        )
        .join("")
    : `<tr><td colspan="6" class="muted">Sin señales todavía.</td></tr>`;
}

function renderVirtualTrades() {
  els.virtualRows.innerHTML = state.virtualTrades.length
    ? state.virtualTrades
        .slice()
        .reverse()
        .map(
          (trade) => `
      <tr>
        <td>${escapeHtml(trade.signal_id)}</td>
        <td>${escapeHtml(trade.asset)}</td>
        <td>${escapeHtml(trade.direction)}</td>
        <td>$${formatMoney(trade.stake)}</td>
        <td>$${formatMoney(trade.payout)}</td>
        <td>${escapeHtml(trade.status)}</td>
        <td>${escapeHtml(trade.outcome || "--")}</td>
      </tr>`,
        )
        .join("")
    : `<tr><td colspan="7" class="muted">Sin operaciones virtuales todavía.</td></tr>`;
}

function updateVirtualControls() {
  const account = state.virtualAccount;
  if (!account) return;
  els.virtualBalance.textContent = `$${formatMoney(account.balance)}`;
  els.virtualTargets.textContent = String(account.target_hits || 0);
  els.virtualBankruptcies.textContent = String(account.bankruptcies || 0);
  els.initialBalanceInput.value = account.initial_balance;
  els.balanceInput.value = account.balance;
  els.stakeInput.value = account.stake;
  els.targetInput.value = account.target_balance;
}

async function loadCandlesForSelected() {
  if (!state.selectedSymbol) {
    drawMockChart();
    return;
  }
  els.chartTitle.textContent = `· ${state.selectedSymbol}`;
  try {
    const payload = await getJson(`/api/markets/${encodeURIComponent(state.selectedSymbol)}/candles?granularity=60&count=120`);
    state.candles = payload.items || [];
    drawCandles(state.candles);
  } catch {
    drawMockChart();
  }
}

function drawCandles(candles) {
  if (!candles.length) {
    drawMockChart();
    return;
  }
  const canvas = els.chart;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fbfcfd";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#e4e7ec";
  ctx.lineWidth = 1;
  for (let y = 40; y < height; y += 40) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  const max = Math.max(...candles.map((c) => c.high));
  const min = Math.min(...candles.map((c) => c.low));
  const scale = (value) => height - 26 - ((value - min) / (max - min || 1)) * (height - 52);
  const step = width / candles.length;
  candles.forEach((candle, index) => {
    const x = index * step + step / 2;
    const open = scale(candle.open);
    const close = scale(candle.close);
    const high = scale(candle.high);
    const low = scale(candle.low);
    const bullish = candle.close >= candle.open;
    ctx.strokeStyle = bullish ? "#15803d" : "#b42318";
    ctx.fillStyle = bullish ? "#22c55e" : "#ef4444";
    ctx.beginPath();
    ctx.moveTo(x, high);
    ctx.lineTo(x, low);
    ctx.stroke();
    const top = Math.min(open, close);
    const bodyHeight = Math.max(3, Math.abs(close - open));
    ctx.fillRect(x - Math.max(3, step * 0.28), top, Math.max(6, step * 0.56), bodyHeight);
  });
}

function drawMockChart() {
  drawCandles(makeCandles(42));
}

function makeCandles(count) {
  let price = 100;
  return Array.from({ length: count }, (_, index) => {
    const drift = Math.sin(index / 4) * 0.45 + (Math.random() - 0.5) * 0.7;
    const open = price;
    const close = open + drift;
    const high = Math.max(open, close) + 0.2 + Math.random() * 0.45;
    const low = Math.min(open, close) - 0.2 - Math.random() * 0.45;
    price = close;
    return { open, close, high, low };
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatMoney(value) {
  return Number(value || 0).toFixed(2);
}

els.discoverBtn.addEventListener("click", async () => {
  els.discoverBtn.disabled = true;
  try {
    await getJson("/api/deriv/market-discovery", { method: "POST" });
    await refresh();
  } finally {
    els.discoverBtn.disabled = false;
  }
});
els.refreshBtn.addEventListener("click", refresh);
els.marketList.addEventListener("click", async (event) => {
  const item = event.target.closest(".market-item");
  if (!item) return;
  state.selectedSymbol = item.dataset.symbol;
  renderMarkets();
  await loadCandlesForSelected();
});
els.marketSearch.addEventListener("input", renderMarkets);
els.marketFilter.addEventListener("change", renderMarkets);
els.scanBtn.addEventListener("click", async () => {
  els.scanBtn.disabled = true;
  try {
    await getJson("/api/live/scan-once", { method: "POST" });
    await refresh();
  } finally {
    els.scanBtn.disabled = false;
  }
});
els.saveVirtualBtn.addEventListener("click", async () => {
  els.saveVirtualBtn.disabled = true;
  try {
    await getJson("/api/virtual-account/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initial_balance: Number(els.initialBalanceInput.value),
        balance: Number(els.balanceInput.value),
        stake: Number(els.stakeInput.value),
        target_balance: Number(els.targetInput.value),
      }),
    });
    await refresh();
  } finally {
    els.saveVirtualBtn.disabled = false;
  }
});
els.brokerToggleBtn.addEventListener("click", async () => {
  els.brokerToggleBtn.disabled = true;
  try {
    await getJson("/api/broker/trading", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !state.brokerEnabled }),
    });
  } catch (error) {
    els.statusLine.textContent = `Broker bloqueado: ${error.message}`;
  } finally {
    els.brokerToggleBtn.disabled = false;
    await refresh();
  }
});
els.telegramBtn.addEventListener("click", async () => {
  els.telegramBtn.disabled = true;
  try {
    await getJson("/api/telegram/test", { method: "POST" });
    els.telegramBtn.textContent = "Telegram enviado";
  } catch {
    els.telegramBtn.textContent = "Telegram falló";
  } finally {
    setTimeout(() => {
      els.telegramBtn.disabled = false;
      els.telegramBtn.textContent = "Probar Telegram";
    }, 2200);
  }
});

refresh().catch((error) => {
  els.statusLine.textContent = `Error cargando estado: ${error.message}`;
  drawMockChart();
});

setInterval(() => {
  refresh().catch(() => {});
}, 30000);
