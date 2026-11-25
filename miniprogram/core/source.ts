export type Source = { page: 'home' | 'publish' | 'mine' | 'settings' } | { page: 'detail' | 'edit'; id: number };
export const HOME: Source = { page: 'home' };
export function workId(value: unknown): number | null {
  if (typeof value !== 'number' && (typeof value !== 'string' || !/^[1-9]\d*$/.test(value))) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}
export function parseSource(value: unknown): Source {
  if (typeof value !== 'string') return HOME;
  if (['home', 'publish', 'mine', 'settings'].includes(value)) return { page: value as 'home' | 'publish' | 'mine' | 'settings' };
  const match = /^(detail|edit):([1-9]\d*)$/.exec(value);
  const id = match ? workId(match[2]) : null;
  return match && id ? { page: match[1] as 'detail' | 'edit', id } : HOME;
}
export function encodeSource(source: Source): string { return 'id' in source ? `${source.page}:${source.id}` : source.page; }
export function sourceUrl(source: Source): string { return `/pages/${source.page}/index` + ('id' in source ? `?id=${source.id}` : ''); }
export const isTab = (source: Source): boolean => ['home', 'publish', 'mine'].includes(source.page);
export function currentSource(): Source {
  const pages = getCurrentPages();
  const page = pages[pages.length - 1];
  if (!page) return HOME;
  const name = page.route.split('/')[1];
  return parseSource(['detail', 'edit'].includes(name) ? `${name}:${page.options.id}` : name);
}
export function goLogin(source: Source): void {
  const pages = getCurrentPages();
  if (pages[pages.length - 1]?.route === 'pages/login/index') return;
  wx.navigateTo({ url: `/pages/login/index?from=${encodeURIComponent(encodeSource(source))}` });
}
export function returnTo(source: Source): void {
  const pages = getCurrentPages();
  const prior = pages[pages.length - 2];
  const route = sourceUrl(source).split('?')[0].slice(1);
  if (prior && prior.route === route && (!('id' in source) || workId(prior.options.id) === source.id)) { wx.navigateBack(); return; }
  if (isTab(source)) wx.switchTab({ url: sourceUrl(source) });
  else wx.redirectTo({ url: sourceUrl(source) });
}
