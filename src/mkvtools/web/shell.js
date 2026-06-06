// Sidebar + topbar dung chung cho moi trang (tru Dang nhap). Goi: MKVShell('catch','Bắt tay')
(function () {
  const NAV = [
    { href: '/', icon: 'dashboard', label: 'Hàng đợi', key: 'queue' },
    { href: '/catch', icon: 'ads_click', label: 'Bắt tay', key: 'catch' },
    { href: '/classic', icon: 'folder_open', label: 'Inbox (cổ điển)', key: 'classic' },
    { href: '/admin', icon: 'admin_panel_settings', label: 'Quản trị', key: 'admin', admin: true },
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
      <div class="px-panel-padding mb-stack-lg">
        <h1 class="font-headline-md text-headline-md font-bold text-primary-fixed-dim tracking-tight">MKVTOOLS</h1>
        <p class="font-label-sm text-label-sm text-on-surface-variant mt-unit uppercase tracking-widest">Command Center</p>
      </div>
      <div class="flex-1 flex flex-col gap-unit px-unit">${items}</div>
      <div class="mt-auto px-unit pt-stack-md border-t border-outline-variant/20 mx-gutter">
        <a href="/logout" class="flex items-center gap-stack-md px-gutter py-stack-sm rounded-lg text-on-surface-variant hover:text-error hover:bg-error-container/10 transition-colors"><span class="ms">logout</span><span class="font-label-sm text-label-sm">Đăng xuất</span></a>
      </div>`;
    top.innerHTML = `
      <div class="font-headline-md text-headline-md text-primary-fixed-dim tracking-tight">${title}</div>
      <div class="flex items-center gap-stack-md">
        <span id="shell-disk" class="font-label-sm text-label-sm text-on-surface-variant hidden md:flex items-center gap-unit"><span class="ms text-[18px]">storage</span><span id="shell-diskv">—</span></span>
        <span id="shell-user" class="font-label-sm text-label-sm text-on-surface-variant"></span>
        <span class="ms text-on-surface-variant text-[22px]">account_circle</span>
      </div>`;
    fetch('/me', { cache: 'no-store' }).then(r => r.json()).then(u => {
      const el = document.getElementById('shell-user');
      if (el) el.textContent = (u.username || '') + (u.role ? ' (' + u.role + ')' : '');
      if (u.role !== 'admin') side.querySelectorAll('[data-admin="true"]').forEach(a => a.style.display = 'none');
    }).catch(() => {});
  };
})();
