# 账号与权限模块｜接口契约

适用范围：`backend/album/auth.py`、`miniprogram/core/auth.ts`、`miniprogram/pages/login/`、`miniprogram/pages/settings/`。
对应需求：R-01～R-04；对应验收标准：AC-01～AC-21、AC-143。
本文只描述已实现的契约，不新增或修改任何业务规则；规则冲突时以 `SPEC.md` 为准。

---

## 1. 角色与权限边界

| 能力 | 游客 | 普通用户 `user` | 管理员 `admin` |
|---|---|---|---|
| 浏览首页、详情、检索、看评论与评分 | ✅ | ✅ | ✅ |
| 注册普通账号 | ✅ | — | — |
| 发表评论 | ✅（匿名） | ✅ | ❌ 小程序不接受管理员凭据 |
| 发布 / 编辑 / 移除自己的作品 | ❌ | ✅ | ❌ |
| 评分（不可自评） | ❌ | ✅ | ❌ |
| 修改本人密码、退出登录 | ❌ | ✅ | ❌（管理员在后台操作，见 §6） |
| 后台查询、禁用用户、移除作品 | ❌ | ❌ | ✅（独立会话） |

设计要点：**两种身份走两条互不相通的认证通道**。小程序接口只认 `role='user'` 的 Token；后台只认服务端 Session 里的 `role='admin'`。管理员凭据无法用于小程序接口，小程序 Token 也无法进入后台。

---

## 2. 通用约定

### 2.1 响应壳

```json
{ "code": 0, "message": "ok", "data": { } }
```

失败时 `code` 为非 0 业务码，`data` 恒为 `null`：

```json
{ "code": 1007, "message": "用户名或密码错误", "data": null }
```

**判定规则**：以 HTTP 状态码与 `code` 同时判定。`code === 0` 且 2xx 才是成功；网络失败时 `code` 为 0 且状态码为 0（见 `miniprogram/core/transport.ts`），属于「结果未知」，写请求不得自动重放。

### 2.2 请求约束

- 所有 POST 请求体必须是 `application/json`；非 JSON 体返回 `1001`。
- 请求体**只接受本文列出的字段**，出现多余字段返回 `1001`（例如注册时携带 `role`、`admin` 会被拒绝，客户端无法提权）。
- 同一 JSON 键重复出现返回 `1001`。
- 接口不接受查询参数，带了返回 `1001`。
- 统一响应头：`Cache-Control: no-store`、`X-Request-ID`、`X-Content-Type-Options: nosniff`。

### 2.3 凭据格式

```
Authorization: Bearer <签名凭据>
```

前缀必须严格为 `Bearer `（大写 B、一个空格）。缺失、前缀不符、验签失败、时间越界一律返回 `401 / 1002`。

### 2.4 输入规则（§4.9）

| 字段 | 规则 | 失败码 |
|---|---|---|
| `username` | 3—20 个字符；仅 `A-Z a-z 0-9 _`、CJK 基本区 `U+4E00–U+9FFF`、扩展 A `U+3400–U+4DBF`、扩展 B `U+20000–U+2FA1F`；区分大小写 | `1001` |
| `password` | 8—20 个字符；必须同时包含字母与数字；允许其他字符 | `1001` |

字符计数按 Unicode 码点，不按字节。密码以 `pbkdf2:sha256:600000` 哈希存储，任何响应和日志都不返回哈希。

---

## 3. 接口

### 3.1 注册 `POST /api/auth/register`

请求：

```json
{ "username": "student_a", "password": "Student1234" }
```

成功 `201`：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user": { "id": 6, "username": "student_a", "role": "user" },
    "token": "eyJ1aWQiOjYsInRva2VuX3ZlcnNpb24iOjB9.aXQ0aGc....",
    "expires_at": "2026-12-03T08:00:00Z"
  }
}
```

- 注册与登录**返回同一结构**，客户端拿到即可直接进入登录态，无需二次输入凭据（AC-02）。
- 新账号固定为 `role='user'`、`status='active'`、`token_version=0`。
- 用户名唯一性由 `users.username UNIQUE` 兜底：先友好预检，并发下仍由唯一约束裁决，两种情况都返回 `1006`。

| 情况 | 状态码 | code |
|---|---|---|
| 用户名或密码不合规 / 缺字段 / 多余字段 | 400 | `1001` |
| 用户名已存在 | 400 | `1006` |

### 3.2 登录 `POST /api/auth/login`

请求同注册。成功 `200`，`data` 结构与注册一致。

| 情况 | 状态码 | code | 说明 |
|---|---|---|---|
| 用户名不存在 | 400 | `1007` | 与密码错误**完全同一响应**，不泄漏账号是否存在 |
| 密码错误 | 400 | `1007` | 同上 |
| 账号 `disabled` | 403 | `1008` | 仅在**密码正确**后才会返回，避免用 1008 反推账号存在 |
| 角色为 `admin` | 403 | `1003` | 管理员只能走 `/admin/login` |

> 时序防护：用户不存在时也会对一份固定的 dummy 哈希执行一次校验，避免用响应时间区分「账号不存在」与「密码错误」。

### 3.3 当前用户 `GET /api/auth/me`

请求头带凭据，无请求体、无查询参数。成功 `200`：

```json
{ "code": 0, "message": "ok", "data": { "id": 6, "username": "student_a", "role": "user" } }
```

| 情况 | 状态码 | code |
|---|---|---|
| 无凭据 / 前缀不符 / 验签失败 / 已过期 | 401 | `1002` |
| 用户不存在 / `disabled` / `token_version` 不一致 | 401 | `1002` |
| 用户角色为 `admin` | 403 | `1003` |

注意区分：**登录时**禁用账号返回 `403/1008`；**已登录后被禁用**，下一次请求返回 `401/1002`。因为每次请求都会回表校验 `status`，禁用是即时生效的，不需要等凭据过期。

### 3.4 修改密码 `POST /api/auth/password`

需要凭据。请求：

```json
{ "old_password": "Student1234", "new_password": "Changed2026" }
```

成功 `200`：`data` 为 `null`。

| 情况 | 状态码 | code |
|---|---|---|
| 未登录 / 凭据失效 | 401 | `1002` |
| 原密码错误 | 400 | `1007` |
| 新密码不合规 / 与原密码相同 / 缺字段 / 多余字段 | 400 | `1001` |

成功后 `token_version += 1`，该用户**此前版本的全部凭据立即失效**，包括发起本次改密的那个。客户端须在成功后清除本地登录态并要求重新登录（AC-18）。

校验顺序：先确认登录 → 再校验原密码 → 再校验新密码规则 → 再比对新旧是否相同。

### 3.5 退出登录 `POST /api/auth/logout`

需要凭据，请求体必须为空（带非空体返回 `1001`）。成功 `200`：`data` 为 `null`。

- 成功后 `token_version += 1`，同版本的其他凭据一并失效。
- 用已失效的凭据再次退出返回 `401/1002`，**不产生 500**（AC-21）。
- 退出只作废旧版本；重新登录会签发新版本凭据，立即可用。

---

## 4. 凭据生命周期

### 4.1 签发

```
payload = { "uid": <int>, "token_version": <int> }
token   = URLSafeTimedSerializer(secret, salt="album-user-token-v1").dumps(payload)
```

- 签名密钥来源：`SECRET_KEY` 环境变量；未配置时首次启动生成 `instance/secret.key`（32 字节十六进制）。
- 载荷是**明文可读但不可篡改**的（签名保护，非加密）。因此载荷中不放用户名、角色等任何敏感信息；角色以数据库当前值为准，不信任载荷。

### 4.2 有效期

| 项 | 值 | 说明 |
|---|---|---|
| `expires_at` 字段 | 签发时刻 + `604800` 秒 | 给客户端做本地提前判断 |
| 服务端验签上限 | `max_age = 604799` 秒 | 第 604799 秒仍可用，满 604800 秒起拒绝 |

两个数字相差 1 秒是刻意为之：客户端用 `expires_at` 判断「是否过期」，服务端用 `max_age` 判断「是否超龄」，边界口径都落在「满 7 天即失效」。

### 4.3 校验顺序

`require_user()` 按下列顺序短路，任何一步失败即返回，不继续执行：

```
1. Authorization 前缀是否为 "Bearer "
2. 验签 + 时间窗（签名时间不得晚于当前时间，年龄不得超过 604799 秒）
3. 载荷类型与范围（uid、token_version 必须是 int；1 ≤ uid ≤ 2^63-1）
4. 按 uid 查用户；不存在 → 1002
5. status 是否 active          → 否：1002
6. token_version 是否与载荷一致 → 否：1002
7. role 是否为 user            → 否：1003
```

第 5、6 步是整套撤销机制的核心：**无状态凭据 + 每次回表比对版本号**。改密、退出、禁用三种场景都不需要维护黑名单。

### 4.4 撤销语义

| 触发 | 作用范围 | 实现 |
|---|---|---|
| 退出登录 | 该用户当前版本的全部凭据 | `token_version += 1` |
| 修改密码 | 同上 | `token_version += 1` |
| 管理员禁用账号 | 该用户全部凭据（因 `status` 校验） | 改 `users.status` |
| 自然过期 | 单个凭据 | `max_age` |

---

## 5. 小程序客户端状态机

`miniprogram/core/auth.ts` 的 `AuthManager` 维护三份状态：`record`（凭据与用户）、`confirmed`（是否经服务端确认）、`generation`（请求代次）。

| 方法 | 行为 |
|---|---|
| `accept(result)` | 校验结构、`role === 'user'`、未过期后落盘并置为已确认；否则清态并抛 `1003` |
| `confirm()` | 读取本地记录 → 调 `/api/auth/me` 回表确认；401/403 清态返回 `null`，网络错误原样抛出 |
| `user()` / `token()` | 仅在**已确认且未过期**时返回值，未确认一律视为游客 |
| `clear()` | 递增 `generation`，丢弃进行中的确认请求，清本地存储 |

关键约束：

- **本地有凭据不等于已登录**。启动时 `app.ts` 调一次 `confirm()`，未确认前按游客处理（AC-11）。
- 401/403 统一清态并回到登录页，登录成功后按 `?from=` 参数回到原页面（AC-12）。来源页白名单只允许 `home`、`publish`、`mine`、`settings`、`detail:<id>`、`edit:<id>`，其他值一律回落首页，防止开放重定向。
- 改密成功后立即 `auth.clear()` 再跳登录（AC-18）。
- 退出时若服务端未确认，本地仍清态，但必须提示「不能确认旧凭据已撤销」，不得显示成功。

---

## 6. 管理后台会话（对照）

管理员**不复用**小程序的 7 天 Token，是刻意的设计：两者威胁模型不同。

| 项 | 小程序 Token | 后台会话 |
|---|---|---|
| 载体 | `Authorization: Bearer` | Cookie `album_admin` + 服务端注册表 |
| 有效期 | 7 天（绝对） | 30 分钟（绝对，不滑动续期） |
| 撤销 | `token_version` | 从注册表移除 sid |
| 防爆破 | 无（不限制普通用户登录次数） | 同一账号连续 5 次失败锁 300 秒 |
| CSRF | 不适用（无 Cookie） | 双提交 Token，所有 POST 校验 |
| 提权防线 | `role !== 'user'` → `1003` | `role !== 'admin'` → `2002` |

后台错误码：`2001`（会话失效，401）、`2002`（非管理员，403）。登录成功统一 303 跳转 `/admin/users`，不接受外部 `next` 地址。

---

## 7. 错误码速查

| code | 状态码 | 含义 | 本模块触发场景 |
|---|---|---|---|
| `1001` | 400 | 参数不合法 | 字段缺失/多余/类型错、用户名或密码不合规、新旧密码相同、请求体非空 |
| `1002` | 401 | 请重新登录 | 凭据缺失/伪造/过期/版本失效/账号被禁用/用户不存在 |
| `1003` | 403 | 无权限 | 管理员凭据用于小程序接口；CSRF 校验失败 |
| `1007` | 400 | 用户名或密码错误 | 登录凭据错；改密时原密码错 |
| `1008` | 403 | 账号已禁用 | 禁用账号在**登录时**尝试登录 |
| `1006` | 400 | 用户名已存在 | 注册重名 |
| `2001` | 401 | 管理会话已失效 | 后台会话过期或已登出 |
| `2002` | 403 | 仅管理员可进入 | 非管理员访问后台 |

---

## 8. 实现位置索引

| 关注点 | 位置 |
|---|---|
| 签发与验签、五个接口 | `backend/album/auth.py`：`issue_token` / `require_user` / `register` / `login` / `me` / `password_change` / `logout` |
| 错误码与响应壳 | `backend/album/common.py`：`ERRORS` / `ok` / `error_json` |
| 事务与写门 | `backend/album/common.py`：`transaction` / `atomic` |
| 用户名存储（区分大小写） | `backend/album/models.py`：`username String(20, collation="BINARY") UNIQUE` |
| 客户端状态机 | `miniprogram/core/auth.ts` |
| 登录/注册页与来源页回跳 | `miniprogram/pages/login/index.ts`、`miniprogram/core/source.ts` |
| 改密/退出页 | `miniprogram/pages/settings/index.ts` |
| 客户端输入校验 | `miniprogram/core/validation.ts`：`validateUsername` / `validatePassword` / `validateCredentials` / `validatePasswordChange` |
| 用例 | `tests/auth/`（后端，pytest）、`tests-node/auth.test.cjs`（客户端状态机，node:test） |
