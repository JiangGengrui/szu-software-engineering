# AGENTS — 校园影集项目规则

执行基线：SPEC 0.3、DECISIONS原型0.2、ARCHITECTURE 0.1、PLAN 0.1；G1—G4均经独立审查通过，当前S6，Gm在当前树通过，G5未通过。以下命令须真实执行后才记通过，不把规则文件当证据。

## 1. 目录与命名

- backend/album：应用工厂、common/auth/work/media/interaction/admin六模块与models；表现层→Blueprint→Service→ORM。
- backend/album/templates与static：Jinja2管理三页、CSS及必要确认脚本；不做SPA。
- miniprogram：原生TypeScript/WXML/WXSS/JSON，tsc生成同目录CommonJS JS；不是H5。tests-node保存小程序核心和工具脚本测试，tests保存后端测试。
- 表现层统一“相纸质”（D-030）：纸底`#FBF6E9`、相纸框`#FFFDF7`、焦糖`#C2703A`、深棕`#8A5A2B`；标题用系统宋体栈`Songti SC/STSong/Noto Serif CJK SC/SimSun`并在无宋体的Android回退无衬线，不加载网络字体；tabBar图标为WXSS内联SVG data-URI，不引入图标库或图片图标。首页默认相纸翻页（一屏一张），与列表视图共用同一分页数据。
- instance：数据库、签名密钥、媒体/tmp，不是静态目录；测试使用独立临时实例。原docs文档不覆盖。
- scripts：构建和追溯工具；.archify是设计图及其回执，不属于业务实现或应用验收。
- Python使用snake_case、类型标注与SQLAlchemy2映射；TypeScript使用camelCase。后端DTO显式列字段，不返回整个ORM对象。
- 依赖锁定于requirements.lock.txt及package-lock.json；仅D-003已授权范围，不修改全局环境，不增加服务/解析器/转码库。
- 当前Bash实测Python3.12.4、Node22.15.0、npm10.9.2；架构图工具使用已有Node24.18.0。应用依赖安装版本以锁文件为准，不用会话环境摘要代替实测。

## 2. 错误与边界

- 服务端在写门和当前事务中校验身份/角色/状态；request user_id/role不能提权。SQLite显式BEGIN保证读快照，所有写入口使用同一进程RLock，单进程运行。
- JSON壳、HTTP/业务码、后台HTML失败状态严格按架构§4；后台每次认证成功进入/admin/users，小程序回已知来源页面，不接受外部next地址。
- 评论身份→作品→内容，评分身份→作品→分数→自评；发布/编辑检查最终有效作品，允许纯媒体，不允许标题单独满足内容。
- 码点计数、二进制MB、名称区分大小写、北京时间、日期缺字段/空值、标签AND均按SPEC，不改变已确认边界；标签先移除零宽/控制字符并折叠内部空白，封面≤512KiB且不占1—9张名额，暂存引用仅上传者可用且重启时只清理超过1小时的无引用文件。
- 上传UUID受控键，暂存/移动/DB提交一次；逐文件暂存上传直接写入`u{上传者id}-{uuid}`受控键；提交前失败补偿仅删除本请求新文件；旧媒体inactive、软删除及禁用保留历史文件。媒体GET/HEAD/Range与封面GET每次校验状态，no-store。
- Token满604800秒拒绝，退出/改密递增版本；普通用户登录按账号5次失败锁300秒；后台独立Session空闲30分钟、每次已认证请求续期且签发后8小时绝对失效，按账号5次失败锁300秒，CSRF。
- 超时是结果未知，不能自动重放写请求或显示成功；列表保留筛选、表单保留非密码输入，原生详情收到不可用时清内容及互动。
- 不记录密码/哈希、Authorization、Cookie、完整Token、上传原文件名或用户输入；日志仅请求ID、路由模板、状态码、耗时。debug/reloader关闭，Jinja转义，原生用户内容用text不注入HTML。

## 3. 必须通过的校验

工作目录为项目根；使用项目虚拟环境，不依赖全局Python包。项目内虚拟环境、node_modules及锁文件已建立；当前机器检查通过记录见`evidence/checks-2026-11-22T07-28-05-589Z`，代码或工具变化后须重跑。

```bash
.venv/Scripts/python.exe -m ruff check backend tests
.venv/Scripts/python.exe -m mypy backend
.venv/Scripts/python.exe -m pytest tests --cov=album --cov-branch --cov-report=term-missing
npm run lint
npm run typecheck
npm test
```

npm lint/test先编译原生TypeScript；ESLint必须扫描全部生成业务JS及手写JS，TypeScript检查源TS，node:test使用相同产物。测试/扫描非空，不以排除业务目录或空脚本通过Gm。

```bash
npm run build:mini
node scripts/check-traceability.mjs .
```

追溯退出0仅表示结构规则满足，不等于G5。真实后台必须启动服务并在浏览器操作；小程序按D-025在微信开发者工具与iOS/Android真机调试模式下验证，mock/API/HTML不替代。手机开启调试、本机private配置urlCheck=false与局域网HTTP是D-025固定环境的一部分，须连同工具/基础库/机型版本记入证据；共享project.config.json保持urlCheck=true，不得把该环境说成体验版/正式版可用。缺环境保持未验证，性能2秒/5秒不能因超时参数15秒/60秒而放宽（P-27仍要求本机回环20客户端）。

运行接口（实现后验证）：PYTHONPATH=backend .venv/Scripts/python.exe -m flask --app album:create_app run --host 127.0.0.1 --port 5000；初始化使用同一app的init-demo命令，密码由SEED_ADMIN_PASSWORD、SEED_USER_PASSWORD配置输入，不打印。不得自动清库或覆盖已有实例。原生真机验收按D-025改为`--host 0.0.0.0`并把小程序API地址指向电脑局域网IP；真机不得请求127.0.0.1，仅限可信局域网内使用。

## 4. 协作协议

遵循METHODOLOGY §8：A1合理需求解释分叉、A2新技术取舍、A3删除/覆盖已有产出、A4验收不可判、A5上游冲突、A6新依赖/服务/费用均须停止相关动作并记录；不擅自替用户裁决。B1命名格式、B2既定架构实现细节、B3不改行为的测试/重构、B4措辞排版、B5已确认决策执行可自主。

已通过G1—G4及D-003授权意味着可按当前基线实施，不重复询问已确认事项。遇到真实新分歧给问题、A/B代价收益、倾向及阻塞点；无确认不得扩大范围。只保存实际决定，变更按CHANGELOG影响矩阵同步。

作者不能自行宣布闸门通过；代码修改后实际重跑机器检查和受影响交互，由未参与生产的上下文独立审查。AC仅SPEC定义，T/E仅ACCEPTANCE定义；未执行保持未验证。既有设计图/模板/历史预期输出不是应用证据。
