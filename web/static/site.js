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

  // Prévia ao vivo do time no formulário
  const form = $('[data-team-form]');
  const preview = $('[data-team-preview]');
  if (form && preview) {
    const nameEl = $('[data-preview-name]', preview), tagEl = $('[data-preview-tag]', preview);
    const logoImg = $('[data-preview-logo]', preview), logoEmpty = $('[data-preview-logo-empty]', preview);
    const input = key => $(`[data-preview-input="${key}"]`, form);
    const render = () => {
      const name = input('name').value.trim(), tag = input('tag').value.trim().toUpperCase(), logo = input('logo').value.trim();
      nameEl.textContent = name || 'Nome do time';
      tagEl.textContent = tag || 'TAG';
      logoEmpty.textContent = tag || 'TAG';
      const valid = /^https:\/\/\S+$/.test(logo);
      logoImg.hidden = !valid; logoEmpty.hidden = valid;
      if (valid && logoImg.src !== logo) logoImg.src = logo;
    };
    logoImg.addEventListener('error', () => { logoImg.hidden = true; logoEmpty.hidden = false; });
    $$('[data-preview-input]', form).forEach(el => el.addEventListener('input', render));
    render();
  }
})();
