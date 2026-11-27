export type MediaField = 'images' | 'video' | 'file';
export interface BinaryPart { field: MediaField; name: string; mime: string; bytes: ArrayBuffer }
// Streaming parts are read one at a time straight into the final request buffer, so a
// nine-image upload never holds 90MiB twice.
export interface StreamPart { field: MediaField; name: string; mime: string; size: number; read: () => Promise<ArrayBuffer> }
export type UploadPart = BinaryPart | StreamPart;
export const FORM_FIELDS = ['title', 'content', 'activity_date', 'tags', 'media_keys', 'cover_key'];
export function utf8(value: string): Uint8Array {
  const bytes: number[] = [];
  for (const character of value) {
    let code = character.codePointAt(0) as number;
    if (code >= 0xd800 && code <= 0xdfff) code = 0xfffd;
    if (code < 0x80) bytes.push(code);
    else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 63));
    else if (code < 0x10000) bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
    else bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 63), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
  }
  return new Uint8Array(bytes);
}
export function safeFilename(name: string): string { return name.split(/[\\/]/).pop()?.replace(/[\r\n"\u0000-\u001f\u007f]/g, '_') || 'upload'; }
function contains(bytes: Uint8Array, target: Uint8Array): boolean {
  outer: for (let i = 0; i <= bytes.length - target.length; i++) {
    if (bytes[i] !== target[0]) continue;
    for (let j = 1; j < target.length; j++) if (bytes[i + j] !== target[j]) continue outer;
    return true;
  }
  return false;
}
function declaredSize(part: UploadPart): number { return 'bytes' in part ? part.bytes.byteLength : part.size; }
export async function buildMultipart(fields: Record<string, string>, files: UploadPart[], boundary: string): Promise<{ body: ArrayBuffer; contentType: string }> {
  if (!/^[A-Za-z0-9_-]{12,70}$/.test(boundary)) throw new Error('上传边界不合法');
  const marker = utf8('--' + boundary);
  const chunks: Uint8Array[] = [];
  for (const name of Object.keys(fields)) {
    if (!FORM_FIELDS.includes(name)) throw new Error('不支持的表单字段');
    const bytes = utf8(fields[name]);
    if (contains(bytes, marker)) throw new Error('上传边界冲突，请重试');
    chunks.push(utf8(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n`), bytes, utf8('\r\n'));
  }
  const headers: Uint8Array[] = [];
  let length = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    if (!['images', 'video', 'file'].includes(file.field) || !['image/jpeg', 'image/png', 'video/mp4'].includes(file.mime)) throw new Error('不支持的媒体类型');
    const size = declaredSize(file);
    if (!Number.isInteger(size) || size <= 0) throw new Error(`第${i + 1}个媒体文件已变化，请重新选择`);
    const header = utf8(`--${boundary}\r\nContent-Disposition: form-data; name="${file.field}"; filename="${safeFilename(file.name)}"\r\nContent-Type: ${file.mime}\r\n\r\n`);
    headers.push(header);
    length += header.byteLength + size + 2;
  }
  const close = utf8(`--${boundary}--\r\n`);
  length += close.byteLength;
  if (length > 100 * 1048576) throw new Error('上传请求不能超过100MB');
  const body = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    body.set(headers[i], offset); offset += headers[i].byteLength;
    const expected = declaredSize(file);
    const bytes = 'bytes' in file ? new Uint8Array(file.bytes) : new Uint8Array(await file.read());
    if (bytes.byteLength !== expected) throw new Error(`第${i + 1}个媒体文件已变化，请重新选择`);
    if (contains(bytes, marker)) throw new Error('上传边界冲突，请重试');
    body.set(bytes, offset); offset += bytes.byteLength;
    body.set(utf8('\r\n'), offset); offset += 2;
  }
  body.set(close, offset);
  return { body: body.buffer, contentType: `multipart/form-data; boundary=${boundary}` };
}
