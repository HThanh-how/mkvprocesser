// Sidebar + topbar dung chung cho moi trang (tru Dang nhap). Goi: MKVShell('catch','Bắt tay')
(function () {
  const NAV = [
    { href: '/', icon: 'download', label: 'Tải video', key: 'shorts' },
    { href: '/queue-ui', icon: 'dashboard', label: 'Xử lý MKV', key: 'queue' },
    { href: '/catch', icon: 'ads_click', label: 'Bắt tay', key: 'catch' },
    { href: '/videos', icon: 'video_library', label: 'Video', key: 'videos' },
    { href: '/admin', icon: 'admin_panel_settings', label: 'Quản trị', key: 'admin', admin: true },
    { href: '/settings', icon: 'settings', label: 'Cài đặt', key: 'settings', admin: true },
  ];
  window.MKVShell = function (active, title) {
    const side = document.getElementById('shell-side');
    const top = document.getElementById('shell-top');
    const items = NAV.map(n => {
      const on = n.key === active;
      const cls = on
        ? "flex items-center gap-stack-md px-gutter py-stack-sm rounded-lg text-primary-fixed-dim bg-primary-container/10 border-r-2 border-primary-fixed-dim transition-all"
        : "flex items-center gap-stack-md px-gutter py-stack-sm rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors";
      const fill = on ? "font-variation-settings:'FILL' 1" : "";
      return `<a href="${n.href}" data-admin="${!!n.admin}" class="${cls}"><span class="ms" style="${fill}">${n.icon}</span><span class="font-label-sm text-label-sm">${n.label}</span></a>`;
    }).join('');
    side.innerHTML = `
      <div class="px-panel-padding mb-stack-lg flex items-start justify-between gap-stack-sm">
        <div>
          <div class="font-headline-md text-headline-md font-bold text-primary-fixed-dim tracking-tight">MKVTOOLS</div>
          <p class="font-label-sm text-label-sm text-on-surface-variant mt-unit uppercase tracking-widest">Command Center</p>
        </div>
        <button id="shell-side-close" type="button" aria-label="Đóng menu" title="Đóng menu"><span class="ms text-[22px]">close</span></button>
      </div>
      <div class="flex-1 flex flex-col gap-unit px-unit">${items}</div>
      <div class="mt-auto px-unit pt-stack-md border-t border-outline-variant/20 mx-gutter">
        <a href="/logout" class="flex items-center gap-stack-md px-gutter py-stack-sm rounded-lg text-on-surface-variant hover:text-error hover:bg-error-container/10 transition-colors"><span class="ms">logout</span><span class="font-label-sm text-label-sm">Đăng xuất</span></a>
      </div>`;
    top.innerHTML = `
      <div id="shell-top-left" class="flex items-center gap-stack-sm">
        <button id="shell-nav-toggle" type="button" aria-label="Mở menu" aria-controls="shell-side" aria-expanded="false" title="Menu"><span class="ms text-[24px]">menu</span></button>
        <div id="shell-page-title" class="font-headline-md text-headline-md text-primary-fixed-dim tracking-tight">${title}</div>
      </div>
      <div class="flex items-center gap-stack-md">
        <span id="shell-disk" class="font-label-sm text-label-sm text-on-surface-variant hidden md:flex items-center gap-unit"><span class="ms text-[18px]">storage</span><span id="shell-diskv">—</span></span>
        <div class="relative">
          <button id="shell-acct" class="flex items-center gap-unit text-on-surface-variant hover:text-primary-fixed-dim transition-colors" title="Tài khoản">
            <span id="shell-user" class="font-label-sm text-label-sm"></span><span class="ms text-[22px]">account_circle</span>
          </button>
          <div id="shell-menu" class="hidden absolute right-0 mt-2 w-56 glass-panel rounded-lg overflow-hidden shadow-2xl z-[60]">
            <div class="px-gutter py-stack-sm border-b border-outline-variant/20"><div id="shell-menu-user" class="text-on-surface text-sm"></div></div>
            <button id="shell-pw" class="w-full text-left px-gutter py-stack-sm text-sm text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface flex items-center gap-unit transition-colors"><span class="ms text-[18px]">key</span>Đổi mật khẩu</button>
            <a href="/logout" class="w-full text-left px-gutter py-stack-sm text-sm text-on-surface-variant hover:bg-error-container/10 hover:text-error flex items-center gap-unit transition-colors"><span class="ms text-[18px]">logout</span>Đăng xuất</a>
          </div>
        </div>
      </div>`;

    // Modal doi mat khau cua chinh minh (gan vao body 1 lan)
    if (!document.getElementById('shell-pwmodal')) {
      const m = document.createElement('div');
      m.id = 'shell-pwmodal';
      m.className = 'hidden fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-center justify-center';
      m.innerHTML = `<div class="glass-panel rounded-xl p-panel-padding w-[360px]" id="shell-pwbox">
        <h3 class="font-headline-md text-base font-semibold mb-stack-md flex items-center gap-unit"><span class="ms text-primary-fixed-dim text-[18px]">key</span>Đổi mật khẩu của tôi</h3>
        <input id="shell-pwnew" type="password" placeholder="Mật khẩu mới" class="w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-gutter py-stack-sm text-on-surface focus:outline-none focus:border-primary-fixed-dim placeholder-on-surface-variant/40">
        <div id="shell-pwmsg" class="text-sm mt-stack-sm"></div>
        <div class="flex justify-end gap-stack-sm mt-stack-md">
          <button id="shell-pwcancel" class="h-9 px-gutter rounded-lg bg-surface-container-high text-on-surface-variant hover:text-on-surface text-sm">Huỷ</button>
          <button id="shell-pwsave" class="h-9 px-gutter rounded-lg bg-primary-fixed-dim text-on-primary-fixed font-label-sm text-label-sm uppercase">Lưu</button>
        </div></div>`;
      document.body.appendChild(m);
    }

    const $ = id => document.getElementById(id);
    let backdrop = $('shell-backdrop');
    if (!backdrop) {
      backdrop = document.createElement('button');
      backdrop.id = 'shell-backdrop';
      backdrop.type = 'button';
      backdrop.setAttribute('aria-label', 'Đóng menu');
      document.body.appendChild(backdrop);
    }

    const menu = $('shell-menu'), modal = $('shell-pwmodal');
    const navToggle = $('shell-nav-toggle'), sideClose = $('shell-side-close');
    const setNavOpen = (open, restoreFocus) => {
      document.body.classList.toggle('shell-nav-open', open);
      navToggle.setAttribute('aria-expanded', String(open));
      navToggle.setAttribute('aria-label', open ? 'Đóng menu' : 'Mở menu');
      if (open) sideClose.focus();
      else if (restoreFocus) navToggle.focus();
    };
    navToggle.onclick = () => setNavOpen(!document.body.classList.contains('shell-nav-open'), false);
    sideClose.onclick = () => setNavOpen(false, true);
    backdrop.onclick = () => setNavOpen(false, true);
    side.querySelectorAll('a').forEach(a => a.addEventListener('click', () => setNavOpen(false, false)));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && document.body.classList.contains('shell-nav-open')) setNavOpen(false, true);
      if (e.key === 'Tab' && document.body.classList.contains('shell-nav-open')) {
        const focusable = [...side.querySelectorAll('a[href], button:not([disabled])')]
          .filter(el => el.offsetParent !== null);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
    const desktop = window.matchMedia('(min-width: 768px)');
    const closeOnDesktop = e => { if (e.matches) setNavOpen(false, false); };
    if (desktop.addEventListener) desktop.addEventListener('change', closeOnDesktop);

    $('shell-acct').onclick = e => { e.stopPropagation(); menu.classList.toggle('hidden'); };
    document.addEventListener('click', () => menu.classList.add('hidden'));
    menu.addEventListener('click', e => e.stopPropagation());
    $('shell-pw').onclick = () => { menu.classList.add('hidden'); $('shell-pwmsg').textContent = ''; $('shell-pwnew').value = ''; modal.classList.remove('hidden'); $('shell-pwnew').focus(); };
    $('shell-pwcancel').onclick = () => modal.classList.add('hidden');
    modal.addEventListener('click', e => { if (e.target === modal) modal.classList.add('hidden'); });
    $('shell-pwsave').onclick = async () => {
      const v = $('shell-pwnew').value, msg = $('shell-pwmsg');
      if (!v || v.length < 4) { msg.textContent = 'Mật khẩu tối thiểu 4 ký tự.'; msg.className = 'text-sm mt-stack-sm text-error'; return; }
      const f = new FormData(); f.append('password', v);
      let d = {}; try { d = await (await fetch('/me/password', { method: 'POST', body: f })).json(); } catch (e) {}
      if (d.ok) { msg.textContent = 'Đã đổi mật khẩu ✓'; msg.className = 'text-sm mt-stack-sm text-ok'; setTimeout(() => modal.classList.add('hidden'), 900); }
      else { msg.textContent = d.error || 'Lỗi đổi mật khẩu'; msg.className = 'text-sm mt-stack-sm text-error'; }
    };

    fetch('/me', { cache: 'no-store' }).then(r => r.json()).then(u => {
      const lbl = (u.username || '') + (u.role ? ' (' + u.role + ')' : '');
      if ($('shell-user')) $('shell-user').textContent = lbl;
      if ($('shell-menu-user')) $('shell-menu-user').textContent = lbl;
      if (u.role !== 'admin') side.querySelectorAll('[data-admin="true"]').forEach(a => a.style.display = 'none');
    }).catch(() => {});
    fetch('/queue', { cache: 'no-store' }).then(r => r.json()).then(q => { const d = $('shell-diskv'); if (d && q.disk_free_gb != null) d.textContent = q.disk_free_gb + ' GB'; }).catch(() => {});
  };
})();
