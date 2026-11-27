import { AUTH_STORAGE_KEY } from './config';
import { AuthResult, UserPublic } from './types';
import { ApiError, send } from './transport';

export interface AuthStorage { get(): unknown; set(value: AuthResult): void; remove(): void }
const CONFIRM_TTL = 60000;
export function validAuth(value: unknown): value is AuthResult {
  if (!value || typeof value !== 'object') return false;
  const record = value as Partial<AuthResult>;
  return typeof record.token === 'string' && record.token.length > 0 && typeof record.expires_at === 'string' && Number.isFinite(Date.parse(record.expires_at)) && !!record.user && Number.isSafeInteger(record.user.id) && record.user.id > 0 && typeof record.user.username === 'string' && record.user.role === 'user';
}
export class AuthManager {
  private record: AuthResult | null = null;
  private confirmed = false;
  private confirmedAt = 0;
  private generation = 0;
  private pending: Promise<UserPublic | null> | null = null;
  constructor(private storage: AuthStorage, private check: (token: string) => Promise<UserPublic>, private now: () => number = Date.now) {}
  user(): UserPublic | null { return this.confirmed && this.record && Date.parse(this.record.expires_at) > this.now() ? this.record.user : null; }
  token(): string | undefined { return this.user() ? this.record?.token : undefined; }
  ownsToken(token: string): boolean { return this.record?.token === token; }
  clear(): void { this.generation++; this.pending = null; this.record = null; this.confirmed = false; this.confirmedAt = 0; this.storage.remove(); }
  accept(value: AuthResult): void {
    if (!validAuth(value) || Date.parse(value.expires_at) <= this.now()) { this.clear(); throw new ApiError(403, 1003, '该账号不能在小程序登录'); }
    this.generation++; this.pending = null; this.record = value; this.confirmed = true; this.confirmedAt = this.now(); this.storage.set(value);
  }
  confirm(): Promise<UserPublic | null> {
    if (this.pending) return this.pending;
    const stored = this.record || this.storage.get();
    if (!validAuth(stored) || Date.parse(stored.expires_at) <= this.now()) { this.clear(); return Promise.resolve(null); }
    // A short confirmation window keeps every page show from spending a round trip on /me;
    // writes are still authorised server-side, so a revoked token fails on its first write.
    if (this.confirmed && this.record && this.record.token === stored.token && this.now() - this.confirmedAt < CONFIRM_TTL) {
      return Promise.resolve(this.record.user);
    }
    const generation = this.generation;
    this.record = stored;
    const pending = this.check(stored.token).then(user => {
      if (generation !== this.generation) return null;
      if (!validAuth({ ...stored, user }) || user.id !== stored.user.id || Date.parse(stored.expires_at) <= this.now()) { this.clear(); return null; }
      this.record = { ...stored, user }; this.confirmed = true; this.confirmedAt = this.now(); this.storage.set(this.record);
      return user;
    }).catch((error: unknown) => {
      if (generation !== this.generation) return null;
      if (error instanceof ApiError && [401, 403].includes(error.status)) { this.clear(); return null; }
      throw error;
    }).finally(() => { if (this.pending === pending) this.pending = null; });
    this.pending = pending;
    return pending;
  }
}
export const auth = new AuthManager({
  get: () => wx.getStorageSync(AUTH_STORAGE_KEY) as unknown,
  set: value => wx.setStorageSync(AUTH_STORAGE_KEY, value),
  remove: () => wx.removeStorageSync(AUTH_STORAGE_KEY)
}, token => send<UserPublic>('/api/auth/me', { token }));
