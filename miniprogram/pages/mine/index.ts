import { api } from '../../core/api';
import { auth } from '../../core/auth';
import { selectTab } from '../../core/leave';
import { cacheRemoteMedia } from '../../core/media';
import { Pager } from '../../core/paging';
import { myCard } from '../../core/presentation';
import { goLogin } from '../../core/source';
import { ApiError, errorMessage } from '../../core/transport';
import { MyWorkCard, PageResult, TapEvent } from '../../core/types';
Page({
  data: { username: '', ready: false, checking: true, loading: false, list: [] as ReturnType<typeof myCard<MyWorkCard>>[], error: '', actionError: '', done: false, total: 0, deleting: 0, mediaFailures: {} as Record<string, boolean>, resolvedCovers: {} as Record<number, string> },
  pager: new Pager<MyWorkCard>(10), prompted: false, generation: 0,
  onShow() { selectTab(this, 'mine'); void this.refresh(); },
  onUnload() { this.generation++; this.pager.reset(); },
  onPullDownRefresh() { void this.refresh(); },
  onReachBottom() { void this.loadMore(); },
  sync() { const resolved = this.data.resolvedCovers; this.setData({ list: this.pager.list.map(work => { const card = myCard(work); return resolved[work.id] ? { ...card, cover: resolved[work.id] } : card; }), loading: this.pager.loading, error: this.pager.error, done: this.pager.done, total: this.pager.total }); },
  async refresh() {
    const generation = ++this.generation; this.pager.reset(); this.sync(); this.setData({ checking: true, ready: false, username: '', mediaFailures: {}, resolvedCovers: {} });
    try {
      const user = await auth.confirm(); if (generation !== this.generation) return;
      if (!user) { if (!this.prompted) { this.prompted = true; goLogin({ page: 'mine' }); } return; }
      this.setData({ username: user.username, ready: true }); await this.loadMore();
    } catch (error) { if (generation === this.generation) this.setData({ error: errorMessage(error) }); }
    finally { if (generation === this.generation) this.setData({ checking: false }); wx.stopPullDownRefresh(); }
  },
  async loadMore() {
    if (!this.data.ready) return; const ticket = this.pager.begin(); if (!ticket) return; this.sync();
    try { this.pager.resolve(ticket, await api<PageResult<MyWorkCard>>(`/api/works/mine?page=${ticket.page}&page_size=10`, { protected: true, source: { page: 'mine' } })); }
    catch (error) { if (!this.pager.current(ticket)) return; this.pager.reject(ticket, errorMessage(error)); if (error instanceof ApiError && error.status === 401) { this.pager.reset(); this.setData({ ready: false, username: '' }); } }
    finally { this.sync(); }
  },
  open(event: TapEvent) { wx.navigateTo({ url: `/pages/detail/index?id=${event.currentTarget.dataset.id}` }); },
  edit(event: TapEvent) { const id = Number(event.currentTarget.dataset.id); if (this.pager.list.find(work => work.id === id)?.status === 'visible') wx.navigateTo({ url: `/pages/edit/index?id=${id}` }); },
  async remove(event: TapEvent) {
    const id = Number(event.currentTarget.dataset.id); if (this.data.deleting || this.pager.list.find(work => work.id === id)?.status !== 'visible') return;
    const generation = this.generation; this.setData({ deleting: id, actionError: '' });
    try {
      const confirmed = await new Promise<boolean>(resolve => wx.showModal({ title: '删除这份作品？', content: '删除后作品将被移除，两端不再公开展示，且不可恢复。', confirmText: '确认删除', confirmColor: '#B42318', cancelText: '取消', success: result => resolve(result.confirm), fail: () => resolve(false) }));
      if (!confirmed || generation !== this.generation) return;
      await api<{ id: number; status: 'removed' }>(`/api/works/${id}`, { method: 'DELETE', protected: true, source: { page: 'mine' } });
      if (generation !== this.generation) return;
      this.pager.list = this.pager.list.map(work => work.id === id ? { ...work, status: 'removed', cover_url: null } : work); this.sync(); wx.showToast({ title: '作品已移除', icon: 'none' });
    } catch (error) {
      if (generation !== this.generation) return;
      this.setData({ actionError: errorMessage(error) });
      if (error instanceof ApiError && error.status === 401) { this.pager.reset(); this.sync(); this.setData({ ready: false, username: '', error: errorMessage(error) }); }
      if (error instanceof ApiError && error.status === 409) await this.refresh();
    }
    finally { this.setData({ deleting: 0 }); }
  },
  login() { goLogin({ page: 'mine' }); },
  settings() { wx.navigateTo({ url: '/pages/settings/index' }); },
  publish() { wx.switchTab({ url: '/pages/publish/index' }); },
  imageError(event: TapEvent) {
    const id = Number(event.currentTarget.dataset.id);
    const card = this.data.list.find(item => item.id === id);
    if (!card?.cover || this.data.resolvedCovers[id]) { this.setData({ [`mediaFailures.${id}`]: true }); return; }
    void cacheRemoteMedia(card.cover).then(path => {
      this.setData({ [`resolvedCovers.${id}`]: path, [`mediaFailures.${id}`]: false }, () => this.sync());
    }).catch(() => this.setData({ [`mediaFailures.${id}`]: true }));
  },
  retryImage(event: TapEvent) {
    const id = Number(event.currentTarget.dataset.id);
    this.setData({ [`mediaFailures.${id}`]: false, [`resolvedCovers.${id}`]: '' }, () => this.sync());
  }
});
