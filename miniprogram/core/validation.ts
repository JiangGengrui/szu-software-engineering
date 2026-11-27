import { LocalMedia, ValidationError, WorkForm } from './types';

export const IMAGE_LIMIT = 10 * 1048576;
export const VIDEO_LIMIT = 50 * 1048576;
export const codePoints = (value: string): number => Array.from(value).length;
export const trimText = (value: string): string => value.replace(/^[\t-\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t-\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu, '');
// Invisible or control code points and folded whitespace are removed before the tag is compared,
// so two tags that look identical on screen cannot be stored as different names.
export const cleanTag = (value: string): string => trimText(value
  .replace(/[\u0000-\u0008\u000e-\u001f\u007f-\u009f\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]/gu, '')
  .replace(/[\t-\r\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/gu, ' '));
export const normalizeTags = (tags: string[]): string[] => Array.from(new Set(tags.map(cleanTag)));
export function beijingToday(now = Date.now()): string { return new Date(now + 8 * 3600000).toISOString().slice(0, 10); }
export function validDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.slice(0, 4) === '0000') return false;
  const date = new Date(value + 'T00:00:00Z');
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
function error(code: number, field: string, message: string): ValidationError { return { code, field, message }; }
export function validateUsername(value: string): ValidationError | null {
  return codePoints(value) >= 3 && codePoints(value) <= 20 && /^[A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff\u{20000}-\u{2fa1f}]+$/u.test(value) ? null : error(1001, 'username', '用户名须为3—20字，仅含中英文、数字或下划线');
}
export function validatePassword(value: string): ValidationError | null {
  return codePoints(value) >= 8 && codePoints(value) <= 20 && /[A-Za-z]/.test(value) && /[0-9]/.test(value) ? null : error(1001, 'password', '密码须为8—20位，且同时包含字母和数字');
}
export function validateCredentials(username: string, password: string, confirmation?: string): ValidationError | null {
  if (confirmation === undefined) return username && password ? null : error(1001, !username ? 'username' : 'password', '请填写用户名和密码');
  return validateUsername(username) || validatePassword(password) || (password !== confirmation ? error(1001, 'confirmation', '两次密码输入不一致') : null);
}
export function validatePasswordChange(oldPassword: string, newPassword: string, confirmation: string): ValidationError | null {
  if (!oldPassword) return error(1001, 'old_password', '请填写原密码');
  const issue = validatePassword(newPassword);
  if (issue) return { ...issue, field: 'new_password' };
  if (oldPassword === newPassword) return error(1001, 'new_password', '新密码不能与原密码相同');
  return newPassword === confirmation ? null : error(1001, 'confirmation', '两次新密码输入不一致');
}
export function validateTags(tags: string[], query = false): ValidationError | null {
  const normalized = normalizeTags(tags);
  return ((!query && normalized.length > 5) || normalized.some(tag => codePoints(tag) < 1 || codePoints(tag) > 10)) ? error(query ? 1001 : 1013, 'tags', query ? '标签名称须为1—10字' : '标签去重后最多5个，每个1—10字') : null;
}
export function validateMedia(files: LocalMedia[]): ValidationError | null {
  const images = files.filter(file => file.kind === 'image');
  const videos = files.filter(file => file.kind === 'video');
  if (images.length && videos.length) return error(1014, 'files', '图片与视频不能混合，请选择一种媒体');
  if (images.length > 9) return error(1015, 'files', '图片最多9张');
  for (let i = 0; i < images.length; i++) {
    const file = images[i];
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!Number.isInteger(file.size) || file.size <= 0 || file.size > IMAGE_LIMIT || !['jpg', 'jpeg', 'png'].includes(ext || '') || file.mime !== (ext === 'png' ? 'image/png' : 'image/jpeg')) return error(1015, 'files', `第${i + 1}张图片不合法：仅支持JPG/JPEG/PNG，每张大于0且不超过10MB`);
  }
  if (videos.length > 1) return error(1015, 'files', '视频只能选择1个');
  if (videos.some(file => !Number.isInteger(file.size) || file.size <= 0 || file.size > VIDEO_LIMIT || !/\.mp4$/i.test(file.name) || file.mime !== 'video/mp4')) return error(1015, 'files', '视频不合法：仅支持MP4，大于0且不超过50MB');
  return null;
}
export function validateWork(form: WorkForm, today = beijingToday()): ValidationError | null {
  if (codePoints(form.title) > 50) return error(1001, 'title', '标题最多50字');
  if (codePoints(trimText(form.content)) > 2000) return error(1012, 'content', '正文最多2000字');
  if (!validDate(form.activity_date) || form.activity_date > today) return error(1001, 'activity_date', '活动日期须为合法日期，且不晚于北京时间今天');
  const tagError = validateTags(form.tags);
  if (tagError) return tagError;
  const effective = form.files.length ? form.files : form.existingMedia.map(file => ({ path: file.url, name: file.kind === 'video' ? 'kept.mp4' : file.mime === 'image/png' ? 'kept.png' : 'kept.jpg', kind: file.kind, mime: file.mime, size: file.size_bytes }));
  if (!trimText(form.content) && !effective.length) return error(1011, 'content', '请填写正文或选择图片/视频，仅标题不能发布');
  return validateMedia(effective);
}
export function validateComment(value: string): ValidationError | null {
  const count = codePoints(trimText(value));
  return count >= 1 && count <= 500 ? null : error(1001, 'comment', '评论须为1—500字，不能只有空白');
}
export function validateScore(score: unknown, own: boolean): ValidationError | null {
  if (typeof score !== 'number' || !Number.isInteger(score) || score < 1 || score > 5) return error(1001, 'score', '请选择1—5的整数评分');
  return own ? error(1009, 'score', '不能给自己的作品评分') : null;
}
