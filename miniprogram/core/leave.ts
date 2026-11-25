let guard: (() => Promise<boolean>) | null = null;
export function setLeaveGuard(value: (() => Promise<boolean>) | null): void { guard = value; }
export type TabName = 'home' | 'publish' | 'mine';
interface TabBarInstance { setData(data: { selected: TabName }): void }
export function selectTab(page: unknown, selected: TabName): void {
  // Custom tab bar instances do not reliably receive pageLifetimes.show on a tab switch.
  const getTabBar = (page as { getTabBar?: () => TabBarInstance | null }).getTabBar;
  if (typeof getTabBar === 'function') getTabBar.call(page)?.setData({ selected });
}
let leaving = false;
export async function leaveTab(url: string): Promise<void> {
  if (leaving || !/^\/pages\/(home|publish|mine)\/index$/.test(url)) return;
  leaving = true;
  try { if (!guard || await guard()) wx.switchTab({ url }); }
  finally { leaving = false; }
}
export function confirmDiscard(): Promise<boolean> { return new Promise(resolve => wx.showModal({ title: '放弃未提交的修改？', content: '离开后本次未提交内容将丢失，不会保存为草稿。', confirmText: '放弃修改', confirmColor: '#B42318', cancelText: '继续编辑', success: result => resolve(result.confirm), fail: () => resolve(false) })); }
