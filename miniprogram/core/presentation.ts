import { API_BASE_URL } from './config';
import { MyWorkCard, WorkCard, WorkDetail } from './types';
export function mediaUrl(value: string | null | undefined): string {
  if (!value) return '';
  if (/^\/media\/[1-9]\d*$/.test(value)) return API_BASE_URL + value;
  return /^https?:\/\/[^\s]+$/i.test(value) ? value : '';
}
export function ratingText(avg: number | null, count: number): string { return count > 0 && avg !== null && Number.isFinite(avg) ? `${avg.toFixed(1)}分 · ${count}人` : '暂无评分'; }
export function myCard<T extends MyWorkCard>(value: T): T & { cover: string; label: string; stateText: string } {
  return { ...value, cover: value.status === 'removed' ? '' : mediaUrl(value.cover_url), label: value.title || value.summary || (value.media_kind === 'video' ? '视频作品' : value.media_kind === 'image' ? '图片作品' : '文字作品'), stateText: value.status === 'removed' ? '已移除' : '公开可见' };
}
export function publicCard(value: WorkCard) { return { ...myCard(value), ratingText: ratingText(value.rating_avg, value.rating_count) }; }
export function detailView(value: WorkDetail): WorkDetail { return { ...value, media: value.media.slice().sort((a, b) => a.position - b.position).map(media => ({ ...media, url: mediaUrl(media.url) })) }; }
export function unavailableState(code: number) {
  return { work: null, comments: [], ratingText: '', myScore: null, score: 0, comment: '', mediaError: '', commentError: '', commentsError: '', ratingError: '', loading: false, commentsLoading: false, commentsDone: true, loggedIn: false, unavailable: code === 1004 ? '作品不存在' : '作品已移除，无法查看' };
}
export function displayTime(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() + 8 * 3600000).toISOString().slice(0, 16).replace('T', ' ') + '（北京时间）'; }
