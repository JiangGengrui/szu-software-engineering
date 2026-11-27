import { api } from './api';
import { auth } from './auth';
import { UPLOAD_TIMEOUT } from './config';
import { effectiveMedia, emptyForm, failSubmission, formFields, formFromWork, replaceSelection } from './form';
import { confirmDiscard, selectTab, setLeaveGuard } from './leave';
import { chooseMedia, makeCover, uploadMedia } from './media';
import { buildMultipart } from './multipart';
import { detailView, myCard } from './presentation';
import { goLogin, Source, workId } from './source';
import { ApiError, errorMessage, unavailableCode } from './transport';
import { InputEvent, MyWorkCard, PageResult, TapEvent, WorkDetail, WorkForm } from './types';
import { beijingToday, codePoints, normalizeTags, trimText, validateTags, validateWork } from './validation';

interface EditorData {
  editing: boolean; form: WorkForm; tagInput: string; count: number; titleCount: number; today: string;
  previews: { url: string; kind: 'image' | 'video' }[]; loading: boolean; ready: boolean; blocked: string; error: string;
  field: string; busy: boolean; progress: string; dirty: boolean; uncertain: boolean; mediaError: string;
  latest: ReturnType<typeof myCard<MyWorkCard>>[]; checking: boolean; latestChecked: boolean;
}
interface EditorMethods {
  id: number; loaded: boolean; prompted: boolean; generation: number; baseline: string;
  source(): Source; enter(): Promise<void>; syncForm(form: WorkForm): void; markDirty(): void; reset(): void;
  input(event: InputEvent): void; tagInputChange(event: InputEvent): void; addTag(): boolean; removeTag(event: TapEvent): void;
  dateChange(event: InputEvent): void; pickImages(): void; pickVideo(): void; pick(kind: 'image' | 'video'): Promise<void>;
  cancelSelection(): void; preview(event: TapEvent): void; mediaFailed(): void; submit(): Promise<void>;
  login(): void; checkResult(): Promise<void>; checkStatus(): Promise<void>; openResult(event: TapEvent): void;
}
export function createEditorPage(editing: boolean): WechatMiniprogram.Page.Options<EditorData, EditorMethods> {
  return {
    data: { editing, form: emptyForm(), tagInput: '', count: 0, titleCount: 0, today: beijingToday(), previews: [], loading: true, ready: false, blocked: '', error: '', field: '', busy: false, progress: '', dirty: false, uncertain: false, mediaError: '', latest: [], checking: false, latestChecked: false },
    id: 0, loaded: false, prompted: false, generation: 0, baseline: '',
    onLoad(options) { this.id = editing ? workId(options.id) || 0 : 0; this.baseline = JSON.stringify(this.data.form); },
    onShow() {
      if (!editing) selectTab(this, 'publish');
      if (!editing) setLeaveGuard(async () => {
        if (this.data.busy) { wx.showToast({ title: '请求处理中，请等待结果', icon: 'none' }); return false; }
        if (!this.data.dirty) return true;
        if (!await confirmDiscard()) return false;
        this.reset(); return true;
      });
      void this.enter();
    },
    onHide() { if (!editing) setLeaveGuard(null); },
    onUnload() { this.generation++; if (!editing) setLeaveGuard(null); },
    source() { return editing && this.id ? { page: 'edit', id: this.id } : { page: 'publish' }; },
    async enter() {
      const generation = ++this.generation;
      this.setData({ loading: true, today: beijingToday(), ready: false, blocked: '' });
      try {
        const user = await auth.confirm(); if (generation !== this.generation) return;
        if (!user) { if (!this.prompted) { this.prompted = true; goLogin(this.source()); } return; }
        if (editing) {
          if (!this.id) { this.setData({ blocked: '作品不存在' }); return; }
          const work = await api<WorkDetail>(`/api/works/${this.id}`); if (generation !== this.generation) return;
          if (work.user.id !== user.id) { this.setData({ blocked: '无权限：只能编辑自己的作品' }); return; }
          if (!this.loaded) { const form = formFromWork(detailView(work)); this.baseline = JSON.stringify(form); this.syncForm(form); this.loaded = true; }
        }
        this.setData({ ready: true });
        if (this.data.dirty) wx.enableAlertBeforeUnload({ message: '未提交的修改将丢失，确定离开？' });
      } catch (error) {
        if (generation !== this.generation) return;
        const code = unavailableCode(error);
        if (code) this.setData({ blocked: code === 1004 ? '作品不存在' : '作品已移除，不能编辑', previews: [] });
        else if (error instanceof ApiError && error.status === 403) this.setData({ blocked: errorMessage(error), previews: [] });
        else this.setData({ error: errorMessage(error) });
      } finally { if (generation === this.generation) this.setData({ loading: false }); }
    },
    syncForm(form) { this.setData({ form, previews: effectiveMedia(form), count: codePoints(trimText(form.content)), titleCount: codePoints(form.title) }); },
    markDirty() {
      const dirty = JSON.stringify(this.data.form) !== this.baseline || !!this.data.tagInput;
      this.setData({ dirty, error: '', field: '' });
      if (dirty) wx.enableAlertBeforeUnload({ message: '未提交的修改将丢失，确定离开？' }); else wx.disableAlertBeforeUnload();
    },
    reset() { const form = emptyForm(); this.baseline = JSON.stringify(form); this.syncForm(form); this.setData({ dirty: false, tagInput: '', error: '', field: '', progress: '', uncertain: false, latest: [], latestChecked: false, mediaError: '' }); wx.disableAlertBeforeUnload(); },
    input(event) { if (this.data.busy) return; const field = event.currentTarget.dataset.field as 'title' | 'content'; if (!['title', 'content'].includes(field)) return; this.syncForm({ ...this.data.form, [field]: event.detail.value }); this.markDirty(); },
    tagInputChange(event) { if (this.data.busy) return; this.setData({ tagInput: event.detail.value }); this.markDirty(); },
    addTag() {
      if (this.data.busy) return false;
      const tags = normalizeTags([...this.data.form.tags, this.data.tagInput]); const issue = validateTags(tags);
      if (issue) { this.setData({ error: issue.message, field: 'tags' }); return false; }
      this.syncForm({ ...this.data.form, tags }); this.setData({ tagInput: '' }); this.markDirty(); return true;
    },
    removeTag(event) { if (this.data.busy) return; this.syncForm({ ...this.data.form, tags: this.data.form.tags.filter((_, index) => index !== Number(event.currentTarget.dataset.index)) }); this.markDirty(); },
    dateChange(event) { if (this.data.busy) return; this.syncForm({ ...this.data.form, activity_date: event.detail.value }); this.markDirty(); },
    pickImages() { void this.pick('image'); }, pickVideo() { void this.pick('video'); },
    async pick(kind) {
      if (this.data.busy) return;
      this.setData({ busy: true, error: '', progress: '选择媒体' });
      try { const files = await chooseMedia(kind); if (files) { this.syncForm(replaceSelection(this.data.form, files)); this.markDirty(); this.setData({ mediaError: '' }); } }
      catch (error) { this.setData({ error: errorMessage(error), field: 'files' }); }
      finally { this.setData({ busy: false, progress: '' }); }
    },
    cancelSelection() { if (this.data.busy) return; this.syncForm(replaceSelection(this.data.form, [])); this.markDirty(); },
    preview(event) { const urls = this.data.previews.filter(file => file.kind === 'image').map(file => file.url); if (urls.length) wx.previewImage({ current: event.currentTarget.dataset.value || urls[0], urls }); },
    mediaFailed() { this.setData({ mediaError: '预览加载失败。新文件可重新选择；已保存媒体可刷新状态核对。' }); },
    async submit() {
      if (this.data.busy || !this.data.ready) return;
      if (trimText(this.data.tagInput) && !this.addTag()) return;
      const issue = validateWork(this.data.form); if (issue) { this.setData({ error: issue.message, field: issue.field }); return; }
      this.setData({ busy: true, error: '', field: '', progress: '确认登录状态', uncertain: false });
      try {
        const user = await auth.confirm(); if (!user) { this.setData({ progress: '失败', ready: false }); goLogin(this.source()); return; }
        const files = this.data.form.files;
        const fields = formFields(this.data.form);
        if (files.length) {
          const keys: string[] = [];
          for (let index = 0; index < files.length; index++) {
            this.setData({ progress: `上传媒体 ${index + 1}/${files.length}` });
            keys.push(await uploadMedia(files[index]));
          }
          fields.media_keys = JSON.stringify(keys);
          this.setData({ progress: '生成封面' });
          const cover = await makeCover(files[0]);
          if (cover) {
            this.setData({ progress: '上传封面' });
            // A missing thumbnail only falls back to the first saved image; it must not block publishing.
            let coverKey = '';
            try { coverKey = await uploadMedia(cover); } catch { coverKey = ''; }
            if (coverKey) fields.cover_key = coverKey;
          }
        }
        const boundary = `CampusAlbum_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        this.setData({ progress: '提交中，请勿重复提交' });
        const multipart = await buildMultipart(fields, [], boundary);
        this.setData({ progress: '上传中，请勿重复提交' });
        const work = await api<WorkDetail>(editing ? `/api/works/${this.id}` : '/api/works', { method: editing ? 'PUT' : 'POST', protected: true, source: this.source(), data: multipart.body, contentType: multipart.contentType, timeout: UPLOAD_TIMEOUT });
        this.setData({ progress: '完成', dirty: false }); wx.disableAlertBeforeUnload();
        if (editing) wx.redirectTo({ url: `/pages/detail/index?id=${work.id}` });
        else { this.reset(); this.setData({ progress: '完成' }); wx.navigateTo({ url: `/pages/detail/index?id=${work.id}` }); }
      } catch (error) {
        const failure = failSubmission(this.data.form, errorMessage(error));
        const fields: Record<number, string> = { 1011: 'content', 1012: 'content', 1013: 'tags', 1014: 'files', 1015: 'files', 1016: 'files' };
        this.setData({ ...failure, field: error instanceof ApiError ? fields[error.code] || '' : '', uncertain: error instanceof ApiError && error.uncertain });
        if (error instanceof ApiError && error.status === 401) this.setData({ ready: false });
        if (error instanceof ApiError && error.status === 403) this.setData({ blocked: errorMessage(error), ready: false, previews: [] });
        if (editing && error instanceof ApiError && (error.status === 409 || unavailableCode(error))) await this.checkStatus();
      } finally { this.setData({ busy: false }); }
    },
    login() { goLogin(this.source()); },
    async checkStatus() {
      if (!editing) return;
      try { const work = await api<WorkDetail>(`/api/works/${this.id}`); if (work.user.id !== auth.user()?.id) this.setData({ blocked: '无权限：只能编辑自己的作品', ready: false, previews: [] }); }
      catch (error) { const code = unavailableCode(error); if (code) this.setData({ blocked: code === 1004 ? '作品不存在' : '作品已移除，不能编辑', ready: false, previews: [] }); else this.setData({ error: errorMessage(error) }); }
    },
    async checkResult() {
      if (this.data.checking) return;
      this.setData({ checking: true });
      try { const result = await api<PageResult<MyWorkCard>>('/api/works/mine?page=1&page_size=10', { protected: true, source: this.source() }); this.setData({ latest: result.list.map(myCard), latestChecked: true }); if (editing) await this.checkStatus(); }
      catch (error) { this.setData({ error: errorMessage(error) }); }
      finally { this.setData({ checking: false }); }
    },
    openResult(event) { wx.navigateTo({ url: `/pages/detail/index?id=${event.currentTarget.dataset.id}` }); }
  };
}
