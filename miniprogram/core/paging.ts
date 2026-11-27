import { PageResult } from './types';
export interface Ticket { generation: number; page: number; replace?: boolean }
export class Pager<T extends { id: number }> {
  list: T[] = [];
  total = 0;
  next = 1;
  done = false;
  loading = false;
  error = '';
  private generation = 0;
  constructor(readonly pageSize: number) {}
  reset(): void { this.generation++; this.list = []; this.total = 0; this.next = 1; this.done = false; this.loading = false; this.error = ''; }
  begin(): Ticket | null {
    if (this.loading || this.done) return null;
    this.loading = true; this.error = '';
    return { generation: this.generation, page: this.next };
  }
  // Re-reads page one while the visible list stays on screen, so returning to a tab does
  // not flash skeletons or jump the scroll position.
  reload(): Ticket | null {
    if (this.loading) return null;
    this.loading = true; this.error = '';
    return { generation: this.generation, page: 1, replace: true };
  }
  current(ticket: Ticket): boolean {
    return ticket.generation === this.generation && this.loading && (ticket.replace ? ticket.page === 1 : ticket.page === this.next);
  }
  resolve(ticket: Ticket, result: PageResult<T>): boolean {
    if (!this.current(ticket)) return false;
    if (result.page !== ticket.page || result.page_size !== this.pageSize) { this.reject(ticket, '分页响应异常，请重试'); return false; }
    if (ticket.replace) this.list = result.list.slice();
    else {
      const known = new Set(this.list.map(item => item.id));
      this.list = this.list.concat(result.list.filter(item => { if (known.has(item.id)) return false; known.add(item.id); return true; }));
    }
    this.total = result.total;
    this.next = ticket.replace ? 2 : this.next + 1;
    this.loading = false;
    this.done = result.list.length < this.pageSize || ticket.page * this.pageSize >= result.total;
    return true;
  }
  reject(ticket: Ticket, message: string): boolean { if (!this.current(ticket)) return false; this.loading = false; this.error = message; return true; }
}
export function listQuery(date: string, tags: string[], page: number, pageSize = 10): string {
  return `page=${page}&page_size=${pageSize}` + (date ? `&date=${encodeURIComponent(date)}` : '') + Array.from(new Set(tags)).map(tag => `&tag=${encodeURIComponent(tag)}`).join('');
}
