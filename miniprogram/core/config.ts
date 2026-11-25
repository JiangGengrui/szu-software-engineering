export const API_BASE_URL = 'http://127.0.0.1:5000';
export const API_BASE_URL_STORAGE_KEY = 'campus_album_api_base_url';
export const REQUEST_TIMEOUT = 15000;
export const UPLOAD_TIMEOUT = 60000;
export const AUTH_STORAGE_KEY = 'campus_album_auth';

export function normalizeApiBaseUrl(value: unknown): string {
  if (typeof value !== 'string') return '';
  const trimmed = value.trim().replace(/\/+$/, '');
  return /^https?:\/\/[^/\s?#@]+$/i.test(trimmed) ? trimmed : '';
}

export function getApiBaseUrl(): string {
  if (typeof wx !== 'undefined' && typeof wx.getStorageSync === 'function') {
    try {
      const override = normalizeApiBaseUrl(wx.getStorageSync(API_BASE_URL_STORAGE_KEY));
      if (override) return override;
    } catch {
      return API_BASE_URL;
    }
  }
  return API_BASE_URL;
}
