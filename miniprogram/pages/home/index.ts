import { api } from '../../core/api';
import { auth } from '../../core/auth';
import { selectTab } from '../../core/leave';
import { cacheRemoteMedia } from '../../core/media';
import { Pager, listQuery } from '../../core/paging';
import { publicCard } from '../../core/presentation';
import { goLogin } from '../../core/source';
import { errorMessage } from '../../core/transport';
import { InputEvent, PageResult, Tag, TapEvent, WorkCard } from '../../core/types';
Page({
  data: { date: '', selectedTags: [] as string[], tags: [] as (Tag & { checked: boolean })[], showTags: false, tagLoading: false, tagError: '', list: [] as ReturnType<typeof publicCard>[], loading: false, error: '', total: 0, done: false, username: '', skeletons: [1, 2, 3], mediaFailures: {} as Record<string, boolean>, resolvedCovers: {} as Record<number, string> },
  pager: new Pager<WorkCard>(10),
  onShow() { selectTab(this, 'home'); this.refresh(); void this.loadTags(); void auth.confirm().then(user => this.setData({ username: user?.username || '' })).catch(() => this.setData({ username: '' })); },
  onUnload() { this.pager.reset(); },
  onPullDownRefresh() { this.refresh(); },
  onReachBottom() { void this.loadMore(); },
  sync() { const resolved = this.data.resolvedCovers; this.setData({ list: this.pager.list.map(work => { const card = publicCard(work); return resolved[work.id] ? { ...card, cover: resolved[work.id] } : card; }), total: this.pager.total, loading: this.pager.loading, error: this.pager.error, done: this.pager.done }); },
  refresh() { this.pager.reset(); this.setData({ mediaFailures: {}, resolvedCovers: {} }); this.sync(); void this.loadMore(); },
  async loadMore() {
    const ticket = this.pager.begin(); if (!ticket) return; this.sync();
    try { this.pager.resolve(ticket, await api<PageResult<WorkCard>>('/api/works?' + listQuery(this.data.date, this.data.selectedTags, ticket.page))); }
    catch (error) { this.pager.reject(ticket, errorMessage(error)); }
    finally { this.sync(); wx.stopPullDownRefresh(); }
  },
  async loadTags() {
    this.setData({ tagLoading: true, tagError: '' });
    try { const tags = await api<Tag[]>('/api/tags'); this.setData({ tags: tags.map(tag => ({ ...tag, checked: this.data.selectedTags.includes(tag.name) })) }); }
    catch (error) { this.setData({ tagError: errorMessage(error) }); }
    finally { this.setData({ tagLoading: false }); }
  },
  chooseDate(event: InputEvent) { this.setData({ date: event.detail.value }); this.refresh(); },
  clearDate() { this.setData({ date: '' }); this.refresh(); },
  clearFilters() { this.setData({ date: '', selectedTags: [], tags: this.data.tags.map(tag => ({ ...tag, checked: false })) }); this.refresh(); },
  toggleTags() { this.setData({ showTags: !this.data.showTags }); },
  changeTags(event: WechatMiniprogram.CustomEvent<{ value: string[] }>) { const names = event.detail.value; this.setData({ selectedTags: names, tags: this.data.tags.map(tag => ({ ...tag, checked: names.includes(tag.name) })) }); this.refresh(); },
  removeTag(event: TapEvent) { const names = this.data.selectedTags.filter(tag => tag !== event.currentTarget.dataset.value); this.setData({ selectedTags: names, tags: this.data.tags.map(tag => ({ ...tag, checked: names.includes(tag.name) })) }); this.refresh(); },
  open(event: TapEvent) { wx.navigateTo({ url: `/pages/detail/index?id=${event.currentTarget.dataset.id}` }); },
  login() { goLogin({ page: 'home' }); },
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
