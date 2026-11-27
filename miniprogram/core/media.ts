import { api } from './api';
import { UPLOAD_TIMEOUT } from './config';
import { LocalMedia } from './types';
import { buildMultipart, StreamPart } from './multipart';
import { validateMedia } from './validation';
export const COVER_LIMIT = 512 * 1024;
export interface UploadedMedia { key: string; kind: 'image' | 'video'; mime: string; size_bytes: number }
export function readFile(path: string): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => wx.getFileSystemManager().readFile({
    filePath: path, success(result) { typeof result.data === 'string' ? reject(new Error('无法读取媒体字节，请重新选择')) : resolve(result.data); },
    fail() { reject(new Error('读取媒体失败，本地文件可能已失效，请重新选择')); }
  }));
}
export function chooseMedia(kind: 'image' | 'video'): Promise<LocalMedia[] | null> {
  return new Promise((resolve, reject) => wx.chooseMedia({
    count: kind === 'image' ? 9 : 1, mediaType: [kind], sourceType: ['album', 'camera'], sizeType: ['original'],
    success: async result => {
      try {
        const files: LocalMedia[] = [];
        for (let i = 0; i < result.tempFiles.length; i++) {
          const file = result.tempFiles[i];
          let extension = file.tempFilePath.split('.').pop()?.toLowerCase() || '';
          if (kind === 'image') extension = await new Promise<string>((yes, no) => wx.getImageInfo({ src: file.tempFilePath, success: image => yes(image.type === 'jpeg' ? 'jpg' : image.type.toLowerCase()), fail: () => no(new Error(`第${i + 1}张图片无法读取`)) }));
          const mime = kind === 'video' ? 'video/mp4' : extension === 'png' ? 'image/png' : 'image/jpeg';
          files.push({ path: file.tempFilePath, name: `${kind}-${i + 1}.${extension}`, kind, size: file.size, mime });
        }
        const issue = validateMedia(files);
        if (issue) throw new Error(issue.message);
        resolve(files);
      } catch (error) { reject(error); }
    },
    fail: error => /cancel/.test(error.errMsg) ? resolve(null) : reject(new Error('无法选择媒体，请检查微信相册/相机权限后重试'))
  }));
}
// Lazy readers let the multipart builder fill one request buffer file by file, so the
// page never keeps every original image in memory at the same time.
export function fileParts(files: LocalMedia[]): StreamPart[] {
  const issue = validateMedia(files);
  if (issue) throw new Error(issue.message);
  return files.map(file => ({
    field: file.kind === 'image' ? 'images' as const : 'video' as const,
    name: file.name, mime: file.mime, size: file.size,
    read: () => readFile(file.path)
  }));
}

function compress(src: string, quality: number, width?: number): Promise<string | null> {
  return new Promise(resolve => {
    try {
      wx.compressImage({
        src, quality, compressedWidth: width,
        success: result => resolve(result.tempFilePath),
        fail: () => resolve(null)
      });
    } catch { resolve(null); }
  });
}

function fileSize(path: string): Promise<number> {
  return new Promise(resolve => {
    try {
      wx.getFileSystemManager().getFileInfo({
        filePath: path,
        success: info => resolve(info.size),
        fail: () => resolve(0)
      });
    } catch { resolve(0); }
  });
}

// The server never decodes images, so the list thumbnail is produced here. A cover is
// optional: when compression is unsupported or still too large the list falls back to
// the first saved image.
export async function makeCover(file: LocalMedia): Promise<LocalMedia | null> {
  if (file.kind !== 'image' || file.size <= COVER_LIMIT) return null;
  const path = await compress(file.path, 60, 720) || await compress(file.path, 40);
  if (!path) return null;
  const suffix = (path.split('?')[0].split('.').pop() || '').toLowerCase();
  const png = suffix === 'png';
  if (!png && !/^jpe?g$/.test(suffix)) return null;
  const size = await fileSize(path);
  if (!(size > 0 && size <= COVER_LIMIT)) return null;
  return { path, name: `cover-${Date.now()}.${png ? 'png' : 'jpg'}`, kind: 'image', mime: png ? 'image/png' : 'image/jpeg', size };
}

// One request per file keeps peak memory at a single media item and lets the caller
// retry only the file that failed.
export async function uploadMedia(file: LocalMedia): Promise<string> {
  const boundary = `CampusAlbum_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const part: StreamPart = {
    field: 'file', name: file.name, mime: file.mime, size: file.size,
    read: () => readFile(file.path)
  };
  const multipart = await buildMultipart({}, [part], boundary);
  const result = await api<UploadedMedia>('/api/uploads', {
    method: 'POST', protected: true, data: multipart.body, contentType: multipart.contentType, timeout: UPLOAD_TIMEOUT
  });
  return result.key;
}

// 真机上 <image> 对局域网 HTTP 资源可能直接失败；用已确认可用的 wx.request
// 取回字节并落到本地临时文件，再交给 image/video 组件显示。
export function cacheRemoteMedia(url: string, mime = ''): Promise<string> {
  if (!/^https?:\/\//i.test(url)) return Promise.resolve(url);
  return new Promise((resolve, reject) => {
    wx.request({
      url, method: 'GET', responseType: 'arraybuffer', timeout: 60000,
      success(result) {
        const data = result.data;
        if (result.statusCode < 200 || result.statusCode >= 300 || !(data instanceof ArrayBuffer)) {
          reject(new Error('媒体读取失败')); return;
        }
        const fromUrl = (url.split('?')[0].split('.').pop() || '').toLowerCase();
        const type = mime.toLowerCase();
        const suffix = /^(jpe?g|png|gif|webp|mp4|mov)$/.test(fromUrl) ? fromUrl
          : type.includes('png') ? 'png'
            : type.includes('webp') ? 'webp'
              : type.includes('gif') ? 'gif'
                : type.includes('mp4') ? 'mp4'
                  : type.includes('quicktime') ? 'mov' : 'jpg';
        const filePath = `${wx.env.USER_DATA_PATH}/remote-${Date.now()}-${Math.random().toString(16).slice(2)}.${suffix}`;
        wx.getFileSystemManager().writeFile({
          filePath, data,
          success() { resolve(filePath); },
          fail() { reject(new Error('媒体缓存失败')); }
        });
      },
      fail() { reject(new Error('媒体下载失败')); }
    });
  });
}
