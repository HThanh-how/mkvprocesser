/* Gan CSRF token vao moi request thay doi trang thai.
 *
 * Server dat cookie `mkv_csrf` (khong httponly) tren moi response. File nay lo
 * hai duong gui token nguoc len, nen cac trang khac khong phai sua gi:
 *   1. window.fetch  -> them header X-CSRF-Token (chi cho request cung goc)
 *   2. form submit   -> chen <input hidden name=csrf_token> ngay truoc khi gui
 *
 * Bat submit o pha capture tren document nen form tao dong bang JS (vd bang
 * quan tri nguoi dung) cung duoc bao ve, khong can dang ky rieng.
 */
(function () {
  var UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i;

  function token() {
    var m = document.cookie.match(/(?:^|;\s*)mkv_csrf=([^;]*)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function sameOrigin(url) {
    if (!/^[a-z][a-z0-9+.-]*:/i.test(url)) return true;   // duong dan tuong doi
    return url.indexOf(location.origin + '/') === 0 || url === location.origin;
  }

  var _fetch = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var method = init.method || (input && input.method) || 'GET';
    if (UNSAFE.test(method) && sameOrigin(url)) {
      var h = new Headers(init.headers || (input && input.headers) || {});
      h.set('X-CSRF-Token', token());
      init.headers = h;
    }
    return _fetch.call(this, input, init);
  };

  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f || f.tagName !== 'FORM' || !UNSAFE.test(f.method || 'GET')) return;
    var i = f.querySelector('input[name="csrf_token"]');
    if (!i) {
      i = document.createElement('input');
      i.type = 'hidden';
      i.name = 'csrf_token';
      f.appendChild(i);
    }
    i.value = token();
  }, true);
})();
