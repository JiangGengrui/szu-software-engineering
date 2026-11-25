# 校园影集｜架构联调与课堂演示主线复现指南

本文档面向项目组成员与课堂联调验收，补充三类信息：开题六人分工与本仓库实际代码的对应关系、macOS / 局域网真机（D-025）跨平台联调方法，以及围绕同一条「校运会」作品的端到端演示主线核验记录。

> 口径说明：本文档中的后端实测与编译检查记录仅代表对应环境下的机器验证与接口/后台回放，不替代 `PLAN.md` 中尚未执行的微信开发者工具、iOS/Android 真机、20 客户端性能及独立 G5 验收。

---

## 一、开题六人分工与仓库模块映射

| 课堂讲者与模块 | 后端核心文件 | 小程序 / 后台界面文件 | 重点接口与核对项 |
|---|---|---|---|
| **李文俊｜架构与联调** | `backend/album/__init__.py`、`models.py`、`common.py`、`seed.py` | `miniprogram/core/{config,transport,api,presentation}.ts` | 应用工厂、7 实体 SQLite 约束与写门、统一响应/错误壳、幂等 `init-demo`、跨平台与演示主线联调 |
| **陈俊年｜账号与权限** | `backend/album/auth.py` | `miniprogram/pages/login/`、`miniprogram/pages/settings/`、`miniprogram/core/auth.ts` | `POST /api/auth/{register,login,password,logout}`、`GET /api/auth/me`、7 天 Token 与 `token_version` 撤销 |
| **吕辉亮｜发布与作品维护** | `backend/album/work.py`、`backend/album/media.py` | `miniprogram/pages/{publish,edit,mine}/`、`miniprogram/core/{editor-page,multipart,media}.ts` | `POST/PUT/DELETE /api/works`、`GET /api/works/mine`、单次 multipart 上传与受控媒体校验 |
| **黄子特｜浏览与检索** | `backend/album/work.py` | `miniprogram/pages/{home,detail}/`、`miniprogram/core/paging.ts` | `GET /api/works`（日期 + 多标签 AND + 分页）、`GET /api/tags`、`GET /api/works/<id>`、请求代次防乱序 |
| **江耿锐｜评论与评分** | `backend/album/interaction.py` | `miniprogram/pages/detail/` | `GET/POST /api/works/<id>/comments`、`GET/PUT /api/works/<id>/rating`、同一用户改分覆盖且人数不变、禁自评 `1009` |
| **张轩玮｜管理员 Web 后台** | `backend/album/admin.py` | `backend/album/templates/*.html`、`backend/album/static/admin.{css,js}` | `/admin/login`（防爆破 + CSRF）、`/admin/users`（禁用同步下架作品）、`/admin/works`（移除作品同步至小程序） |

---

## 二、跨平台与局域网真机联调说明（D-025 适配）

1. **后端运行（macOS / Linux）**：
   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.lock.txt
   PYTHONPATH=backend SEED_ADMIN_PASSWORD="<管理员密码>" SEED_USER_PASSWORD="<演示学生密码>" \
     .venv/bin/python -m flask --app album:create_app init-demo
   PYTHONPATH=backend .venv/bin/python -m flask --app album:create_app run --host 127.0.0.1 --port 5000 --no-reload --no-debugger
   ```
   - 若 macOS 的 `5000` 端口被系统「隔空播放接收器 (AirPlay Receiver)」占用，可改用 `--port 5001`。
   - 真机调试（D-025）时改为 `--host 0.0.0.0`，确保手机与电脑位于同一可信局域网，并用本机局域网 IP 访问（不得在真机上请求 `127.0.0.1`）。

2. **小程序编译与不改源码切换 API 地址**：
   ```bash
   npm install
   npm run build:mini
   ```
   - 共享 `miniprogram/project.config.json` 保持 `urlCheck: true` 不变；本机微信开发者工具中在「详情 → 本地设置」勾选「不校验合法域名」（写入被 `.gitignore` 忽略的 `project.private.config.json`）。
   - `miniprogram/core/config.ts` 默认仍为 `http://127.0.0.1:5000`；联调端口 `5001` 或局域网 IP 时，可通过微信本地存储动态覆盖，避免污染受 Git 跟踪的源码：
     ```js
     // 切换为局域网后端或 5001 端口（仅接受 http(s)://host[:port] 根地址）
     wx.setStorageSync('campus_album_api_base_url', 'http://192.168.1.10:5000')

     // 恢复默认 http://127.0.0.1:5000
     wx.removeStorageSync('campus_album_api_base_url')
     ```

---

## 三、课堂核心演示主线与实测核验记录

### 演示步骤与验收口径

| 步骤 | 操作角色 | 核心请求 / 页面入口 | 预期结果 |
|---|---|---|---|
| 1. 初始化演示数据 | 组长 / 运维 | `flask --app album:create_app init-demo` | 幂等创建 `admin`、`student_a`、`student_b`、`student_c`（禁用）及 5 条演示作品 |
| 2. 发布作品 | 学生 A (`student_a`) | `POST /api/works`（`multipart/form-data`，带「校运会」标签） | 返回 `201`，生成新作品 ID，首页作品流可见 |
| 3. 日期 + 标签检索 | 学生 B (`student_b`) | `GET /api/works?date=YYYY-MM-DD&tag=校运会` | 返回 `200`，精准命中步骤 2 发布的「校运会」作品 |
| 4. 评论与改分去重 | 学生 B (`student_b`) | `POST /api/works/<id>/comments`、`PUT /api/works/<id>/rating`（4 分改 2 分） | 评论返回 `201`；改分后 `rating_avg` 由 `4.0` 更新为 `2.0`，`rating_count` 保持 `1` 不变 |
| 5. 后台移除作品 | 管理员 (`admin`) | `POST /admin/login`（带 CSRF）→ `POST /admin/works/<id>/remove` | 登录跳转 `/admin/users`；移除后 `303` 回 `/admin/works` 且作品状态置为 `removed` |
| 6. 跨端一致性验证 | 学生 B / 游客 | `GET /api/works`、同条件检索、`GET /api/works/<id>` | 首页与组合检索均不再包含该作品；旧详情返回 `HTTP 404`（业务码 `1010`：「作品已移除，无法查看」） |

### 2026-11-26 macOS 跨平台联调核验摘要

- **环境**：macOS，`Python 3.13`（项目 `.venv`，依赖按 `requirements.lock.txt` 安装）、`Node v26.0.0`、`npm 11.12.1`，临时隔离实例 `ALBUM_INSTANCE_PATH`（不污染默认 `instance/`）。
- **静态与编译检查**：
  - `mypy backend`：9 个源文件 0 错误通过。
  - `ruff check backend`：代码逻辑与风格 0 错误（注：若仓库位于 OneDrive 同步目录，macOS 可能附加可执行位触发 `EXE002`，需保持标准 `0644` 权限）。
  - `npm run typecheck`、`npm run build:mini`、`npm run lint`：全部退出码 `0` 通过。
- **真实服务主线回放**：按上表步骤 1–6 在本地真实 Flask 进程完整回放通过，并在重启服务后核验持久化数据完整保留。
- **待实机补齐项**：微信开发者工具与 iOS/Android 真机六页人工交互、原生媒体上传边界（P-21/P-25）及课堂计时彩排（P-29）仍按 `PLAN.md` 保持待验证状态。
