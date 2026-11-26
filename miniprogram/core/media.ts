import { LocalMedia } from './types';
import { BinaryPart } from './multipart';
import { validateMedia } from './validation';
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
export async function binaryParts(files: LocalMedia[]): Promise<BinaryPart[]> {
  const parts: BinaryPart[] = [];
  const issue = validateMedia(files);
  if (issue) throw new Error(issue.message);
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const bytes = await readFile(file.path);
    if (bytes.byteLength !== file.size) throw new Error(`第${i + 1}个媒体文件已变化，请重新选择`);
    parts.push({ field: file.kind === 'image' ? 'images' : 'video', name: file.name, mime: file.mime, bytes });
  }
  return parts;
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
