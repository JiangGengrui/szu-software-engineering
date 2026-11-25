import { api } from '../../core/api';
import { auth } from '../../core/auth';
import { goLogin } from '../../core/source';
import { ApiError, errorMessage } from '../../core/transport';
import { InputEvent } from '../../core/types';
import { validatePasswordChange } from '../../core/validation';
Page({
  data: { username: '', ready: false, loading: true, old_password: '', new_password: '', confirmation: '', busy: false, error: '', field: '' },
  prompted: false,
  onShow() { void this.enter(); },
  onHide() { this.clearPasswords(); },
  clearPasswords() { this.setData({ old_password: '', new_password: '', confirmation: '' }); },
  async enter() {
    this.setData({ loading: true });
    try { const user = await auth.confirm(); this.setData({ ready: !!user, username: user?.username || '' }); if (!user && !this.prompted) { this.prompted = true; this.login(); } }
    catch (error) { this.setData({ ready: false, error: errorMessage(error) }); }
    finally { this.setData({ loading: false }); }
  },
  input(event: InputEvent) { if (this.data.busy) return; const field = event.currentTarget.dataset.field as string; if (['old_password', 'new_password', 'confirmation'].includes(field)) this.setData({ [field]: event.detail.value, field: '', error: '' }); },
  async changePassword() {
    if (this.data.busy) return;
    const { old_password, new_password, confirmation } = this.data;
    const issue = validatePasswordChange(old_password, new_password, confirmation);
    if (issue) { this.setData({ error: issue.message, field: issue.field }); return; }
    this.setData({ busy: true, error: '', field: '' });
    try {
      await api<null>('/api/auth/password', { method: 'POST', protected: true, source: { page: 'settings' }, data: { old_password, new_password } });
      auth.clear(); this.setData({ ready: false, username: '' }); wx.showToast({ title: '密码已更新，请重新登录', icon: 'none' }); this.login();
    } catch (error) { this.setData({ error: errorMessage(error), ready: !!auth.user() }); }
    finally { this.clearPasswords(); this.setData({ busy: false }); }
  },
  async logout() {
    if (this.data.busy) return;
    this.setData({ busy: true, error: '' });
    try {
      if (auth.token()) await api<null>('/api/auth/logout', { method: 'POST', protected: true, redirect: false });
      auth.clear(); this.setData({ ready: false, username: '' }); wx.switchTab({ url: '/pages/home/index' });
    } catch (error) {
      auth.clear(); this.setData({ ready: false, username: '' });
      if (error instanceof ApiError && error.status === 401) wx.switchTab({ url: '/pages/home/index' });
      else this.setData({ error: `已清理本机登录态，但服务端退出未确认；不能确认旧凭据已撤销。${errorMessage(error)}` });
    } finally { this.clearPasswords(); this.setData({ busy: false }); }
  },
  login() { goLogin({ page: 'settings' }); },
  home() { wx.switchTab({ url: '/pages/home/index' }); }
});
