import { api } from '../../core/api';
import { auth } from '../../core/auth';
import { HOME, parseSource, returnTo, Source } from '../../core/source';
import { ApiError, errorMessage } from '../../core/transport';
import { AuthResult, InputEvent } from '../../core/types';
import { validateCredentials } from '../../core/validation';
// Shared across page instances: only the latest valid submit may accept an identity.
let latestAttempt = 0;
Page({
  data: { register: false, username: '', password: '', confirmation: '', busy: false, error: '', field: '' },
  source: HOME as Source, active: true,
  onLoad(options) {
    this.active = true;
    try { this.source = parseSource(typeof options.from === 'string' ? decodeURIComponent(options.from) : undefined); }
    catch { this.source = HOME; }
  },
  onHide() { this.setData({ password: '', confirmation: '' }); },
  onUnload() { this.active = false; },
  isCurrentAttempt(attempt: number) { return this.active && attempt === latestAttempt; },
  toggle(event: WechatMiniprogram.CustomEvent) { const register = event.currentTarget.dataset.mode === 'register'; if (!this.data.busy && register !== this.data.register) this.setData({ register, password: '', confirmation: '', error: '', field: '' }); },
  input(event: InputEvent) { if (this.data.busy) return; const field = event.currentTarget.dataset.field as string; if (['username', 'password', 'confirmation'].includes(field)) this.setData({ [field]: event.detail.value, error: '', field: '' }); },
  async submit() {
    if (!this.active || this.data.busy) return;
    const { username, password, confirmation, register } = this.data;
    const issue = validateCredentials(username, password, register ? confirmation : undefined);
    if (issue) { this.setData({ error: issue.message, field: issue.field }); return; }
    const attempt = ++latestAttempt;
    this.setData({ busy: true, error: '', field: '' });
    try {
      const result = await api<AuthResult>(`/api/auth/${register ? 'register' : 'login'}`, { method: 'POST', data: { username, password } });
      if (!this.isCurrentAttempt(attempt)) return;
      auth.accept(result); this.setData({ password: '', confirmation: '' }); returnTo(this.source);
    } catch (error) { if (!this.isCurrentAttempt(attempt)) return; this.setData({ error: errorMessage(error), field: error instanceof ApiError && error.code === 1006 ? 'username' : '', password: '', confirmation: '' }); }
    finally { if (this.isCurrentAttempt(attempt)) this.setData({ busy: false }); }
  },
  browse() { wx.switchTab({ url: '/pages/home/index' }); }
});
