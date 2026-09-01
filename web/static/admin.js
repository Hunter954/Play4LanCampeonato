(() => {
  'use strict';

  const page = document.body.dataset.adminPage;
  if (!page) return;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const serverRoot = $('#server-admin');
  const currentServer = serverRoot?.dataset.serverCode || null;

  const escapeHtml = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  function toast(title, detail = '', type = 'success') {
    const stack = $('#admin-toast-stack');
    if (!stack) return;
    const item = document.createElement('div');
    item.className = `admin-toast ${type}`;
    item.innerHTML = `<i class="bi ${type === 'error' ? 'bi-exclamation-circle-fill' : 'bi-check-circle-fill'}"></i><div><b>${escapeHtml(title)}</b>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div>`;
    stack.appendChild(item);
    window.setTimeout(() => item.remove(), 4200);
  }

  function prettyTime(value) {
    if (!value) return 'Aguardando';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('pt-BR', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
  }

  function setStatusBadge(element, status) {
    if (!element) return;
    const normalized = (status || 'UNKNOWN').toLowerCase();
    element.className = `${element.classList.contains('large') ? 'status-badge large' : 'status-badge'} ${normalized}`;
    element.innerHTML = `<span></span>${escapeHtml(status || 'UNKNOWN')}`;
  }

  function rconLabel(telemetry) {
    if (telemetry?.rcon_ok) return 'Conectado';
    if (telemetry?.online) return 'Com erro';
    return '—';
  }

  function updateDashboardServer(data) {
    const tile = document.querySelector(`[data-server-code="${CSS.escape(data.server_id || data.code || '')}"]`);
    if (!tile) return;
    const telemetry = data.payload || data.telemetry || {};
    setStatusBadge($('[data-role="status"]', tile), data.status);
    const map = $('[data-role="map"]', tile);
    const players = $('[data-role="players"]', tile);
    const rcon = $('[data-role="rcon"]', tile);
    const hb = $('[data-role="heartbeat"]', tile);
    if (map) map.textContent = telemetry.map || '—';
    if (players) players.textContent = `${telemetry.player_count || 0}/10`;
    if (rcon) rcon.textContent = telemetry.rcon_ok ? 'OK' : (telemetry.online ? 'ERRO' : '—');
    if (hb) hb.textContent = prettyTime(data.last_heartbeat);
  }

  function renderPlayers(players = []) {
    const body = $('#players-table-body');
    if (!body) return;
    if (!players.length) {
      body.innerHTML = '<div class="empty-state" id="players-empty"><i class="bi bi-person-dash"></i><div><b>Nenhum jogador conectado</b><span>A lista será preenchida automaticamente quando jogadores entrarem no servidor.</span></div></div>';
      return;
    }

    body.innerHTML = players.map(player => `
      <div class="player-row" data-player-userid="${escapeHtml(player.userid)}">
        <span class="userid">#${escapeHtml(player.userid ?? '?')}</span>
        <strong><span class="player-presence"></span>${escapeHtml(player.name || '?')}</strong>
        <code>${escapeHtml(player.steam || '?')}</code>
        <span>${escapeHtml(player.ping ?? '?')} ms</span>
        <form class="js-async-form" data-confirm="Remover ${escapeHtml(player.name || 'este jogador')} do servidor?" method="post" action="/admin/servers/${encodeURIComponent(currentServer)}/kick">
          <input type="hidden" name="userid" value="${escapeHtml(player.userid)}">
          <button class="icon-button danger" title="Expulsar jogador"><i class="bi bi-person-x"></i></button>
        </form>
      </div>`).join('');
  }

  function updateServerDetail(data) {
    if (!currentServer || (data.server_id || data.code) !== currentServer) return;
    const telemetry = data.payload || data.telemetry || {};
    setStatusBadge($('[data-role="server-status"]'), data.status);

    const values = {
      '[data-role="hero-map"]': telemetry.map || 'Aguardando mapa',
      '[data-role="metric-map"]': telemetry.map || '—',
      '[data-role="metric-players"]': `${telemetry.player_count || 0}/10`,
      '[data-role="metric-rcon"]': rconLabel(telemetry),
      '[data-role="metric-heartbeat"]': prettyTime(data.last_heartbeat),
      '[data-role="players-online"]': telemetry.player_count || 0,
      '[data-role="health-process"]': data.status || 'UNKNOWN',
      '[data-role="health-rcon"]': telemetry.rcon_ok ? 'OK' : (telemetry.online ? 'ERRO' : '—'),
    };
    Object.entries(values).forEach(([selector, value]) => {
      const element = $(selector);
      if (element) element.textContent = value;
    });

    const warning = $('#rcon-warning');
    if (warning) {
      warning.classList.toggle('is-hidden', !telemetry.rcon_error);
      const text = $('[data-role="rcon-error"]', warning);
      if (text) text.textContent = telemetry.rcon_error || '';
    }
    renderPlayers(telemetry.players || []);
  }

  function renderCommands(commands = []) {
    const history = $('#command-history');
    if (!history) return;
    if (!commands.length) {
      history.innerHTML = '<div class="empty-inline"><i class="bi bi-clock-history"></i> Nenhum comando enviado.</div>';
      return;
    }
    history.innerHTML = commands.map(command => `
      <div class="command-item" data-command-id="${escapeHtml(command.id)}">
        <div class="command-top">
          <div><b>#${escapeHtml(command.id)} · ${escapeHtml(command.command)}</b>${command.rcon_command ? `<code>&gt; ${escapeHtml(command.rcon_command)}</code>` : ''}</div>
          <span class="cmd-status ${escapeHtml((command.status || '').toLowerCase())}">${escapeHtml(command.status || '')}</span>
        </div>
        ${command.result ? `<pre>${escapeHtml(command.result)}</pre>` : ''}
        ${command.error ? `<div class="command-error"><i class="bi bi-exclamation-circle"></i> ${escapeHtml(command.error)}</div>` : ''}
      </div>`).join('');
  }

  async function fetchOverview() {
    try {
      const response = await fetch('/admin/api/overview', {headers: {'Accept': 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      (data.servers || []).forEach(server => updateDashboardServer({
        server_id: server.code,
        status: server.status,
        last_heartbeat: server.last_heartbeat,
        payload: server.telemetry || {},
      }));
      const online = $('#summary-servers-online');
      const players = $('#summary-players');
      const pending = $('#summary-pending');
      if (online) online.textContent = data.summary.servers_online ?? 0;
      if (players) players.textContent = data.summary.players_total ?? 0;
      if (pending) pending.textContent = data.summary.pending_registrations ?? 0;
    } catch (_) {}
  }

  async function fetchServerState() {
    if (!currentServer) return;
    try {
      const response = await fetch(`/admin/api/servers/${encodeURIComponent(currentServer)}/state`, {headers: {'Accept': 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      updateServerDetail({
        server_id: data.server.code,
        status: data.server.status,
        last_heartbeat: data.server.last_heartbeat,
        payload: data.server.telemetry || {},
      });
      renderCommands(data.commands || []);
    } catch (_) {}
  }

  async function submitAsync(form) {
    const confirmation = form.dataset.confirm;
    if (confirmation && !window.confirm(confirmation)) return;

    const button = $('button', form);
    const original = button?.innerHTML;
    if (button) {
      button.classList.add('is-busy');
      button.disabled = true;
      button.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Processando';
    }

    const pendingStatus = form.dataset.pendingStatus;
    if (pendingStatus && currentServer) setStatusBadge($('[data-role="server-status"]'), pendingStatus);

    try {
      const response = await fetch(form.action, {
        method: (form.method || 'POST').toUpperCase(),
        body: new FormData(form),
        headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
      });
      let data = {};
      try { data = await response.json(); } catch (_) {}
      if (!response.ok) throw new Error(data.error || `Erro HTTP ${response.status}`);
      toast('Ação enviada ao Agent', 'A tela será atualizada automaticamente.');
      if (page === 'server-detail') window.setTimeout(fetchServerState, 350);
      if (page === 'dashboard') window.setTimeout(fetchOverview, 350);
    } catch (error) {
      toast('Não foi possível executar', error.message || 'Erro inesperado.', 'error');
      if (page === 'server-detail') fetchServerState();
    } finally {
      if (button) {
        button.classList.remove('is-busy');
        button.disabled = false;
        button.innerHTML = original;
      }
    }
  }

  document.addEventListener('submit', event => {
    const form = event.target.closest('.js-async-form');
    if (!form) return;
    event.preventDefault();
    submitAsync(form);
  });

  if (window.io) {
    const socket = window.io({transports: ['websocket', 'polling']});
    socket.on('server_status', data => {
      if (page === 'dashboard') {
        updateDashboardServer(data);
        fetchOverview();
      } else if (page === 'server-detail') {
        updateServerDetail(data);
      }
    });
    socket.on('server_command', data => {
      if (page === 'server-detail' && data.server_code === currentServer) {
        if (data.status === 'DONE') toast('Comando concluído', data.rcon_command || data.command || 'Ação concluída.');
        if (data.status === 'FAILED') toast('Comando falhou', data.error || 'Verifique o histórico.', 'error');
        fetchServerState();
      }
    });
  }

  // Fallback para proxies/navegadores onde WebSocket não esteja disponível.
  if (page === 'dashboard') {
    fetchOverview();
    window.setInterval(fetchOverview, 5000);
  }
  if (page === 'server-detail') {
    fetchServerState();
    window.setInterval(fetchServerState, 3000);
  }
})();
