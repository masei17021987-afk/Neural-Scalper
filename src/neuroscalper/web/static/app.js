'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  status: null,
  history: { logs: [], decisions: [], signals: [], trades: [], strategies: [] },
  page: 'dashboard',
  journal: 'logs',
  help: localStorage.getItem('neuroscalper-help') !== 'off',
  settingsHydrated: false,
  apiDownShown: false,
  latestBacktest: null,
};

const pageMeta = {
  dashboard: ['Главная', 'Всё необходимое для безопасного первого запуска.'],
  data: ['Рынок и данные', 'Публичный поток, локальный стакан и запись истории.'],
  model: ['Нейросеть', 'Обучение и состояние RiskAwareLOBNet.'],
  backtest: ['Бэктест', 'Событийная проверка с торговыми расходами и задержкой.'],
  paper: ['Paper-счёт', 'Виртуальные позиции и жёсткий защитный контур.'],
  settings: ['Настройки', 'Понятные параметры с безопасными ограничениями.'],
  journal: ['Журнал', 'Сигналы, причины отказов и технические события.'],
};

function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[char]);
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(number);
}
function formatCompact(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('ru-RU', { notation: 'compact', maximumFractionDigits: 2 }).format(number);
}
function money(value, digits = 2) { return `${formatNumber(value, digits)} USDT`; }
function percent(value, digits = 2) { return `${formatNumber(value, digits)}%`; }
function timeText(ts) {
  const n = Number(ts);
  if (!n) return '—';
  return new Date(n).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function dateTimeText(value) {
  if (!value) return '—';
  const date = typeof value === 'number' ? new Date(value) : new Date(value);
  return Number.isNaN(date.getTime()) ? escapeHTML(value) : date.toLocaleString('ru-RU');
}
function directionClass(direction) {
  return direction === 'LONG' ? 'long' : direction === 'SHORT' ? 'short' : 'flat';
}
function signedClass(value) { return Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : ''; }

async function api(path, options = {}) {
  const config = { headers: { 'Content-Type': 'application/json' }, ...options };
  const response = await fetch(path, config);
  if (!response.ok) {
    let message = `Ошибка ${response.status}`;
    try { const payload = await response.json(); message = payload.detail || payload.message || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function toast(title, message = '', type = 'success') {
  const container = $('#toast-container');
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  node.innerHTML = `<i>${type === 'error' ? '!' : '✓'}</i><div><b>${escapeHTML(title)}</b>${message ? `<p>${escapeHTML(message)}</p>` : ''}</div>`;
  container.appendChild(node);
  setTimeout(() => node.remove(), 4300);
}

function setPage(page) {
  if (!pageMeta[page]) return;
  state.page = page;
  $$('.page').forEach(node => node.classList.toggle('active', node.id === `page-${page}`));
  $$('.nav-item').forEach(node => node.classList.toggle('active', node.dataset.page === page));
  $('#page-title').textContent = pageMeta[page][0];
  $('#page-subtitle').textContent = pageMeta[page][1];
  if (page === 'journal') renderJournal();
  if (page === 'settings' && state.status) hydrateSettings(state.status.config, true);
  requestAnimationFrame(drawCharts);
}

function updateConnection(status) {
  const app = status.app || {};
  const collector = status.collector || {};
  const connected = app.running && ['CONNECTED', 'RECONNECTING'].includes(collector.state);
  const waiting = app.running && !connected;
  const label = app.running ? (collector.state === 'CONNECTED' ? app.source : collector.state || app.source) : 'Остановлено';
  $('#sidebar-status').textContent = label;
  $('#connection-label').textContent = label;
  ['#sidebar-status-dot', '#connection-dot'].forEach(selector => {
    const dot = $(selector); dot.classList.toggle('online', connected); dot.classList.toggle('waiting', waiting);
  });
}

function updateDashboard(status) {
  const market = status.market || {}, paper = status.paper || {}, risk = status.risk || {};
  $('#metric-price').textContent = market.price ? `${formatNumber(market.price, market.price > 1000 ? 2 : 5)}` : '—';
  $('#metric-spread').textContent = `Спред ${formatNumber(market.spread_bps, 2)} б.п.`;
  $('#metric-equity').textContent = money(paper.equity || 0);
  $('#metric-balance').textContent = `Баланс ${money(paper.balance || 0)}`;
  const pnl = Number(paper.unrealized_pnl || 0);
  $('#metric-pnl').textContent = `${pnl >= 0 ? '+' : ''}${money(pnl)}`;
  $('#metric-pnl').className = signedClass(pnl);
  $('#metric-regime').textContent = market.regime || 'WAITING';
  $('#metric-liquidity').textContent = `Ликвидность ${percent((market.liquidity_score || 0) * 100, 0)}`;
  $('#metric-drawdown').textContent = percent(risk.drawdown_pct || 0);
  $('#metric-risk-state').textContent = risk.kill_switch ? 'Входы заблокированы' : 'Защита активна';
  $('#metric-risk-state').className = risk.kill_switch ? 'negative' : '';

  const signal = status.last_signal;
  const model = signal?.model || {};
  const probabilities = model.probabilities || { LONG: 0, FLAT: 1, SHORT: 0 };
  const confidence = Math.round((signal?.confidence || 0) * 100);
  const chip = $('#signal-chip');
  chip.textContent = signal?.direction === 'FLAT' ? 'ЖДЁМ' : signal?.direction || 'ЖДЁМ';
  chip.className = `signal-chip ${directionClass(signal?.direction)}`;
  $('#confidence-value').textContent = `${confidence}%`;
  $('#confidence-ring').style.setProperty('--confidence', confidence);
  for (const direction of ['long', 'flat', 'short']) {
    const value = Math.max(0, Math.min(1, Number(probabilities[direction.toUpperCase()] || 0)));
    $(`#prob-${direction}`).style.width = `${value * 100}%`;
    $(`#prob-${direction}-text`).textContent = `${Math.round(value * 100)}%`;
  }
  const riskDecision = status.last_risk_decision;
  if (signal) {
    $('#decision-title').textContent = signal.direction === 'FLAT'
      ? 'Сейчас лучше не входить'
      : riskDecision?.allowed ? `${signal.direction}: условия пройдены` : `${signal.direction}: вход заблокирован`;
    const reason = riskDecision && !riskDecision.allowed
      ? riskDecision.message
      : (signal.reasons || [])[0] || 'Анализ выполнен.';
    $('#decision-reason').textContent = reason;
    $('#net-edge').textContent = `${formatNumber(signal.expected_net_edge_bps, 2)} б.п.`;
    $('#net-edge').className = signedClass(signal.expected_net_edge_bps);
  } else {
    $('#decision-title').textContent = 'Рынок ещё не анализировался';
    $('#decision-reason').textContent = 'После запуска здесь появится человеческое объяснение решения.';
    $('#net-edge').textContent = '— б.п.';
  }
  renderOrderbook(status.orderbook || {});
  renderRecentSignals(status.recent_signals || []);
}

function renderOrderbook(book) {
  $('#book-mid').textContent = book.mid ? formatNumber(book.mid, book.mid > 1000 ? 2 : 5) : '—';
  $('#book-spread').textContent = `${formatNumber(book.spread_bps || 0, 2)} б.п.`;
  const renderSide = (selector, rows) => {
    const target = $(selector);
    target.innerHTML = (rows || []).map(row => `<div style="--strength:${Math.max(0, Math.min(1, Number(row.strength || 0)))}"><span>${formatNumber(row.price, row.price > 1000 ? 2 : 5)}</span><span>${formatNumber(row.quantity, 4)}</span></div>`).join('');
  };
  renderSide('#orderbook-asks', (book.asks || []).slice(0, 6).reverse());
  renderSide('#orderbook-bids', (book.bids || []).slice(0, 6));
}

function renderRecentSignals(signals) {
  const target = $('#recent-signals-table');
  if (!signals.length) { target.innerHTML = '<tr><td colspan="5" class="empty-cell">Сигналов пока нет</td></tr>'; return; }
  target.innerHTML = signals.slice(0, 8).map(row => `<tr>
    <td>${timeText(row.ts_ms)}</td>
    <td><span class="direction-pill ${directionClass(row.direction)}">${escapeHTML(row.direction)}</span></td>
    <td>${percent((row.confidence || 0) * 100, 0)}</td>
    <td class="${signedClass(row.expected_net_edge_bps)}">${formatNumber(row.expected_net_edge_bps, 2)} б.п.</td>
    <td>${escapeHTML(row.status || '—')}</td>
  </tr>`).join('');
}

function updateData(status) {
  const collector = status.collector || {}, market = status.market || {}, app = status.app || {};
  const tag = $('#collector-state'); tag.textContent = collector.state || 'STOPPED';
  tag.className = `state-tag ${collector.state === 'CONNECTED' ? 'good' : collector.state === 'ERROR' ? 'bad' : ''}`;
  $('#data-source').textContent = app.source || 'Остановлено';
  $('#data-symbol').textContent = market.symbol || '—';
  $('#data-messages').textContent = formatCompact(collector.messages || 0);
  $('#data-latency').textContent = `${formatNumber(market.latency_ms || 0, 0)} мс`;
  $('#data-reconnects').textContent = String(collector.reconnects || 0);
  $('#data-snapshots').textContent = formatCompact(market.snapshot_count || 0);
  const quality = market.data_quality || {}; $('#data-quality').textContent = quality.score == null ? '—' : percent(quality.score * 100, 0); $('#data-quality').className = quality.healthy === false ? 'negative' : 'positive';
}

function updateModel(status) {
  const model = status.model || {}, training = status.training || {};
  const tag = $('#model-ready-tag');
  tag.textContent = model.ready ? 'MODEL READY' : 'BASELINE';
  tag.className = `state-tag ${model.ready ? 'good' : ''}`;
  $('#model-name').textContent = model.ready ? (String(model.checkpoint).split(/[\\/]/).pop() || 'RiskAwareLOBNet') : 'Микроструктурный baseline';
  $('#model-device').textContent = `Устройство: ${model.device || 'CPU'}`;
  const progress = Math.max(0, Math.min(1, Number(training.progress || 0)));
  $('#train-progress').style.width = `${progress * 100}%`;
  $('#train-percent').textContent = `${Math.round(progress * 100)}%`;
  $('#train-message').textContent = training.message || 'Обучение не запущено';
  const details = [];
  if (training.epoch) details.push(`Эпоха ${training.epoch}/${training.epochs}`);
  if (training.validation_loss != null) details.push(`val loss ${formatNumber(training.validation_loss, 4)}`);
  if (training.accuracy != null) details.push(`accuracy ${percent(training.accuracy * 100, 1)}`);
  if (training.macro_f1 != null) details.push(`macro F1 ${formatNumber(training.macro_f1, 3)}`);
  $('#train-details').textContent = details.join(' · ');
  $$('[data-action="train"]').forEach(button => { button.disabled = Boolean(training.running); });
}

function updateBacktest(status) {
  const job = status.backtest || {};
  const progress = Math.max(0, Math.min(1, Number(job.progress || 0)));
  $('#backtest-progress').style.width = `${progress * 100}%`;
  $('#backtest-percent').textContent = `${Math.round(progress * 100)}%`;
  $('#backtest-message').textContent = job.message || 'Бэктест не запущен';
  $$('[data-action="backtest"]').forEach(button => { button.disabled = Boolean(job.running); });
  if (job.metrics) {
    state.latestBacktest = job;
    renderBacktestResult(job);
  }
}

function renderBacktestResult(result) {
  const metrics = result?.metrics || {};
  const root = $('#backtest-metrics');
  $$('[data-metric]', root).forEach(node => {
    const key = node.dataset.metric, value = metrics[key];
    if (value == null) { node.textContent = '—'; return; }
    if (key === 'net_profit') { node.textContent = `${Number(value) >= 0 ? '+' : ''}${money(value)}`; node.className = signedClass(value); }
    else if (['max_drawdown_pct', 'fill_rate_pct'].includes(key)) node.textContent = percent(value);
    else node.textContent = formatNumber(value, ['trades'].includes(key) ? 0 : 3);
  });
  const returnNode = $('[data-submetric="return_pct"]', root);
  if (returnNode) { returnNode.textContent = `Доходность ${percent(metrics.return_pct || 0)}`; returnNode.className = signedClass(metrics.return_pct); }
  const winNode = $('[data-submetric="win_rate_pct"]', root);
  if (winNode) winNode.textContent = `Win rate ${percent(metrics.win_rate_pct || 0, 1)}`;
  requestAnimationFrame(drawCharts);
}

function updatePaper(status) {
  const paper = status.paper || {}, risk = status.risk || {};
  $('#paper-balance').textContent = money(paper.balance || 0);
  $('#paper-equity').textContent = money(paper.equity || 0);
  $('#paper-trade-count').textContent = String(paper.trade_count || 0);
  $('#paper-orders').textContent = String(paper.pending_orders || 0);
  const position = paper.position;
  $('#position-empty').classList.toggle('hidden', Boolean(position));
  $('#position-details').classList.toggle('hidden', !position);
  const tag = $('#position-tag');
  if (position) {
    tag.textContent = position.direction;
    tag.className = `state-tag ${position.direction === 'LONG' ? 'good' : 'bad'}`;
    $('#position-details').innerHTML = `<div class="position-hero"><div><span>${escapeHTML(position.symbol)}</span><strong class="${directionClass(position.direction)}">${escapeHTML(position.direction)}</strong></div><strong class="${signedClass(position.unrealized_pnl)}">${Number(position.unrealized_pnl)>=0?'+':''}${money(position.unrealized_pnl)}</strong></div><div class="detail-grid">
      <div><span>Цена входа</span><b>${formatNumber(position.entry_price, 4)}</b></div><div><span>Количество</span><b>${formatNumber(position.quantity, 6)}</b></div>
      <div><span>Стоп</span><b>${formatNumber(position.stop_price, 4)}</b></div><div><span>Тейк</span><b>${formatNumber(position.take_profit_price, 4)}</b></div>
      <div><span>Открыта</span><b>${timeText(position.opened_ts_ms)}</b></div><div><span>Уплачено при входе</span><b>${money(position.fees, 4)}</b></div>
    </div>`;
  } else { tag.textContent = 'НЕТ'; tag.className = 'state-tag'; }
  const kill = $('#kill-tag'); kill.textContent = risk.kill_switch ? 'BLOCKED' : 'ACTIVE'; kill.className = `state-tag ${risk.kill_switch ? 'bad' : 'good'}`;
  $('#risk-dd').textContent = percent(risk.drawdown_pct || 0);
  $('#risk-dd-bar').style.width = `${Math.min(100, (risk.drawdown_pct || 0) / Math.max(risk.limits?.max_drawdown_pct || 1, 1) * 100)}%`;
  $('#risk-daily').textContent = `${Number(risk.daily_pnl||0)>=0?'+':''}${money(risk.daily_pnl || 0)}`;
  $('#risk-daily').className = signedClass(risk.daily_pnl);
  $('#risk-losses').textContent = String(risk.consecutive_losses || 0);
  $('#risk-per-trade').textContent = percent(risk.limits?.risk_per_trade_pct || 0);
  renderTrades(state.history.trades || []);
}

function renderTrades(rows) {
  const target = $('#trades-table');
  if (!rows.length) { target.innerHTML = '<tr><td colspan="7" class="empty-cell">Закрытых сделок пока нет</td></tr>'; return; }
  target.innerHTML = rows.slice(0, 50).map(item => {
    const row = item.payload || item;
    return `<tr><td>${timeText(row.closed_ts_ms)}</td><td>${escapeHTML(row.symbol)}</td><td><span class="direction-pill ${directionClass(row.direction)}">${escapeHTML(row.direction)}</span></td><td>${formatNumber(row.entry_price,4)}</td><td>${formatNumber(row.exit_price,4)}</td><td class="${signedClass(row.net_pnl)}">${Number(row.net_pnl)>=0?'+':''}${money(row.net_pnl)}</td><td>${escapeHTML(row.reason || '—')}</td></tr>`;
  }).join('');
}

function setFormValue(name, value) {
  const element = $(`[name="${CSS.escape(name)}"]`);
  if (!element) return;
  if (element.type === 'checkbox') element.checked = Boolean(value);
  else element.value = value ?? '';
}
function getNested(object, path) { return path.split('.').reduce((value, key) => value?.[key], object); }
function setNested(object, path, value) {
  const keys = path.split('.'); let target = object;
  keys.slice(0, -1).forEach(key => { target[key] ||= {}; target = target[key]; });
  target[keys.at(-1)] = value;
}

function hydrateSettings(config, force = false) {
  if (!config || (state.settingsHydrated && !force)) return;
  $$('[name]', $('#settings-form')).forEach(element => {
    if (element.name.startsWith('strategies.')) return;
    const value = getNested(config, element.name);
    if (value != null) setFormValue(element.name, value);
  });
  renderStrategySwitches(config.strategies || {});
  state.settingsHydrated = true;
}

function renderStrategySwitches(strategyConfig = {}) {
  const target = $('#strategy-switches');
  const catalog = state.history.strategies || [];
  if (!catalog.length) return;
  target.innerHTML = catalog.map(item => {
    const key = `${item.id}_enabled`;
    const checked = strategyConfig[key] !== false;
    return `<label class="strategy-tile"><input type="checkbox" name="strategies.${key}" ${checked?'checked':''}><div class="tile-top"><b>${escapeHTML(item.title)}</b><i>✓</i></div><p>${escapeHTML(item.description)}</p></label>`;
  }).join('');
}

function collectSettings() {
  const patch = {};
  $$('[name]', $('#settings-form')).forEach(element => {
    let value;
    if (element.type === 'checkbox') value = element.checked;
    else if (element.type === 'number') value = Number(element.value);
    else value = element.value;
    setNested(patch, element.name, value);
  });
  return patch;
}

async function saveSettings() {
  try {
    const result = await api('/api/config', { method: 'POST', body: JSON.stringify({ patch: collectSettings() }) });
    state.settingsHydrated = false;
    toast('Настройки сохранены', result.restart_required ? 'Для части параметров перезапустите поток рынка.' : 'Новые ограничения применены.');
    await refreshStatus();
  } catch (error) { toast('Не удалось сохранить', error.message, 'error'); }
}

function renderJournal() {
  const target = $('#journal-content');
  const rows = state.history[state.journal] || [];
  if (!rows.length) { target.innerHTML = '<div class="empty-state"><div>≡</div><strong>Записей пока нет</strong><p>Запустите программу, и события появятся здесь.</p></div>'; return; }
  if (state.journal === 'logs') {
    target.innerHTML = rows.slice().reverse().map(row => `<div class="log-row"><time>${dateTimeText(row.ts)}</time><span class="log-level ${escapeHTML(row.level)}">${escapeHTML(row.level)}</span><span class="log-message">${escapeHTML(row.message)}</span></div>`).join('');
  } else if (state.journal === 'decisions') {
    target.innerHTML = rows.map(item => `<div class="decision-row"><time>${timeText(item.ts_ms)}</time><span class="decision-action">${escapeHTML(item.action)}</span><span>${escapeHTML(item.signal_id || '—')}</span><span class="log-message"><b>${escapeHTML(item.reason)}</b>${item.payload?.risk?.code ? ` · ${escapeHTML(item.payload.risk.code)}` : ''}</span></div>`).join('');
  } else {
    target.innerHTML = rows.map(item => { const row = item.payload || item; return `<div class="decision-row"><time>${timeText(row.ts_ms)}</time><span class="direction-pill ${directionClass(row.direction)}">${escapeHTML(row.direction)}</span><span>${percent((row.confidence||0)*100,0)} · ${formatNumber(row.expected_net_edge_bps,2)} б.п.</span><span class="log-message">${escapeHTML((row.reasons||[])[0] || row.status || '—')}</span></div>`; }).join('');
  }
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.max(1, Math.round(rect.width * dpr)); canvas.height = Math.max(1, Math.round(rect.height * dpr));
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); return { ctx, width: rect.width, height: rect.height };
}
function drawSeriesChart(canvas, series) {
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { left: 14, right: 14, top: 12, bottom: 20 };
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  ctx.strokeStyle = 'rgba(255,255,255,.045)'; ctx.lineWidth = 1;
  for (let i=0;i<=4;i++){ const y=pad.top+plotH*i/4; ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(width-pad.right,y);ctx.stroke(); }
  series.forEach(item => {
    const points = item.points || []; if (points.length < 2) return;
    const values = points.map(point => Number(point[1])).filter(Number.isFinite); if (values.length < 2) return;
    let min = Math.min(...values), max = Math.max(...values); if (Math.abs(max-min)<1e-12){min-=1;max+=1;}
    ctx.strokeStyle = item.color; ctx.lineWidth = item.width || 1.6; ctx.lineJoin='round'; ctx.lineCap='round';
    ctx.beginPath();
    points.forEach((point,index)=>{ const x=pad.left+plotW*index/Math.max(1,points.length-1); const y=pad.top+plotH*(1-(Number(point[1])-min)/(max-min)); index?ctx.lineTo(x,y):ctx.moveTo(x,y); });
    ctx.stroke();
    if (item.fill) { ctx.lineTo(width-pad.right,height-pad.bottom);ctx.lineTo(pad.left,height-pad.bottom);ctx.closePath(); const gradient=ctx.createLinearGradient(0,pad.top,0,height-pad.bottom);gradient.addColorStop(0,item.fill);gradient.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=gradient;ctx.fill(); }
  });
}
function drawCharts() {
  const styles = getComputedStyle(document.documentElement);
  const status = state.status;
  if (status) {
    const price = status.charts?.price || [], equity = status.charts?.equity || [];
    $('#main-chart-empty').style.display = price.length > 1 ? 'none' : 'grid';
    drawSeriesChart($('#main-chart'), [
      { points: price, color: styles.getPropertyValue('--accent-2').trim(), width: 1.4 },
      { points: equity, color: styles.getPropertyValue('--accent').trim(), width: 1.7, fill: 'rgba(101,212,154,.08)' },
    ]);
  }
  const result = state.latestBacktest;
  const points = result?.equity_curve || [];
  $('#backtest-chart-empty').style.display = points.length > 1 ? 'none' : 'grid';
  drawSeriesChart($('#backtest-chart'), [{ points, color: styles.getPropertyValue('--accent').trim(), width: 1.8, fill: 'rgba(101,212,154,.11)' }]);
}

function updateAll(status) {
  state.status = status;
  updateConnection(status); updateDashboard(status); updateData(status); updateModel(status); updateBacktest(status); updatePaper(status);
  if (!state.settingsHydrated) hydrateSettings(status.config);
  if (state.page === 'journal') renderJournal();
  requestAnimationFrame(drawCharts);
}

async function refreshStatus() {
  try {
    const payload = await api('/api/status');
    state.apiDownShown = false; updateAll(payload);
  } catch (error) {
    if (!state.apiDownShown) { toast('Связь с приложением потеряна', error.message, 'error'); state.apiDownShown = true; }
  }
}
async function refreshHistory() {
  try {
    state.history = await api('/api/history');
    renderTrades(state.history.trades || []);
    if (state.status && !state.settingsHydrated) hydrateSettings(state.status.config, true);
    if (state.page === 'journal') renderJournal();
  } catch (_) {}
}
async function loadLatestBacktest() {
  try { state.latestBacktest = await api('/api/reports/latest-backtest'); renderBacktestResult(state.latestBacktest); } catch (_) {}
}

function confirmAction(title, text) {
  return new Promise(resolve => {
    const modal = $('#confirm-modal'); $('#confirm-title').textContent = title; $('#confirm-text').textContent = text; modal.classList.remove('hidden');
    const finish = value => { modal.classList.add('hidden'); $('#confirm-ok').onclick = null; $('#confirm-cancel').onclick = null; resolve(value); };
    $('#confirm-ok').onclick = () => finish(true); $('#confirm-cancel').onclick = () => finish(false);
  });
}

async function runAction(action, button) {
  const original = button?.innerHTML;
  if (button) { button.disabled = true; button.textContent = 'Выполняется…'; }
  try {
    let result;
    if (action === 'start-demo') result = await api('/api/actions/start-demo', { method: 'POST' });
    else if (action === 'start-market') result = await api('/api/actions/start-market', { method: 'POST' });
    else if (action === 'stop') result = await api('/api/actions/stop', { method: 'POST' });
    else if (action === 'reset-paper') {
      if (!await confirmAction('Сбросить paper-счёт?', 'Баланс, открытая позиция и локальная история paper-брокера будут сброшены.')) return;
      result = await api('/api/actions/reset-paper', { method: 'POST' });
    } else if (action === 'reset-kill') {
      if (!await confirmAction('Снять аварийную блокировку?', 'Делайте это только после того, как понятна причина остановки.')) return;
      result = await api('/api/actions/reset-kill-switch', { method: 'POST' });
    } else if (action === 'train') {
      result = await api('/api/actions/train', { method: 'POST', body: JSON.stringify({ source: $('#train-source').value, samples: Number($('#train-samples').value) }) });
    } else if (action === 'backtest') {
      result = await api('/api/actions/backtest', { method: 'POST', body: JSON.stringify({ source: $('#backtest-source').value, steps: Number($('#backtest-steps').value) }) });
    }
    if (result?.ok === false) throw new Error(result.message || 'Действие не выполнено');
    const messages = {
      'start-demo': ['Демо запущено', 'Через несколько секунд появится анализ рынка.'],
      'start-market': ['Подключение запущено', 'Используются публичные данные; ордера остаются виртуальными.'],
      stop: ['Программа остановлена', 'Состояние paper-счёта сохранено.'],
      'reset-paper': ['Paper-счёт сброшен', 'Начальный баланс восстановлен.'],
      'reset-kill': ['Блокировка снята', 'Защитные лимиты продолжают работать.'],
      train: ['Обучение запущено', 'Прогресс отображается на странице «Нейросеть».'],
      backtest: ['Бэктест запущен', 'Прогресс отображается на странице «Бэктест».'],
    };
    toast(...messages[action]); await refreshStatus();
  } catch (error) { toast('Действие не выполнено', error.message, 'error'); }
  finally { if (button) { button.disabled = false; button.innerHTML = original; } }
}

function bindEvents() {
  $$('.nav-item').forEach(button => button.addEventListener('click', () => setPage(button.dataset.page)));
  $$('[data-page-link]').forEach(button => button.addEventListener('click', () => setPage(button.dataset.pageLink)));
  $$('[data-action]').forEach(button => button.addEventListener('click', () => runAction(button.dataset.action, button)));
  $('#save-settings').addEventListener('click', saveSettings);
  $('#refresh-button').addEventListener('click', async () => { await Promise.all([refreshStatus(), refreshHistory()]); toast('Данные обновлены'); });
  $('#journal-refresh').addEventListener('click', refreshHistory);
  $$('.journal-tabs button').forEach(button => button.addEventListener('click', () => {
    state.journal = button.dataset.journal; $$('.journal-tabs button').forEach(item => item.classList.toggle('active', item === button)); renderJournal();
  }));
  $('#help-toggle').addEventListener('click', () => {
    state.help = !state.help; localStorage.setItem('neuroscalper-help', state.help ? 'on' : 'off'); document.body.classList.toggle('help-off', !state.help); $('#help-toggle span').textContent = state.help ? 'Подсказки включены' : 'Подсказки выключены';
  });
  $$('.help-close').forEach(button => button.addEventListener('click', () => button.closest('.help-card').classList.add('hidden-by-user')));
  window.addEventListener('resize', () => requestAnimationFrame(drawCharts));
}

async function initialize() {
  document.body.classList.toggle('help-off', !state.help);
  $('#help-toggle span').textContent = state.help ? 'Подсказки включены' : 'Подсказки выключены';
  bindEvents();
  await Promise.all([refreshStatus(), refreshHistory(), loadLatestBacktest()]);
  setInterval(refreshStatus, 1000);
  setInterval(refreshHistory, 5000);
}

document.addEventListener('DOMContentLoaded', initialize);
