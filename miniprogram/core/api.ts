import { auth } from './auth';
import { currentSource, goLogin, Source } from './source';
import { ApiError, RequestOptions, send } from './transport';

export interface ApiOptions extends RequestOptions { protected?: boolean; source?: Source; redirect?: boolean; isCurrent?: () => boolean }
export async function requireUser(source: Source, isCurrent: () => boolean): Promise<boolean> {
  const user = await auth.confirm();
  if (!isCurrent()) return false;
  if (!user) { goLogin(source); return false; }
  return true;
}
export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const token = options.protected ? auth.token() : undefined;
  if (options.protected && !token) {
    auth.clear(); if (options.redirect !== false && (options.isCurrent?.() ?? true)) goLogin(options.source || currentSource());
    throw new ApiError(401, 1002, '请登录后继续，登录后不会自动提交本次操作');
  }
  try { return await send<T>(path, { ...options, token }); }
  catch (error) {
    if (options.protected && error instanceof ApiError && error.status === 401) {
      if (token && auth.ownsToken(token)) { auth.clear(); if (options.redirect !== false && (options.isCurrent?.() ?? true)) goLogin(options.source || currentSource()); }
    }
    throw error;
  }
}
