import { getApiBaseUrl, REQUEST_TIMEOUT } from './config';
import { Envelope } from './types';

export class ApiError extends Error {
  constructor(public status: number, public code: number, message: string, public uncertain = false) { super(message); this.name = 'ApiError'; }
}
export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; data?: string | Record<string, unknown> | ArrayBuffer;
  token?: string; contentType?: string; timeout?: number;
}
export function send<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return new Promise((resolve, reject) => {
    const method = options.method || 'GET';
    const header: Record<string, string> = { 'Content-Type': options.contentType || 'application/json' };
    if (options.token) header.Authorization = `Bearer ${options.token}`;
    wx.request<Envelope<T>>({
      url: getApiBaseUrl() + path, method, data: options.data, header, timeout: options.timeout || REQUEST_TIMEOUT,
      success(response) {
        const body = response.data;
        if (body && body.code === 0 && response.statusCode >= 200 && response.statusCode < 300) resolve(body.data);
        else reject(new ApiError(response.statusCode, body?.code || 0, body?.message || '服务返回异常，请稍后重试'));
      },
      fail() { reject(new ApiError(0, 0, method === 'GET' ? '网络连接失败或请求超时，请检查网络后重试' : '请求未获确认，结果未知。请先查询最新状态，再决定是否重试', method !== 'GET')); }
    });
  });
}
export const errorMessage = (value: unknown): string => value instanceof Error ? value.message : '操作失败，请稍后重试';
export const unavailableCode = (value: unknown): number => value instanceof ApiError && [1004, 1010].includes(value.code) ? value.code : 0;
