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
