(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // Menu mobile
  const toggle = $('[data-nav-toggle]');
  const nav = $('[data-nav]');
  if (toggle && nav) toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    toggle.innerHTML = open ? '<i class="bi bi-x-lg"></i>' : '<i class="bi bi-list"></i>';
  });

  // Dropdown do usuário
  $$('[data-dropdown]').forEach(dd => {
    $('[data-dropdown-toggle]', dd).addEventListener('click', e => { e.stopPropagation(); dd.classList.toggle('open'); });
  });
  document.addEventListener('click', e => {
    $$('[data-dropdown].open').forEach(dd => { if (!dd.contains(e.target)) dd.classList.remove('open'); });
  });

  // Mensagens: fechar e sumir sozinhas
  $$('[data-flash]').forEach((el, i) => {
    const close = () => { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 300); };
    $('[data-flash-close]', el)?.addEventListener('click', close);
    if (!el.classList.contains('flash-danger')) setTimeout(close, 6000 + i * 800);
  });

  // Confirmação antes de enviar formulários sensíveis
  $$('form[data-confirm]').forEach(form => form.addEventListener('submit', e => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  }));

  // Copiar link de convite
  $$('[data-copy]').forEach(btn => btn.addEventListener('click', async () => {
    const input = $('[data-copy-source]', btn.parentElement);
    try { await navigator.clipboard.writeText(input.value); }
    catch { input.select(); document.execCommand('copy'); }
    const old = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-check2"></i> Copiado';
    setTimeout(() => { btn.innerHTML = old; }, 1800);
  }));

  // Chaveamento: destaca o caminho do time
  $$('[data-bracket]').forEach(br => {
    const root = br.closest('main') || document;
    br.addEventListener('mouseover', e => {
      const bt = e.target.closest('.bt[data-team]');
      $$('.bt.hl', root).forEach(el => el.classList.remove('hl'));
      if (bt) $$(`.bt[data-team="${bt.dataset.team}"]`, root).forEach(el => el.classList.add('hl'));
    });
    br.addEventListener('mouseleave', () => $$('.bt.hl', root).forEach(el => el.classList.remove('hl')));
  });

  // Pagamento Pix: contagem regressiva + verificação automática
  const checkout = $('[data-reg-status-url]');
  if (checkout) {
    const pix = $('[data-pix-expires]', checkout);
    const cd = $('[data-countdown]', checkout);
    if (pix && cd && pix.dataset.pixExpires) {
      const end = new Date(pix.dataset.pixExpires).getTime();
      const tick = () => {
        const s = Math.max(0, Math.round((end - Date.now()) / 1000));
        cd.textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
        if (s === 0) location.reload();
      };
      tick(); setInterval(tick, 1000);
    }
    if (checkout.dataset.regStatus === 'AWAITING_PAYMENT' && pix) {
      const poll = async () => {
        try {
          const r = await fetch(checkout.dataset.regStatusUrl, {headers: {Accept: 'application/json'}});
          const d = await r.json();
          if (d.status !== 'AWAITING_PAYMENT') location.reload();
        } catch (_) {}
      };
      setInterval(poll, 5000);
    }
  }

  // Página da partida: estado ao vivo + veto
  const matchEl = $('[data-match]');
  if (matchEl) {
    const initial = $('[data-initial-state]', matchEl);
    let state = initial ? JSON.parse(initial.textContent) : null;
    let lastSig = '';
    const grid = $('[data-veto-grid]', matchEl), turn = $('[data-veto-turn]', matchEl), help = $('[data-veto-help]', matchEl);
    const section = $('[data-veto-section]', matchEl);
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    const renderVeto = st => {
      if (!grid || !st) return;
      const v = st.veto; const nxt = v.next;
      const canAct = nxt && (v.my_slot === nxt.slot || v.is_admin);
      const remaining = v.pool.filter(p => !p.action);
      grid.innerHTML = v.pool.map(p => {
        let cls = p.action || '', tag = '';
        if (p.action === 'ban') tag = `${esc(p.team)} baniu`;
        else if (p.action === 'pick') tag = `${esc(p.team)} escolheu`;
        else if (!nxt && st.maps.some(m => m.name === p.name)) { cls = 'decider'; tag = 'Decisivo'; }
        const click = canAct && !p.action ? 'clickable' : '';
        return `<button type="button" class="veto-card ${cls} ${click}" style="--map-c:${esc(p.color)}" data-map="${esc(p.name)}" ${click ? '' : 'disabled'}>${tag ? `<span class="vc-tag">${tag}</span>` : ''}<small>${click ? (nxt.action === 'ban' ? 'Clique para banir' : 'Clique para escolher') : '&nbsp;'}</small><b>${esc(p.name)}</b></button>`;
      }).join('');
      if (nxt) {
        const verb = nxt.action === 'ban' ? 'banir' : 'escolher';
        turn.textContent = v.my_slot === nxt.slot ? `Sua vez de ${verb}!` : `Vez de ${nxt.team} ${verb}`;
        turn.classList.toggle('mine', v.my_slot === nxt.slot);
        help.textContent = v.my_slot ? 'Você é capitão: toque no mapa quando for a sua vez.' : `Restam ${remaining.length} mapas. O veto atualiza sozinho.`;
      } else if (st.maps.length) {
        turn.textContent = 'Veto concluído'; turn.classList.remove('mine');
        help.textContent = `Mapa${st.maps.length > 1 ? 's' : ''}: ${st.maps.map(m => m.name).join(', ')}. Lados no round faca.`;
      } else { turn.textContent = 'Aguardando abertura'; help.textContent = ''; }
      if (section && (st.status === 'VETO' || st.maps.length)) section.hidden = false;
    };

    const apply = async st => {
      state = st; renderVeto(st);
      const s1 = $('[data-score="1"]', matchEl), s2 = $('[data-score="2"]', matchEl);
      if (s1) s1.textContent = st.team1_score; if (s2) s2.textContent = st.team2_score;
      const cm = $('[data-current-map]', matchEl); if (cm && st.current_map && st.status !== 'FINISHED') cm.textContent = st.current_map + (st.round ? ` · round ${st.round}` : '');
      const sig = JSON.stringify([st.status, st.team1_score, st.team2_score, st.round, st.maps.map(m => [m.status, m.team1, m.team2])]);
      if (lastSig && sig !== lastSig) {
        const statusChanged = JSON.parse(lastSig)[0] !== st.status || JSON.parse(lastSig)[4]?.length !== st.maps.length;
        if (statusChanged) { location.reload(); return; }
        try { const r = await fetch(matchEl.dataset.boardUrl); $('[data-scoreboard]', matchEl).innerHTML = await r.text(); } catch (_) {}
      }
      lastSig = sig;
    };

    grid?.addEventListener('click', async e => {
      const card = e.target.closest('.veto-card.clickable'); if (!card) return;
      const nxt = state.veto.next;
      if (!confirm(`${nxt.action === 'ban' ? 'Banir' : 'Escolher'} ${card.dataset.map}?`)) return;
      card.disabled = true;
      try {
        const r = await fetch(matchEl.dataset.vetoUrl, {method: 'POST', headers: {'Content-Type': 'application/json', Accept: 'application/json'}, body: JSON.stringify({map: card.dataset.map})});
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || 'Não foi possível registrar.');
        apply(d.state);
      } catch (err) { alert(err.message); card.disabled = false; }
    });

    if (state) apply(state);
    const poll = async () => {
      if (document.hidden || (state && state.status === 'FINISHED')) return;
      try { const r = await fetch(matchEl.dataset.stateUrl, {headers: {Accept: 'application/json'}}); apply(await r.json()); } catch (_) {}
    };
    setInterval(poll, 3000);
  }

  // Envio de imagem: valida no navegador e mostra a prévia antes de enviar
  const MAX_UPLOAD = 5 * 1024 * 1024;
  $$('[data-upload]').forEach(box => {
    const input = $('[data-upload-input]', box), img = $('[data-upload-img]', box), name = $('[data-upload-name]', box);
    input?.addEventListener('change', () => {
      const file = input.files[0];
      if (!file) return;
      if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { alert('Envie uma imagem JPG, PNG, WEBP ou GIF.'); input.value = ''; return; }
      if (file.size > MAX_UPLOAD) { alert('A imagem pode ter no máximo 5 MB.'); input.value = ''; return; }
      if (name) name.textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
      if (img) {
        img.src = URL.createObjectURL(file); img.hidden = false;
        img.previousElementSibling?.setAttribute('hidden', '');
      }
      input.dispatchEvent(new Event('preview'));
    });
  });

  // Prévia ao vivo do time no formulário
  const form = $('[data-team-form]');
  const preview = $('[data-team-preview]');
  if (form && preview) {
    const nameEl = $('[data-preview-name]', preview), tagEl = $('[data-preview-tag]', preview);
    const logoImg = $('[data-preview-logo]', preview), logoEmpty = $('[data-preview-logo-empty]', preview);
    const input = key => $(`[data-preview-input="${key}"]`, form);
    const remove = $('[data-remove-logo]', form);
    const original = logoImg.getAttribute('src');
    const render = () => {
      const name = input('name').value.trim(), tag = input('tag').value.trim().toUpperCase();
      nameEl.textContent = name || 'Nome do time';
      tagEl.textContent = tag || 'TAG';
      logoEmpty.textContent = tag || 'TAG';
      const file = input('logo').files[0];
      let src = file ? URL.createObjectURL(file) : (remove?.checked ? null : original);
      logoImg.hidden = !src; logoEmpty.hidden = !!src;
      if (src) logoImg.src = src;
    };
    logoImg.addEventListener('error', () => { logoImg.hidden = true; logoEmpty.hidden = false; });
    ['name', 'tag'].forEach(k => input(k).addEventListener('input', render));
    input('logo').addEventListener('preview', render);
    remove?.addEventListener('change', render);
    render();
  }
})();
