import { leaveTab } from '../core/leave';
Component({
  data: { selected: '', items: [{ page: 'home', label: '首页', symbol: '⌂' }, { page: 'publish', label: '发布', symbol: '+' }, { page: 'mine', label: '我的', symbol: '○' }] },
  lifetimes: { attached() { this.update(); } },
  pageLifetimes: { show() { this.update(); } },
  methods: {
    update() { const pages = getCurrentPages(); this.setData({ selected: pages[pages.length - 1]?.route.split('/')[1] || 'home' }); },
    choose(event: WechatMiniprogram.CustomEvent) {
      const page = event.currentTarget.dataset.page as string;
      const pages = getCurrentPages();
      const current = pages[pages.length - 1]?.route.split('/')[1];
      if (page !== current) void leaveTab(`/pages/${page}/index`);
    }
  }
});
