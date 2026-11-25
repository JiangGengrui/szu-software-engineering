# 校园影集

校园影集是一个面向校园活动作品的发布、检索、互动与管理平台，由**原生微信小程序**、**Flask 管理后台**和**共享后端**组成。小程序不是 H5 替代版。

## 项目状态

- 当前阶段：**S6 验收**。
- 需求、原型、架构和实施计划已分别通过 G1—G4；清理前最近一次 Gm 机器检查已通过，清理后已重跑小程序构建、类型检查、Lint 与后端 369 项测试。
- 最终 G5 验收尚未通过。验收记录为 **108/157 通过、0 失败、49 未验证**，剩余项依赖微信真机、20 个原生渲染客户端性能、课堂演示和独立 G5。
- 本仓库只发布项目本体与实现过程文档；测试、验收证据和本地工具包不进入版本库。

## 功能概览

### 微信小程序

- 首页作品流、标签筛选、关键词检索和分页加载。
- 作品发布、编辑、删除，支持图片与视频上传。
- 作品详情、评论、评分和互动状态。
- 我的作品、登录状态恢复和未登录引导。
- 自定义 TabBar 在首页、发布、我的之间保持正确高亮。

### 管理后台

- 管理员登录、会话过期和按账号锁定。
- 作品检索、查看、移除和状态管理。
- 用户列表、禁用与恢复。
- CSRF 防护、输入转义和危险操作确认。

### 后端

- Flask 应用工厂、Blueprint、Service 与 SQLAlchemy 分层。
- SQLite 持久化、媒体文件受控存储与状态校验。
- 小程序 JSON API 与管理后台 Jinja2 页面共用同一套业务服务。
- 统一错误壳、请求 ID、日志脱敏和上传补偿。

## 技术栈

| 层 | 技术 |
|---|---|
| 小程序 | 原生 TypeScript / WXML / WXSS / JSON，`tsc` 生成 CommonJS JS |
| 后端 | Python 3.12、Flask、SQLAlchemy 2、SQLite |
| 后台页面 | Jinja2、HTML、CSS |
| 测试与质量 | pytest、Ruff、mypy、ESLint、Node `node:test`（本地保留） |

## 目录结构

```text
campus-album/
├─ backend/album/          # Flask 应用、六模块、模型、Jinja2 模板与静态资源
├─ miniprogram/            # 原生微信小程序源码
├─ docs/                   # 课程原始资料与架构图
├─ SPEC.md                 # 需求与 157 条验收标准
├─ DECISIONS.md            # 已确认决策与边界
├─ ARCHITECTURE.md         # 架构设计
├─ PLAN.md                 # 实施计划与任务状态
├─ CHANGELOG.md            # 变更与影响记录
├─ AGENTS.md               # 工程规则与协作协议
├─ story.md                # S1—S7 实施步骤
├─ package.json            # 小程序构建与前端质量命令
├─ pyproject.toml          # Python 工具配置
├─ requirements.lock.txt   # Python 锁定依赖
└─ tsconfig.json           # 小程序 TypeScript 配置
```

## 快速开始

### 1. 环境

- Python 3.12
- Node.js 22 与 npm 10
- 微信开发者工具（仅用于原生小程序调试）

### 2. 安装依赖

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm install
```

### 3. 初始化演示数据并启动后端

首次初始化需要设置管理员和演示普通用户的密码。密码只通过环境变量传入，不写入源码。

```powershell
$env:PYTHONPATH = "backend"
$env:SEED_ADMIN_PASSWORD = "请设置管理员密码"
$env:SEED_USER_PASSWORD = "请设置普通用户密码"
.venv\Scripts\python.exe -m flask --app album:create_app init-demo
.venv\Scripts\python.exe -m flask --app album:create_app run --host 127.0.0.1 --port 5000 --no-reload --no-debugger
```

后台入口：<http://127.0.0.1:5000/admin/login>

初始化会在 `instance/` 写入数据库、密钥和媒体文件，不覆盖已有实例。重复初始化不会重置既有密码或作品；如种子用户名已被不同角色占用，初始化会拒绝而不是覆盖。

### 4. 构建并导入小程序

```powershell
npm run build:mini
```

在微信开发者工具中导入 `miniprogram/` 目录并填写 AppID。开发环境 API 地址位于 `miniprogram/core/config.ts`，默认是 `http://127.0.0.1:5000`。

真机调试时：

- 将 API 地址改为运行 Flask 的电脑局域网 IP；
- 让 Flask 使用 `--host 0.0.0.0`；
- 手机与电脑处于同一可信局域网；
- 共享 `project.config.json` 保持域名校验开启，仅本机 private 配置可临时关闭校验。

本期不声明体验版或正式版可用，也不将模拟器、接口测试或截图替代原生真机验收。

## 文档导航

| 文档 | 内容 |
|---|---|
| [SPEC.md](SPEC.md) | 已通过 G1 的需求基线、31 条需求和 157 条验收标准 |
| [DECISIONS.md](DECISIONS.md) | 已确认决策、冲突裁决和边界 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 已通过 G3 的架构设计 |
| [架构图](docs/architecture-campus-album.html) | 校园影集架构可视化 |
| [PLAN.md](PLAN.md) | 已通过 G4 的实施计划与任务状态 |
| [CHANGELOG.md](CHANGELOG.md) | 变更、影响和待同步事项 |
| [AGENTS.md](AGENTS.md) | 工程规则、错误边界和协作协议 |
| [story.md](story.md) | S1—S7 实际实施步骤 |
| [docs/](docs/) | 课程原始资料：用户故事、PRD、功能设计、架构设计、测试文档、流程图和开题汇报 |

## 仓库边界

为保持仓库聚焦，以下内容**仅保留在本地**，已加入 `.gitignore`，不随 GitHub 发布：

- `tests/`、`tests-node/`
- `evidence/`
- `scripts/`
- `checklists/`
- `templates/`
- `.qoder/`、`.mcp.json`
- `ACCEPTANCE.md`、`METHODOLOGY.md`
- `.archify/`（仅架构图 HTML 已整理到 `docs/architecture-campus-album.html`）
- `.workbuddy/`

因此，克隆本仓库后可以执行 `npm run build:mini`、`npm run typecheck` 和 `npm run lint`，也可以运行后端；但 `npm test`、`npm run traceability`、`npm run check:all` 依赖本地保留的 `tests-node/` 与 `scripts/`，公开仓库不包含这些文件。完整的 G5 验收证据仍以本地记录和独立审查为准。

## 已知限制

- 微信开发者工具、iOS/Android 真机六页正反路径尚未完成。
- 原生上传边界、20 客户端性能、课堂演示和独立 G5 尚未执行。
- 公开仓库不包含验收证据，不能仅凭仓库内容宣称 G5 通过。
- 不提供生产部署、体验版或正式版发布配置。
