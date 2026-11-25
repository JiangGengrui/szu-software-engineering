'use strict';

// Progressive enhancement only: permissions, session validity and CSRF live on the server.
document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (form.dataset.submitting === 'yes') {
      event.preventDefault();
      return;
    }
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = 'yes';
    const button = form.querySelector('button[type="submit"]');
    const status = form.querySelector('.submit-status');
    if (button) {
      button.dataset.original = button.textContent;
      button.textContent = '正在提交…';
      button.disabled = true;
    }
    if (status) status.textContent = '正在等待服务器确认，请勿重复提交。';
    window.setTimeout(() => {
      if (form.dataset.submitting !== 'yes') return;
      if (status) status.textContent = '等待时间较长，结果尚未确认。请重新查询状态，不要自动重复操作。';
      // Keep a possibly successful write disabled. Browser reload/navigation can query its state.
      if (form.method.toLowerCase() === 'get') restore(form);
    }, 15000);
  });
});

function restore(form) {
  delete form.dataset.submitting;
  const button = form.querySelector('button[type="submit"]');
  if (button && button.dataset.original) {
    button.textContent = button.dataset.original;
    button.disabled = false;
  }
}

window.addEventListener('pageshow', () => {
  document.querySelectorAll('form').forEach(restore);
  document.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ''; });
});
