(() => {
  'use strict';
  const button = document.getElementById('prototype-toggle');
  const dialog = document.getElementById('prototype-dialog');
  const frame = document.getElementById('prototype-frame');
  const close = document.getElementById('prototype-close');
  const status = document.getElementById('prototype-status');
  const origin = location.protocol === 'file:' ? '*' : location.origin;
  let opener, position, token = 0, pending = null;
  function hide() {
    if (!dialog.open) return;
    pending = null;
    dialog.close();
    button.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('prototype-open');
    opener?.focus({preventScroll:true});
    window.scrollTo(position.x, position.y);
  }
  function escape() {
    if (!dialog.open || pending !== null) return;
    pending = ++token;
    frame.contentWindow.postMessage({type:'research-reader:escape', token:pending}, origin);
    const requested = pending;
    setTimeout(() => {
      if (pending === requested) {
        pending = null;
        status.textContent = '原型暂未响应，可使用关闭按钮返回报告。';
      }
    }, 1800);
  }
  button.addEventListener('click', () => {
    if (dialog.open) { hide(); return; }
    opener = document.activeElement;
    position = {x:window.scrollX, y:window.scrollY};
    if (!frame.hasAttribute('src')) frame.src = frame.dataset.src;
    status.textContent = '';
    document.body.classList.add('prototype-open');
    dialog.showModal();
    button.setAttribute('aria-expanded','true');
    close.focus();
  });
  close.addEventListener('click', hide);
  dialog.addEventListener('cancel', event => { event.preventDefault(); escape(); });
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopImmediatePropagation(); escape();
    }
  }, true);
  window.addEventListener('message', event => {
    if (!dialog.open || event.source !== frame.contentWindow) return;
    if (location.protocol !== 'file:' && event.origin !== location.origin) return;
    const message = event.data;
    if (!message || typeof message !== 'object') return;
    if (message.type === 'research-reader:escape-request') escape();
    if (message.type === 'research-reader:escape-result' && pending !== null && message.token === pending) {
      pending = null;
      if (message.consumed === false) hide();
    }
  });
})();
