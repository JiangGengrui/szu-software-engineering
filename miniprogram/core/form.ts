import { LocalMedia, WorkDetail, WorkForm } from './types';
import { beijingToday, normalizeTags, trimText } from './validation';
export function emptyForm(): WorkForm { return { title: '', content: '', tags: [], activity_date: beijingToday(), files: [], existingMedia: [] }; }
export function formFromWork(work: WorkDetail): WorkForm { return { title: work.title, content: work.content, tags: [...work.tags], activity_date: work.activity_date, files: [], existingMedia: [...work.media] }; }
export function formFields(form: WorkForm): Record<string, string> { return { title: form.title, content: trimText(form.content), activity_date: form.activity_date, tags: JSON.stringify(normalizeTags(form.tags)) }; }
export function replaceSelection(form: WorkForm, files: LocalMedia[]): WorkForm { return { ...form, files: files.slice() }; }
export function failSubmission(form: WorkForm, message: string) { return { form, busy: false, progress: '失败', error: message }; }
export function effectiveMedia(form: WorkForm): { url: string; kind: 'image' | 'video' }[] { return form.files.length ? form.files.map(file => ({ url: file.path, kind: file.kind })) : form.existingMedia.map(file => ({ url: file.url, kind: file.kind })); }
