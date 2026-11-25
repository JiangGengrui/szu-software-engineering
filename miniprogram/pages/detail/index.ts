import { api, requireUser } from '../../core/api';
import { auth } from '../../core/auth';
import { Pager } from '../../core/paging';
import { detailView, displayTime, ratingText, unavailableState } from '../../core/presentation';
import { goLogin, workId } from '../../core/source';
import { errorMessage, unavailableCode } from '../../core/transport';
import { CommentPublic, InputEvent, PageResult, RatingStats, TapEvent, WorkDetail } from '../../core/types';
import { codePoints, trimText, validateComment, validateScore } from '../../core/validation';
Page({
  data: { work: null as WorkDetail | null, loading: true, error: '', unavailable: '', comments: [] as (CommentPublic & { time: string })[], commentsLoading: false, commentsDone: false, commentsError: '', commentError: '', comment: '', commentCount: 0, commentBusy: false, ratingText: '', myScore: null as number | null, score: 0, stars: [1, 2, 3, 4, 5], ratingBusy: false, ratingError: '', loggedIn: false, own: false, mediaError: '', videoHeight: 220 },
  id: 0, generation: 0, ratingGeneration: 0, scoreEdited: false, pager: new Pager<CommentPublic>(20),
  onLoad(options) { this.id = workId(options.id) || 0; },
  onShow() { void this.reload(); },
  onUnload() { this.generation++; this.ratingGeneration++; this.pager.reset(); },
  onPullDownRefresh() { void this.reload(); },
  onReachBottom() { void this.loadComments(); },
  stopUnavailable(code: number) { this.generation++; this.ratingGeneration++; this.pager.reset(); this.setData({ ...unavailableState(code), commentCount: 0, own: false, commentBusy: false, ratingBusy: false, error: '' }); },
  async reload() {
    if (!this.id) { this.stopUnavailable(1004); wx.stopPullDownRefresh(); return; }
    const generation = ++this.generation; this.ratingGeneration++; this.scoreEdited = false; this.pager.reset();
    this.setData({ work: null, loading: true, error: '', unavailable: '', comments: [], commentsLoading: false, commentsDone: false, commentsError: '', commentError: '', ratingError: '', ratingText: '', myScore: null, score: 0, ratingBusy: false, commentBusy: false, mediaError: '', loggedIn: false, own: false });
    try {
      const work = await api<WorkDetail>(`/api/works/${this.id}`);
      if (generation !== this.generation) return;
      this.setData({ work: detailView(work), loading: false, ratingText: ratingText(work.rating_avg, work.rating_count) });
      void this.loadComments();
      const user = await auth.confirm();
      if (generation !== this.generation) return;
      this.setData({ loggedIn: !!user, own: user?.id === work.user.id });
      if (user) await this.loadRating(generation);
    } catch (error) {
      if (generation !== this.generation) return;
      const code = unavailableCode(error);
      if (code) this.stopUnavailable(code);
      else if (this.data.work) this.setData({ loggedIn: false, own: false, ratingError: '登录状态暂时无法确认，可继续浏览；互动前请重试登录' });
      else this.setData({ error: errorMessage(error) });
    } finally { if (generation === this.generation) this.setData({ loading: false }); wx.stopPullDownRefresh(); }
  },
  isCurrentRating(generation: number, ratingGeneration: number) { return generation === this.generation && ratingGeneration === this.ratingGeneration; },
  async loadRating(generation: number) {
    if (generation !== this.generation || !this.data.work || this.data.ratingBusy) return;
    const ratingGeneration = ++this.ratingGeneration;
    try { const stats = await api<RatingStats>(`/api/works/${this.id}/rating`, { protected: true, source: { page: 'detail', id: this.id }, isCurrent: () => this.isCurrentRating(generation, ratingGeneration) }); if (this.isCurrentRating(generation, ratingGeneration)) this.setData({ myScore: stats.my_score, score: this.scoreEdited ? this.data.score : stats.my_score || 0, ratingText: ratingText(stats.rating_avg, stats.rating_count) }); }
    catch (error) { if (!this.isCurrentRating(generation, ratingGeneration)) return; const code = unavailableCode(error); if (code) this.stopUnavailable(code); else this.setData({ ratingError: errorMessage(error), loggedIn: !!auth.user() }); }
  },
  async loadComments() {
    if (!this.data.work || this.data.unavailable) return;
    const ticket = this.pager.begin(); if (!ticket) return;
    const generation = this.generation; this.setData({ commentsLoading: true, commentsError: '' });
    try { const result = await api<PageResult<CommentPublic>>(`/api/works/${this.id}/comments?page=${ticket.page}&page_size=20`); if (generation === this.generation) this.pager.resolve(ticket, result); }
    catch (error) { if (generation !== this.generation) return; const code = unavailableCode(error); if (code) { this.stopUnavailable(code); return; } this.pager.reject(ticket, errorMessage(error)); }
    finally { if (generation === this.generation) this.setData({ comments: this.pager.list.map(comment => ({ ...comment, time: displayTime(comment.created_at) })), commentsLoading: this.pager.loading, commentsDone: this.pager.done, commentsError: this.pager.error }); }
  },
  inputComment(event: InputEvent) { this.setData({ comment: event.detail.value, commentCount: codePoints(trimText(event.detail.value)), commentError: '' }); },
  async sendComment() {
    if (!this.data.work || this.data.commentBusy) return;
    this.setData({ commentBusy: true, commentError: '' }); const generation = this.generation;
    try {
      if (!await requireUser({ page: 'detail', id: this.id }, () => generation === this.generation)) return;
      if (generation !== this.generation) return;
      const issue = validateComment(this.data.comment); if (issue) { this.setData({ commentError: issue.message }); return; }
      await api<CommentPublic>(`/api/works/${this.id}/comments`, { method: 'POST', protected: true, source: { page: 'detail', id: this.id }, isCurrent: () => generation === this.generation, data: { content: trimText(this.data.comment) } });
      if (generation !== this.generation) return;
      this.setData({ comment: '', commentCount: 0, loggedIn: true }); this.pager.reset(); await this.loadComments();
    } catch (error) { if (generation !== this.generation) return; const code = unavailableCode(error); if (code) this.stopUnavailable(code); else this.setData({ commentError: errorMessage(error), loggedIn: !!auth.user() }); }
    finally { if (generation === this.generation) this.setData({ commentBusy: false }); }
  },
  selectScore(event: TapEvent) { if (!this.data.own && !this.data.ratingBusy) { this.scoreEdited = true; this.setData({ score: Number(event.currentTarget.dataset.score), ratingError: '' }); } },
  async sendRating() {
    if (!this.data.work || this.data.ratingBusy) return;
    const generation = this.generation, ratingGeneration = ++this.ratingGeneration;
    // Invalidate earlier reads before awaiting identity; they must not reset the selected score.
    this.setData({ ratingBusy: true, ratingError: '' });
    try {
      if (!await requireUser({ page: 'detail', id: this.id }, () => generation === this.generation)) return;
      if (!this.isCurrentRating(generation, ratingGeneration) || !this.data.work) return;
      const own = auth.user()?.id === this.data.work.user.id; this.setData({ own });
      const issue = validateScore(this.data.score, own); if (issue) { this.setData({ ratingError: issue.message }); return; }
      const stats = await api<RatingStats>(`/api/works/${this.id}/rating`, { method: 'PUT', protected: true, source: { page: 'detail', id: this.id }, isCurrent: () => this.isCurrentRating(generation, ratingGeneration), data: { score: this.data.score } });
      if (this.isCurrentRating(generation, ratingGeneration)) { this.scoreEdited = false; this.setData({ loggedIn: true, myScore: stats.my_score, score: stats.my_score || 0, ratingText: ratingText(stats.rating_avg, stats.rating_count) }); }
    } catch (error) { if (!this.isCurrentRating(generation, ratingGeneration)) return; const code = unavailableCode(error); if (code) this.stopUnavailable(code); else this.setData({ ratingError: errorMessage(error), loggedIn: !!auth.user() }); }
    finally { if (this.isCurrentRating(generation, ratingGeneration)) this.setData({ ratingBusy: false }); }
  },
  preview(event: TapEvent) { const urls = this.data.work?.media.filter(media => media.kind === 'image').map(media => media.url) || []; if (urls.length) wx.previewImage({ current: event.currentTarget.dataset.value || urls[0], urls }); },
  async mediaFailed() {
    const generation = this.generation; this.setData({ mediaError: '媒体加载失败，可重试；请检查网络及媒体是否仍可用' });
    try { await api<WorkDetail>(`/api/works/${this.id}`); }
    catch (error) { if (generation === this.generation && unavailableCode(error)) this.stopUnavailable(unavailableCode(error)); }
  },
  videoMetadata(event: WechatMiniprogram.CustomEvent<{ width: number; height: number }>) { const { width, height } = event.detail; if (width > 0 && height > 0) this.setData({ videoHeight: (wx.getWindowInfo().windowWidth - 64) * height / width }); },
  login() { goLogin({ page: 'detail', id: this.id }); },
  home() { wx.switchTab({ url: '/pages/home/index' }); }
});
