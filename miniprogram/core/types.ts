export interface UserPublic { id: number; username: string; role: 'user' | 'admin' }
export interface AuthResult { user: UserPublic; token: string; expires_at: string }
export interface MediaPublic { id: number; kind: 'image' | 'video'; url: string; mime: string; size_bytes: number; position: number }
export interface MyWorkCard {
  id: number; title: string; summary: string; activity_date: string; created_at: string;
  status: 'visible' | 'removed'; media_kind: 'image' | 'video' | 'text' | null; cover_url: string | null;
}
export interface WorkCard extends MyWorkCard { user: Pick<UserPublic, 'id' | 'username'>; rating_avg: number | null; rating_count: number }
export interface WorkDetail extends WorkCard { content: string; tags: string[]; media: MediaPublic[] }
export interface CommentPublic { id: number; content: string; display_name: string; created_at: string }
export interface RatingStats { rating_avg: number | null; rating_count: number; my_score: number | null }
export interface PageResult<T> { list: T[]; total: number; page: number; page_size: number }
export interface Tag { id: number; name: string }
export interface LocalMedia { path: string; name: string; kind: 'image' | 'video'; mime: string; size: number }
export interface ValidationError { code: number; field: string; message: string }
export interface WorkForm { title: string; content: string; tags: string[]; activity_date: string; files: LocalMedia[]; existingMedia: MediaPublic[] }
export interface Envelope<T> { code: number; message: string; data: T }
export type InputEvent = WechatMiniprogram.CustomEvent<{ value: string }>;
export type TapEvent = WechatMiniprogram.CustomEvent<Record<string, never>, Record<string, never>, { id?: number; value?: string; index?: number; score?: number; field?: string }>;
