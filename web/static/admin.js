(() => {
  'use strict';

  if (!document.body.classList.contains('admin-shell')) return;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const serverRoot = $('#server-admin');
  const currentServer = serverRoot?.dataset.serverCode || null;
  const endpoint = document.body.dataset.adminPage || '';

  const escapeHtml = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  function toast(title, detail = '', type = 'success') {
    const stack = $('#admin-toast-stack');
    if (!stack) return;
    const node = document.createElement('div');
    node.className = `admin-toast ${type}`;
    node.innerHTML = `<i class="bi ${type === 'error' ? 'bi-exclamation-circle-fill' : 'bi-check-circle-fill'}"></i><div><b>${escapeHtml(title)}</b>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div>`;
    stack.appendChild(node);
    setTimeout(() => node.remove(), 4200);
  }

  function setStatusBadge(el, status) {
    if (!el) return;
    const large = el.classList.contains('large');
    const normalized = String(status || 'UNKNOWN').toLowerCase().replace(/[^a-z0-9_-]/g, '');
    el.className = `status-badge${large ? ' large' : ''} ${normalized}`;
    el.innerHTML = `<span></span>${escapeHtml(status || 'UNKNOWN')}`;
  }

  function formatMoney(v) {
    const n = Number(v || 0);
    return `$${Number.isFinite(n) ? n.toLocaleString('pt-BR') : '0'}`;
  }

  function updateCommon(data) {
    if (!currentServer || (data.server_id || data.code) !== currentServer) return;
    const t = data.payload || data.telemetry || {};
    setStatusBadge($('[data-role="server-status"]'), data.status);
    const values = {
      '[data-role="phase"]': t.phase || 'AGUARDANDO',
      '[data-role="metric-map"]': t.map || '—',
      '[data-role="metric-phase"]': t.phase || 'AGUARDANDO',
      '[data-role="metric-players"]': `${Number(t.player_count || (t.players || []).length || 0)}/10`,
      '[data-role="metric-rcon"]': t.rcon_ok ? 'OK' : (t.online ? 'ERRO' : '—'),
      '[data-role="score"]': `${Number(t.team1_score || 0)} × ${Number(t.team2_score || 0)}`,
      '[data-role="test-mode"]': t.test_mode ? 'Ligado' : 'Desligado',
    };
    Object.entries(values).forEach(([sel, value]) => {
      const el = $(sel); if (el) el.textContent = value;
    });
    $$('.map-card').forEach(card => card.classList.toggle('active', card.closest('form')?.querySelector('[name="map_name"]')?.value === t.map));
  }

  function accountMarkup(p) {
    if (p.registered) {
      const team = Array.isArray(p.platform_teams) && p.platform_teams[0] ? ` · ${escapeHtml(p.platform_teams[0].tag || p.platform_teams[0].name || '')}` : '';
      return `<small><span class="account-pill registered"><i class="bi bi-patch-check-fill"></i> PLAY4LAN</span>${team}</small>`;
    }
    return '<small><span class="account-pill guest">Não cadastrado</span></small>';
  }

  function playerRow(p) {
    const alive = Boolean(p.alive);
    const ready = Boolean(p.ready);
    const name = escapeHtml(p.platform_nickname || p.name || '?');
    const actionState = ready ? 'wait' : 'ready';
    const actionLabel = ready ? `Colocar em espera: ${name}` : `Marcar como pronto: ${name}`;
    return `<div class="live-player-row" data-userid="${escapeHtml(p.userid)}">
      <div class="player-name-cell"><b>${name}</b>${accountMarkup(p)}<small>#${escapeHtml(p.userid)} · ${escapeHtml(p.steam_id64 || p.steam || '?')}</small></div>
      <span class="hp ${alive ? '' : 'dead'}"><i class="bi bi-heart-pulse-fill"></i>${Number(p.health || 0)}</span>
      <span class="money">${formatMoney(p.money)}</span>
      <span>${Number(p.kills || 0)}</span><span>${Number(p.assists || 0)}</span><span>${Number(p.deaths || 0)}</span><span>${Number(p.damage || 0)}</span>
      <span class="weapon-cell">${escapeHtml(p.weapon || '—')}</span><span>${escapeHtml(p.ping ?? '?')}</span>
      <span><span class="ready-pill ${ready ? 'yes' : 'no'}">${ready ? 'Pronto' : 'Espera'}</span></span>
      <div class="row-menu">
        <form class="js-async-form js-secure-form" data-action-label="${escapeHtml(actionLabel)}" method="post" action="/admin/servers/${encodeURIComponent(currentServer)}/players/${encodeURIComponent(p.userid)}/${actionState}"><button class="mini-action" title="${ready ? 'Colocar em espera' : 'Marcar pronto'}"><i class="bi ${ready ? 'bi-person-dash' : 'bi-person-check'}"></i></button></form>
        <form class="js-async-form js-secure-form" data-action-label="Expulsar ${name}" method="post" action="/admin/servers/${encodeURIComponent(currentServer)}/kick"><input type="hidden" name="userid" value="${escapeHtml(p.userid)}"><button class="mini-action danger" title="Expulsar"><i class="bi bi-person-x"></i></button></form>
      </div></div>`;
  }

  function renderPlayers(players = []) {
    ['CT', 'TR', 'SPEC'].forEach(side => {
      const rows = players.filter(p => (p.team || 'SPEC') === side);
      const host = $(`[data-team-rows="${side}"]`);
      const count = $(`[data-team-count="${side}"]`);
      if (count) count.textContent = `${rows.length} ${rows.length === 1 ? 'jogador' : 'jogadores'}`;
      if (host) host.innerHTML = rows.length ? rows.map(playerRow).join('') : '<div class="team-empty">Nenhum jogador deste lado.</div>';
    });
  }

  function renderChat(chat = []) {
    const host = $('#live-chat');
    if (!host) return;
    const sorted = [...chat].sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
    if (!sorted.length) { host.innerHTML = '<div class="empty-state">Nenhuma mensagem registrada ainda.</div>'; return; }
    host.innerHTML = sorted.map(m => `<div class="chat-line" data-seq="${escapeHtml(m.seq)}"><span class="chat-team ${String(m.team || 'SPEC').toLowerCase()}">${escapeHtml(m.team || 'SPEC')}</span><b>${escapeHtml(m.name || '?')}</b>${m.team_only ? '<span class="team-only">EQUIPE</span>' : ''}<span>${escapeHtml(m.text || '')}</span></div>`).join('');
    host.scrollTop = host.scrollHeight;
  }

  function renderBackups(backups = []) {
    const host = $('#backup-list');
    if (!host) return;
    if (!backups.length) { host.innerHTML = '<div class="empty-state">Nenhum backup disponível neste momento.</div>'; return; }
    host.innerHTML = backups.map(b => `<div class="backup-row"><div class="backup-round"><span>ROUND</span><b>${Number(b.round) >= 0 ? escapeHtml(b.round) : '—'}</b></div><div><b>${escapeHtml(b.file)}</b><small>Backup PLAY4LAN</small></div><form class="js-async-form js-secure-form" data-action-label="Restaurar round ${escapeHtml(b.round)}" method="post" action="/admin/servers/${encodeURIComponent(currentServer)}/restore"><input type="hidden" name="backup" value="${escapeHtml(b.file)}"><button class="button secondary"><i class="bi bi-arrow-counterclockwise"></i> Restaurar</button></form></div>`).join('');
  }

  function applyServerState(server) {
    updateCommon({server_id: server.code, status: server.status, last_heartbeat: server.last_heartbeat, payload: server.telemetry || {}});
    const t = server.telemetry || {};
    renderPlayers(t.players || []);
    renderChat(t.chat || []);
    renderBackups(t.backups || []);
  }

  async function fetchServerState() {
    if (!currentServer) return;
    try {
      const res = await fetch(`/admin/api/servers/${encodeURIComponent(currentServer)}/state`, {headers: {'Accept': 'application/json'}});
      if (!res.ok) return;
      const data = await res.json();
      if (data.server) applyServerState(data.server);
    } catch (_) {}
  }

  async function fetchOverview() {
    try {
      const res = await fetch('/admin/api/overview', {headers: {'Accept': 'application/json'}});
      if (!res.ok) return;
      const data = await res.json();
      (data.servers || []).forEach(server => {
        const tile = document.querySelector(`[data-server-code="${CSS.escape(server.code)}"]`);
        if (!tile) return;
        setStatusBadge($('[data-role="status"]', tile), server.status);
        const t = server.telemetry || {};
        const map = $('[data-role="map"]', tile); if (map) map.textContent = t.map || '—';
        const players = $('[data-role="players"]', tile); if (players) players.textContent = `${t.player_count || 0}/10`;
        const rcon = $('[data-role="rcon"]', tile); if (rcon) rcon.textContent = t.rcon_ok ? 'OK' : (t.online ? 'ERRO' : '—');
      });
      if ($('#summary-servers-online')) $('#summary-servers-online').textContent = data.summary?.servers_online ?? 0;
      if ($('#summary-players')) $('#summary-players').textContent = data.summary?.players_total ?? 0;
      if ($('#summary-pending')) $('#summary-pending').textContent = data.summary?.pending_registrations ?? 0;
    } catch (_) {}
  }

  // PIN: obrigatório em toda ação de servidor e nunca fica armazenado no navegador.
  const modal = $('#pin-modal');
  const pinInput = $('#pin-input');
  const pinError = $('#pin-error');
  const pinLabel = $('#pin-action-label');
  const pinConfirm = $('#pin-confirm');
  let pendingForm = null;

  function closePin() {
    if (!modal) return;
    modal.classList.remove('open'); modal.setAttribute('aria-hidden', 'true');
    if (pinInput) pinInput.value = '';
    if (pinError) pinError.textContent = '';
    pendingForm = null;
  }

  function openPin(form) {
    pendingForm = form;
    if (pinLabel) pinLabel.textContent = form.dataset.actionLabel || 'Ação protegida';
    if (pinError) pinError.textContent = '';
    if (pinInput) pinInput.value = '';
    modal?.classList.add('open'); modal?.setAttribute('aria-hidden', 'false');
    setTimeout(() => pinInput?.focus(), 50);
  }

  $$('[data-pin-close]').forEach(el => el.addEventListener('click', closePin));
  modal?.addEventListener('click', e => { if (e.target === modal) closePin(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && modal?.classList.contains('open')) closePin(); });
  pinInput?.addEventListener('input', () => { pinInput.value = pinInput.value.replace(/\D/g, '').slice(0, 4); if (pinError) pinError.textContent = ''; });
  pinInput?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); pinConfirm?.click(); } });

  async function sendForm(form, pin = null) {
    const button = $('button', form);
    const original = button?.innerHTML;
    const fd = new FormData(form);
    if (pin !== null) fd.set('pin', pin);
    if (button) { button.disabled = true; button.classList.add('is-busy'); button.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Enviando'; }
    const pendingStatus = form.dataset.pendingStatus;
    if (pendingStatus) setStatusBadge($('[data-role="server-status"]'), pendingStatus);
    try {
      const res = await fetch(form.action, {method: (form.method || 'POST').toUpperCase(), body: fd, headers: {'X-Requested-With':'XMLHttpRequest','Accept':'application/json'}});
      let data = {}; try { data = await res.json(); } catch (_) {}
      if (!res.ok) throw new Error(data.error || `Erro HTTP ${res.status}`);
      toast(data.message || 'Ação enviada', 'O servidor será atualizado automaticamente.');
      if (form.action.includes('/security/pin') && form.querySelector('[name="new_pin"]')) form.reset();
      setTimeout(fetchServerState, 350);
      return true;
    } catch (err) {
      if (String(err.message).toLowerCase().includes('pin')) {
        if (pinError) pinError.textContent = err.message;
        if (modal) { modal.classList.add('open'); modal.setAttribute('aria-hidden','false'); pendingForm = form; }
        pinInput?.focus();
      } else {
        toast('Não foi possível executar', err.message || 'Erro inesperado.', 'error'); closePin();
      }
      return false;
    } finally {
      if (button) { button.disabled = false; button.classList.remove('is-busy'); button.innerHTML = original; }
    }
  }

  pinConfirm?.addEventListener('click', async () => {
    if (!pendingForm) return;
    const pin = pinInput?.value || '';
    if (!/^\d{4}$/.test(pin)) { if (pinError) pinError.textContent = 'Digite os 4 dígitos do PIN.'; pinInput?.focus(); return; }
    const form = pendingForm;
    const ok = await sendForm(form, pin);
    if (ok) closePin();
  });

  document.addEventListener('submit', e => {
    const form = e.target.closest('.js-async-form');
    if (!form) return;
    e.preventDefault();
    if (form.classList.contains('js-secure-form')) openPin(form);
    else sendForm(form);
  });

  if (window.io) {
    const socket = window.io({transports: ['websocket', 'polling']});
    socket.on('server_status', data => {
      if (currentServer) {
        if ((data.server_id || data.code) === currentServer) {
          updateCommon(data);
          const t = data.payload || {};
          renderPlayers(t.players || []); renderChat(t.chat || []); renderBackups(t.backups || []);
        }
      } else fetchOverview();
    });
    socket.on('server_command', data => {
      if (currentServer && data.server_code === currentServer) {
        if (data.status === 'DONE') toast('Comando concluído', data.rcon_command || data.command || 'Operação concluída.');
        else if (data.status === 'FAILED') toast('Comando falhou', data.error || 'Veja a página Logs.', 'error');
        setTimeout(fetchServerState, 250);
      }
    });
  }

  if (currentServer) { fetchServerState(); setInterval(fetchServerState, 3000); }
  if (endpoint === 'admin.dashboard') { fetchOverview(); setInterval(fetchOverview, 5000); }
})();
