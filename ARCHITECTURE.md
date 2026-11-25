# ARCHITECTURE — 校园影集

版本0.1；2026-11-20；状态：架构已通过独立G3，PLAN 0.1已通过独立G4，进入S5按本契约实现。项目依赖已安装锁定，业务及测试进行中，Gm/G5未通过。架构图是设计图，不是已部署系统的证据。

## 1. 上下文与输入

- 需求输入：SPEC 0.3，31R/157AC，已通过独立G1；全部Must/Should均实现，不按旧六人分工或旧四周日期分配工作。
- 形态输入：DECISIONS D-001～D-019及九页面原型0.2，已通过独立G2；首页V1单列动态，三Tab，后台成功登录统一到用户管理。
- 已选栈：原生微信小程序；Python 3.12、Flask/Jinja2、Flask-SQLAlchemy/SQLAlchemy、SQLite、本地媒体。表现层→Blueprint→Service→ORM，不新增外部服务。
- 规模：一个后端进程、最多20个演示客户端；正式性能样本200作品、1000评论、1000评分。首页/检索20客户端并发、上传单请求，各冷客户端缓存5次；时限仍为2秒/5秒，不用设计推断实测通过。
- 执行组织：当前AI按阶段生产，新上下文独立审查。未承诺新的交付日；S4用相对工作日和可观察状态排程。
- 部署边界：开发服务默认只监听127.0.0.1，debug/reloader关闭；不是公网生产服务器。不修改系统/全局依赖，项目内安装仅限D-003。
- 外部运行条件：微信客户端/开发者工具、可用AppID及真机网络条件尚未验证。S4准备环境，S6缺条件则标未验证，不改用H5。

## 2. 组件、职责和目录边界

| 组件与计划位置 | 管什么 | 不管什么 |
|---|---|---|
| miniprogram/ 原生页面P01—P06 | WXML/WXSS、TypeScript、页面来源、表单反馈、列表请求代次、系统媒体选择与原生播放 | 不决定权限、数据库状态、全局评分或Token有效性 |
| backend/album/templates + static | Jinja2 P07—P09、HTML表单、Flash、浏览器确认与提交状态 | 不直连SQLite、不保存管理密码、不实现独立SPA |
| common | 配置、JSON响应、输入基础解析、日期/码点工具、进程内写入锁、事务入口 | 不编排注册/发布/评分业务、不吞未知异常冒充成功 |
| auth Blueprint + AuthService | 注册/登录、Token签验、版本撤销、改密、管理员Session/锁定 | 不修改作品正文，不信任请求role/user_id |
| work Blueprint + WorkService | 公开/本人/管理查询，发布编辑删除，标签关联，事务编排 | 不决定媒体物理路径，不直接返回文件字节 |
| media Blueprint + MediaService | 上传校验、UUID文件键、暂存/落盘/回滚、媒体状态校验及Range读取 | 不根据客户端路径读文件，不绕过作品/作者状态 |
| interaction Blueprint + InteractionService | 评论、单用户评分更新、统计 | 不改变作品/作者，不物理删除历史互动 |
| admin Blueprint + AdminService | 管理查询、禁用/移除、渲染上下文、后台登出 | 不复制公开API的过滤条件，不增加恢复或批量操作 |
| models + SQLite | 七实体、索引、唯一/外键/检查约束 | 不渲染、不替代Service权限与输入校验 |
| instance/ | 数据库、随机签名密钥、受控media目录与tmp目录 | 不进入静态路由、源码包或版本跟踪；不存真实学生敏感信息 |
| tests/、scripts/ | 双端核心/接口/浏览器测试、初始化、追溯与证据工具 | 不把模拟wx或设计数据当原生交互证据 |

后端使用应用工厂注入测试配置；Blueprint解析传输格式，Service接收明确字段和当前事务会话，ORM只返回内部实体。公开DTO在Service/序列化函数显式列字段，不序列化整个User对象。

### 2.1 主请求与状态流

1. 小程序读公开作品不带也不需要Token；受限请求带Authorization: Bearer。服务器在当前事务内解析身份、读取User并校验active/token_version/role。
2. 后台浏览器先GET登录页取得CSRF令牌，POST凭据；Session成功后重定向/admin/users。其他后台页面无Session重定向登录；写操作无Session返回401/2001，不把重定向当成功。
3. 发布/编辑：解析multipart→锁与事务→身份/归属/状态→有效字段/媒体校验→暂存新文件→写实体与关联→移至最终UUID路径→一次提交→201/200。
4. 禁用：锁与事务内再次查Session/管理员→查目标→拒绝自己→检查状态→用户disabled、全部作品removed→一次提交。公开查询/媒体路由按新状态拒绝访问。
5. 客户端仅在收到成功响应后切换成功状态；超时视为结果未知，先查状态，不自动重放写请求。详情发现1010必须清内容及互动区。

## 3. 数据契约

所有主键为SQLite INTEGER；时间以UTC保存，接口输出带Z的ISO8601；activity_date为DATE，今天按UTC+08:00计算（当前中国标准时间，无新增时区包）。文本长度按Unicode码点。用户名/标签存原大小写，唯一约束使用SQLite BINARY，不使用NOCASE。

| 实体 | 字段与约束 |
|---|---|
| User | id PK；username VARCHAR(20) NOT NULL UNIQUE BINARY；password_hash TEXT NOT NULL；role CHECK(user/admin)；status CHECK(active/disabled)；token_version INTEGER>=0；created_at NOT NULL；admin_failures INTEGER>=0默认0；admin_locked_until UTC可空 |
| Work | id PK；user_id FK User.id NOT NULL；title VARCHAR(50)默认空；content TEXT默认空；activity_date DATE NOT NULL；status CHECK(visible/removed)默认visible；created_at、updated_at NOT NULL |
| Media | id PK；work_id FK Work.id NOT NULL；kind CHECK(image/video)；file_key TEXT UNIQUE NOT NULL；mime TEXT；size_bytes INTEGER>0；position INTEGER>=0；active BOOLEAN默认真；created_at NOT NULL |
| Tag | id PK；name VARCHAR(10) UNIQUE BINARY NOT NULL |
| WorkTag | work_id FK Work.id、tag_id FK Tag.id，二者构成联合PK，不另存关联数量 |
| Comment | id PK；work_id FK Work.id；user_id FK User.id；content TEXT NOT NULL；created_at NOT NULL |
| Rating | id PK；work_id FK Work.id；user_id FK User.id；score INTEGER CHECK 1<=score<=5；created_at、updated_at；UNIQUE(work_id,user_id) |

- 外键每个连接启用PRAGMA foreign_keys=ON；不配置用户/作品的物理级联删除入口。软移除、禁用均保留Work/Media/Comment/Rating及磁盘文件。
- 当前有效媒体用active=true及position排序。替换将旧Media.active=false、增加新行；旧文件保留但旧ID不可访问。新媒体position从0递增；同一有效集合的位置唯一由串行写事务保证。
- 索引：Work(status,created_at,id)、Work(user_id,created_at,id)、Work(activity_date,status)、WorkTag(tag_id,work_id)、Comment(work_id,created_at,id)、Media(work_id,active,position)。Rating唯一索引同时用于人数/均分查询。
- 稳定顺序：作品created_at DESC,id DESC；评论created_at DESC,id DESC；后台用户id DESC。编辑不改created_at，标签查询不改变公开排序。
- 公开可见谓词固定为Work.status=visible AND User.status=active。公开详情/媒体/互动每次都重查；本人列表保留本人removed元信息，管理列表不过滤removed。
- 多标签AND使用关联查询与去重后的标签数量比较；未知标签直接空集。查询不创建Tag。用户名子串将%、_等LIKE元字符按普通字符转义，所有值用绑定参数；大小写遵循原名称，不用SQLite默认不区分ASCII大小写的LIKE来改变业务匹配。
- 平均分按整数sum/count，用Decimal ROUND_HALF_UP到1位小数；无评分时rating_avg=null、rating_count=0。客户端只在count>0显示一位小数，否则“暂无评分”；禁用评分者仍计入sum/count，不公开评分者列表。

### 3.1 对外DTO

| 名称 | 明确字段 |
|---|---|
| UserPublic | id, username, role；不含password_hash、token_version或锁定内部字段 |
| AuthResult | user: UserPublic, token, expires_at；仅注册/登录成功返回token |
| MediaPublic | id, kind, url=/media/{id}, mime, size_bytes, position；不含磁盘路径/原文件名 |
| WorkCard | id,title,summary,user:{id,username},activity_date,created_at,status,media_kind,cover_url,rating_avg,rating_count |
| WorkDetail | WorkCard加content,tags:名称数组,media:MediaPublic数组；不增加评分者身份列表 |
| MyWorkCard | id,title,summary,activity_date,created_at,status,media_kind,cover_url；removed的cover_url=null，不输出可播放媒体入口 |
| CommentPublic | id,content,display_name,created_at；禁用评论者display_name=已注销用户，不输出原用户名或其他身份字段 |
| RatingStats | rating_avg,rating_count,my_score；my_score仅评分写响应或当前用户评分查询中返回，公开详情不依赖认证 |
| Page<T> | list:T[],total,page,page_size；超过末页list=[]，不回退最后一页 |
| AdminUserRow | id,username,role,status,created_at,work_count；计数含removed，在列头标明 |
| AdminWorkRow | id,user:{id,username},title,summary,activity_date,tags,status |

summary取content前80码点，无正文时为空，由标题/媒体标识呈现卡片；不把省略号算入原始正文。cover_url仅image时为position=0的有效媒体；video用标识，不生成视频截图。MyWorkCard的removed摘要不用于恢复P03内容。

## 4. 接口契约

### 4.1 传输与共同校验

- JSON成功为{code:0,message:"ok",data:...}；JSON错误为{code:非零,message:中文提示,data:null}。业务错误沿用SPEC §4.7，不增加代码或重用1016表示非文件错误。
- JSON请求为对象，重复敏感字段/错误类型拒绝400/1001；multipart文本字段最多一次，文件字段允许重复；不接受客户端id/user_id/role/status改变身份或所有权。未知字段拒绝400/1001。
- GET分页page默认1、page_size默认10（评论20）；page>=1，page_size在1—20；非法数字/重复单值/越界400/1001。date为可选YYYY-MM-DD；不传或查询空值表示无日期过滤，区别发布显式空日期非法。
- 查询标签用重复tag名称参数；UTF-8 URL编码；trim、去重、区分大小写，多项AND，空项/超出名称长度400/1001。查询只检查名称合法，不因超过5个查询标签而截断；发布/编辑仍最多5标签。
- 所有写字段后端再验证，前端只提前反馈。正文/标签/评论trim，用户名不自动改写，标题保留输入。密码不trim、不回显；字母/数字规则依SPEC执行。
- 文件multipart字段images可重复、video可重复以便明确拒绝多视频；text字段title/content/activity_date/tags，tags为JSON字符串数组；省略tags时发布[]。不让逗号分隔破坏合法标签名称。
- 发布缺activity_date才默认北京时间今天；空/null非法。编辑省略title/content/tags/activity_date分别保留旧值；显式title/content空串允许，tags=[]清标签，日期空/null非法。省略媒体或未传文件保留原媒体，有文件整体替换，无清空全部媒体标志。
- 请求体上限100MiB（9×10MiB加表单开销）；超过总上限归400/1015。字段上限仍分别验证，不能以总大小替代每文件大小。不得截断正文/文件使非法输入变合法。

### 4.2 小程序与公开API

| 方法与路径 | 输入 | 成功data / HTTP | Service校验及主要失败 |
|---|---|---|---|
| POST /api/auth/register | JSON username,password | AuthResult / 201 | Auth：字段/用户名/密码→唯一性；1001/1006；两次确认在客户端 |
| POST /api/auth/login | JSON username,password | AuthResult / 200 | Auth：字段→统一凭据错误1007→disabled 1008→拒绝admin 1003 |
| GET /api/auth/me | Bearer | UserPublic / 200 | Auth：签名/期限→DB版本/active→普通用户；1002/1003 |
| POST /api/auth/password | Bearer；JSON old_password,new_password | null / 200 | Auth：身份→字段→原密1007→新密规则/与旧相同1001；成功递增版本 |
| POST /api/auth/logout | Bearer；无业务字段 | null / 200 | Auth：有效普通用户才递增版本；无效/重复Token返回401/1002，客户端清本地，不能500 |
| GET /api/works | date、重复tag、page、page_size | Page<WorkCard> / 200 | Work：参数→公开可见过滤；1001 |
| GET /api/tags | 无 | [{id,name}] / 200 | Work：按名称顺序返回已存标签，不写死列表 |
| GET /api/works/{id} | 正整数路径ID | WorkDetail / 200 | Work：不存在1004；removed/作者disabled 1010 |
| GET /api/works/mine | Bearer；page/page_size | Page<MyWorkCard> / 200 | Work：身份→分页→仅当前用户（含removed）；1002/1003/1001 |
| POST /api/works | Bearer；multipart | WorkDetail（含id）/ 201 | Work/Media：按§4.4；1001/1002/1003/1011—1016 |
| PUT /api/works/{id} | Bearer；multipart部分字段 | WorkDetail / 200 | Work/Media：身份→存在1004→归属1003→removed 1005→编辑后整体字段校验 |
| DELETE /api/works/{id} | Bearer；无业务字段 | {id,status:"removed"} / 200 | Work：身份→存在1004→归属1003→状态1005→软移除 |
| GET /api/works/{id}/comments | page/page_size，默认20 | Page<CommentPublic> / 200 | Interaction：存在/可见1004/1010→分页1001 |
| POST /api/works/{id}/comments | Bearer；JSON content | CommentPublic / 201 | Interaction：身份→作品可见→trim后1—500；1002/1003/1004/1010/1001 |
| GET /api/works/{id}/rating | Bearer | RatingStats / 200 | Interaction：身份→作品可见；尚未评分my_score=null；本人作品也可读统计 |
| PUT /api/works/{id}/rating | Bearer；JSON score | RatingStats / 200 | Interaction：身份→可见→1—5整数（拒绝bool）→禁自评1009→插入/更新唯一评分 |
| GET /media/{id} | ID；可带标准Range头 | 原媒体字节 / 200或206 | Media：记录存在→active→作品visible/作者active→受控键/存在文件；不可用404/1010，未知ID404/1004 |

媒体成功不套JSON；不满足的字节Range按HTTP标准416，不用业务400代替。HEAD与GET使用同一状态检查。未知API路径404/1004，不把字符串路径当磁盘路径；方法不匹配由HTTP405表达，不执行写动作。

### 4.3 后台HTML与管理写操作

| 方法与路径 | 入参 | 成功 | 校验/失败 |
|---|---|---|---|
| GET /admin/login | 无 | 登录HTML 200；已有有效Session→/admin/users | 生成匿名会话CSRF令牌，不暴露凭据 |
| POST /admin/login | form username,password,csrf_token | 签发管理员Session，303到/admin/users | CSRF→字段→按账号锁定→凭据→active→role；锁定409/1005并显示解锁剩余秒；错凭据400/1007；disabled403/1008；非管理员403/2002 |
| POST /admin/logout | form csrf_token | 撤销当前Session，303到/admin/login | 无Session401/2001；非管理员403/2002；CSRF失败403/1003 |
| GET /admin/users | username,user_id,role,status,page,page_size | Jinja用户表格200 | Session/role→筛选；无Session302登录，非管理员403无数据；参数400/1001 |
| GET /admin/works | author,date,重复tag,status,page,page_size | Jinja作品表格200 | 同上；author按用户名子串；removed可查 |
| POST /admin/users/{id}/disable | form csrf_token及当前合法筛选 | 成功Flash后303回用户列表 | Session→role→CSRF→存在1004→禁止自己1003→disabled冲突1005→原子禁用/移除 |
| POST /admin/works/{id}/remove | form csrf_token及当前合法筛选 | 成功Flash后303回作品列表 | Session→role→CSRF→存在1004→removed冲突1005→修改 |

后台写失败返回匹配HTTP状态的HTML错误/表单页，显示业务码及中文提示，不能以200或成功Flash掩盖失败。JSON接口才使用统一JSON壳；表单可读失败结果不要求小程序JSON协议。筛选回跳只重建本站固定列表路径与白名单参数，不接受任意next URL。后台每次重新认证成功只进入/admin/users。

### 4.4 复合失败与输入验证顺序

- 公共读：解析路由→查询字段类型/范围→查询。详情/媒体按目标存在和可见状态判定；媒体不得先开文件后鉴权。
- 注册：字段类型→用户名格式/长度→密码格式/长度→用户名唯一。
- 登录：字段类型→凭据（不存在与错密同1007）→账号状态→角色；管理登录在凭据前检查该账号锁定。管理员账号第5次凭据失败设置locked_until=now+300s；成功清零，达到期限清锁后开始下一轮。
- 发布/编辑内容验证：身份/编辑权限与状态→字段类型→标题→正文上限→活动日期→标签→A正文或媒体存在→B不混合→C图片合法→D视频合法→写入。对应1011/1014/1015按短路顺序；不会为了条件覆盖改变顺序。
- 编辑的A/B/C/D使用最终有效内容与保留/替换后的媒体；保留媒体使用已经存储的元数据，不能把“本次无文件”判为纯文字。
- 评论：身份→作品存在/可见→评论；评分：身份→作品存在/可见→分数范围→自评。移除：Session→role→CSRF→存在→状态→修改；CSRF属请求来源安全校验，不修改资源的业务顺序。
- 数据库唯一冲突：注册重名1006，评分在锁内更新而非制造重复；其他约束冲突和锁等待失败409/1005且回滚。文件读写/移动失败500/1016。未知程序异常属于必须修复的缺陷，不把它伪装成成功、参数错误或文件错误。

## 5. 认证、安全与媒体边界

### 5.1 Token与管理员Session

- 密码采用Werkzeug PBKDF2-HMAC-SHA256，600000轮、每次独立随机盐；校验调用哈希验证函数，不自行比较明文。测试可配置较低轮数，但实际Gm/验收须另验证默认参数，不能据低轮测试推断生产耗时。
- 小程序Token用itsdangerous时间戳签名，独立salt；负载仅uid、token_version；max_age=604800秒，并在满期限时拒绝（边界不接受第604800秒）。每个受限请求在当前事务中查User，只有active、普通角色且版本相等可用。
- 退出/改密在同一写事务中递增token_version。客户端401清Token和用户信息；重启调用/api/auth/me确认后才恢复受限页，不能仅凭本地有字符串视为登录。
- 管理端使用Flask签名Cookie加单进程内随机sid注册表；注册表保存uid、签发时间、绝对到期时间，30分钟到期，不滑动续期。Cookie为HttpOnly、SameSite=Lax；本机HTTP不设Secure，HTTPS环境设Secure。不在Cookie中放密码或小程序Token。
- 登录成功轮换sid和CSRF值，登出删除当前sid并清Cookie；服务重启丢弃注册表，原Cookie不能恢复管理会话。两个管理会话各自登出不撤销另一个，且不能复用小程序Token。
- CSRF使用secrets随机值与constant-time比对，包含登录、退出、禁用、移除表单；服务端不接受仅靠隐藏按钮或浏览器确认实现保护。
- 启动密钥来自环境或instance内随机生成的本地密钥文件，不写入源代码/日志。测试使用隔离密钥，实例文件不提交或随交付源码打包。
- 日志只记录请求ID、路由模板、HTTP/业务码、耗时，不记录Authorization、Cookie、表单正文、密码、完整Token或上传原文件名；关闭debug及浏览器错误页中的堆栈。Jinja默认转义，用户内容只用原生text/textarea，不用rich-text或HTML注入。

### 5.2 上传与数据库的一致性

1. 每次写命令获取同一进程RLock（最多等5秒，超时409/1005），再进入一个SQLAlchemy事务；身份、归属和状态在锁内重查，不沿用锁外对象快照。ORM隐式查询也必须位于该事务，避免先查询后begin的嵌套冲突。
2. SQLite启用WAL、busy_timeout=5000ms。所有应用写入口（注册、登录锁计数、撤销、作品、互动、管理、初始化）使用同一写门；读请求只进行短事务，结束即释放连接，不在数据库事务中播放视频。
3. 文件流读入服务端临时目录，每个文件边读取边累计大小，超过单文件上限立即失败；后缀与请求MIME、实际文件头/容器标识一致才接受。PNG/JPEG须有相应结构与结束标记，MP4须有有效ftyp及可界定的容器结构；不以扩展名或Content-Type单独判断，不引入转码/图片解码依赖。
4. 临时与最终目录均在instance/media下，生成UUID十六进制文件键加规范后缀；绝不拼接原文件名或客户端目录。服务端使用数据库键和规范化路径确认仍位于媒体根下，再读写。
5. 所有输入校验通过后才创建Work/Tag/WorkTag/Media并flush。新文件从tmp原子移动到最终目录；所有移动成功后提交一次数据库事务。编辑把旧Media标inactive与新关联放同一事务，旧文件不删除。
6. 在提交前失败：回滚所有实体及关联，删除本请求新建的暂存文件和已移动的新文件；不能删除之前已提交或旧版本文件。若清理本请求文件失败，记不含用户内容的维护错误，文件无已提交关联而不可访问。
7. 进程在文件移动后、DB提交前崩溃会残留孤立文件；重新启动先按已提交Media.file_key建立引用集，清理tmp及未引用的新文件。所有历史Media行（包括inactive和removed作品）均保留在引用集，绝不以不可见为理由删除其文件。启动清理发生在开始接收请求之前。
8. 数据库提交后响应丢失，作品仍已成功保存，客户端不可自动再次发布。客户端可从“我的作品”核对后决定；本期没有幂等键或重复正文去重语义。

媒体读取先查Media.active、作品及作者，再构造send_file响应；Cache-Control:no-store，响应重新读取不可见状态后不返回字节，避免未来请求继续用服务器缓存。Range/HEAD同样鉴权；已开始传输的响应不承诺追溯撤回，设备离线缓存不承诺擦除。

### 5.3 并发语义

- 同账号同名注册由唯一约束保证只有一条成功；不同大小写名称不合并。
- 并发评分在写门内查唯一记录后更新，只保留一人一条；读取统计的sum/count来自同一快照。
- 两次编辑按获得写门的先后顺序执行，后提交者覆盖自己提交的字段，未提交字段读取锁内最新值；不增加版本冲突弹窗或合并编辑功能。
- 编辑与移除竞争：编辑先提交则移除之后隐藏新版本；移除先提交则后来的编辑返回409/1005，不恢复作品。
- 禁用与发布/互动竞争：每次命令在同一写门内重查身份；禁用先提交则旧Token401/1002，发布先提交则随后禁用覆盖其全部作品为removed。
- 状态一致性按已提交写操作后的新请求判断；不靠通知推送、客户端本地删列表或隐藏按钮维护真实状态。

## 6. 小程序与后台实现契约

- TypeScript源文件与WXML/WXSS/JSON放原生工程，tsc生成微信可执行CommonJS JavaScript，不生成网页替代品。S4确定编译入口；ESLint覆盖所有生成的业务JS及手写JS，TypeScript检查源文件，核心测试读取同一编译产物。不以仅扫描一个空目录通过Gm。
- 微信wx.uploadFile一次只能上传一个文件；多媒体发布采用wx.request的multipart ArrayBuffer，使用文件系统读取已选文件，按HTTP multipart边界拼接一次请求。≤9张/90MiB加封装会增加客户端峰值内存，这是需实测的后果；不私自把9张改成逐张独立作品或提前提交半成品。
- 媒体请求超时60秒，普通读/写15秒；超时阈值不替代2秒/5秒性能判据。系统文件选择和播放用原生API，上传进度至少有“读取/上传中/完成/失败”状态，不伪造百分比。
- 首页筛选使用请求代次；切换条件后旧响应即使晚到也丢弃。每代同页只有一个在途请求，页码在成功后推进，按ID去重；返回首页保留条件但从第1页重新请求当前状态。
- P04仅内存保留未提交表单；退出确认不生成持久草稿。密码/Token不进入普通本地草稿；认证存储专用键，退出清理；来源只允许P01—P06内的已知页面与合法作品ID。
- 后台Jinja2表单提交后成功303重定向再GET，失败保留非密码值和错误状态；少量同源JS只做确认、loading与表单错误恢复，不接入SPA依赖。无JS时服务器权限/CSRF仍生效；交付UI必须有取消危险操作的能力。
- 配置将API_BASE_URL留给本机开发者工具/已获准局域网环境；不把127.0.0.1当真机可访问服务器，不将微信不校验域名的开发模式描述为正式真机环境。

## 7. 五类失败与可观察行为

| 类别 | 场景 | 服务端与客户端行为 |
|---|---|---|
| 空 | 首页/日期/标签没有结果、超过末页 | 200空list与正确total；明确空态/停止加载；无评论/评分用各自文案 |
| 空 | 发布正文/媒体均空，或编辑最终均空 | 400/1011，表单保留，不创建Work或关联 |
| 错 | 非法日期/分页/标签、超长内容、图视频混合/伪类型 | 按§4.4返回指定400业务码；具体非法图片在message中用文件序号指出；无副作用 |
| 错 | DB唯一/约束冲突 | 重名400/1006，其他409/1005；事务回滚，新文件按§5.2撤销；不返回半成品 |
| 错 | 磁盘写入/移动失败 | 500/1016；旧编辑版本仍可见，发布无半成品；保留表单与可重试提示 |
| 错 | 媒体行存在但文件缺失 | 404/1004，不泄露磁盘路径；页面显示媒体失败/重试，不把缺文件变空白成功 |
| 超时 | 读/写网络超过15秒，媒体上传超过60秒 | 请求结束loading，保留输入；写结果未知不自动重试，先重新查询；已提交数据不因断线撤销 |
| 超时 | 管理锁5分钟/Session30分钟/Token7天 | 锁定409/1005；无效Session写401/2001、页面重定向；小程序401/1002并清本地，分别按两端导航规则重登 |
| 并发 | 同名注册、重复评分、并发编辑、删除与编辑、禁用与发布 | 全部写门串行、DB约束兜底，行为按§5.3；锁等5秒失败409/1005，不悄悄重试 |
| 并发 | 筛选改变、旧响应后到、触底重复事件 | 请求代次+在途页去重，旧响应不覆盖新筛选；失败页不推进页码 |
| 权限 | 游客、伪user_id、他人作品、admin小程序写、disabled旧Token | 身份与归属来自服务端当前事务，按1002/1003拒绝；伪造字段不能提权 |
| 权限 | 直接媒体URL、后台越权/CSRF、路径穿越 | 状态查询与根目录限制先于文件读取；后台角色/CSRF拒绝；不靠UI隐藏入口 |

未捕获程序缺陷不得用“文件失败”或“参数错误”掩盖；S5/S6发现后保留失败并修复。异常堆栈仅在隔离测试证据中保留，脱敏后再交付；应用响应不展示内部堆栈。

## 8. ADR式关键取舍

状态：既有技术选择沿用，契约细化已获独立G3确认（Accepted）。决定依据为SPEC §5.1授权S3冻结表示与协议，不增加业务范围；生产者Qoder，检查人为未参与生产的独立general-purpose上下文。

| ADR | 选定 / 放弃 | 维度比较与理由 | 后果与重看条件 |
|---|---|---|---|
| ADR-01 交付与渲染 | 原生微信+Jinja2单体 / H5替代或SPA | 原生为既有交付约束；Jinja2复用Python栈和已有表单，新增SPA会增加构建/认证边界 | 两套UI需分别验收；浏览器不能证明微信。只有新范围批准才讨论客户端替换 |
| ADR-02 存储与并发 | SQLite单进程写门 / PostgreSQL或多进程 | ≤20客户端与课程体量，不需新数据库服务；写门让禁用、发布与文件补偿具有单一顺序 | 写入排队、无横向扩展；超过现有并发或启多进程须重新G3，不能直接开多worker |
| ADR-03 媒体 | 本地受控目录+DB关联 / 静态直链或对象存储 | 复用既有本地存储；每次访问能检查removed/disabled，静态直链无法撤销 | 需要Range与文件补偿；历史文件占空间。公网/多机媒体需求须新授权，不改静态绕过 |
| ADR-04 认证 | 7天签名Token+DB版本、独立30分钟Session / 仅本地退出或共用Token | 旧版本整体撤销及后台独立登录均来自SPEC；使用Flask已带依赖，无新认证库 | 每次受限请求查DB，服务重启后台重登；多进程需共享Session存储，当前不引入 |
| ADR-05 上传原子性 | 单次multipart+文件补偿 / 分文件暂存上传API | 现有发布调用链就是multipart；一次业务写事务，不新增公开上传票据协议 | 微信端需要组装ArrayBuffer，有内存峰值和耗时风险；S6必须真机实测，失败不能降低原规格 |
| ADR-06 统计与查询 | SQL关联/聚合实时计算 / 冗余计数或缓存 | 200作品/1000评分规模可直接查；避免评分更新或禁用后缓存失效分歧 | 需批量关联避免N+1；增长后以实测决定索引/聚合调整，不能凭猜测加缓存服务 |
| ADR-07 文件版本 | 旧Media inactive并保留文件 / 删除旧文件或仍公开旧URL | 整体替换后旧内容不应通过旧入口继续访问，保留行能区分历史与崩溃孤立文件 | 占磁盘但可追溯；没有媒体清理产品能力，不把启动孤立清理用于历史文件 |

能力、成本、熟悉度边界：均使用来源既定工具，免费项目内运行；未假设用户掌握另一套平台。新的性能数字、真实设备能力与依赖版本在执行前记录，不能编造“熟悉”或“已达标”。

## 9. 规模、初始化与可恢复性

- 小程序/后台只请求当前页。作品列表一次取本页作品，批量取作者/首图/评分聚合，不按卡片逐条发SQL；标签用集合查询。评论每页20，后台/作品每页10，上限20。
- 默认初始化命令在S5形成：唯一admin、active student_a/student_b、disabled student_c；5作品及校运会/演示标签。用户名和固定种子标识用于重复执行去重，已存在记录不重置密码或用户编辑内容，不把重复init当恢复数据库。
- 默认种子只用虚构内容；性能样本另建隔离数据库和媒体目录，不覆盖默认演示库。测试配置、fixture目录和密钥隔离，不向真实账号发请求。
- 密码由初始化配置输入，程序不打印密码/哈希；演示说明只描述设置入口，不将机密混入日志或证据。清库、重置用户或覆盖实例不自动执行。
- 不承诺高可用或自动跨机容灾。SQLite文件在服务停止后连同已提交media与密钥作本地备份；备份/还原须用户明确要求，不能自动覆盖实例。磁盘/进程故障返回失败或连接中断，启动孤立清理见§5.2。
- 性能上传可能需要90MiB缓冲及复制；目前无内存与时限实测。记录这项风险而非伪造结果；若真机达不到已冻结标准，回到设计/用户裁决，不把API时间替代首屏或以模拟wx通过。

## 10. 图解与下游动作

```text
原生微信P01—P06 ── JSON/Bearer + multipart ─┐
                                           ├─ Flask Blueprints
管理浏览器P07—P09 ── HTML/Session + CSRF ──┘      │
                                            Services
                                Auth / Work / Media / Interaction / Admin
                                              │             │
                                    SQLAlchemy + 写门     MediaService
                                              │             │
                                            SQLite      instance/media
                                              └─ 状态查询 ──┘
```

[独立HTML架构设计图](.archify/architecture-campus-album-20261120-011526/campus-album.html)已由本地archify生成；最终候选与review-2自动检查回执保留，validate/deliver/check/browser-check均通过。核对时修正图中Admin误写“复用公开查询谓词”，现为管理查询保留removed、不套公开过滤。最新版本只声明自动图检查通过，不用旧截图证明新文件的目视质量，也不能冒充应用Gm或微信验收。

- [x] 独立G3核对两输入、取舍后果、职责排除、接口校验归属、空/错/超时/并发/权限；架构0.1六项均通过，无阻断修正。
- 实施提醒（不新增需求）：Python3.12的SQLite默认legacy事务不能仅靠Session.begin保证SELECT快照，S5用显式BEGIN配置落实本文短事务；极大整数ID/页码避免SQLite绑定及OFFSET溢出，超末页仍空；Token到期边界须显式验证满604800秒拒绝；微信ArrayBuffer90MiB及5秒仍需实测。
- [x] S4已按31R/157AC形成30任务并通过G4；安排了微信/浏览器环境、缺陷分级、性能样本与16组合/真实路径，实际执行仍由PLAN逐项记录。
- [ ] S5冻结依赖版本、初始化命令及双端lint/typecheck/test；实现时不临时换栈或新增业务码。
- [ ] S6真实后台浏览器、微信工具/真机、性能、兼容与T/E；未执行不得改为通过。

Q-S02的ROUND_HALF_UP/null、Q-S03的锁定409/1005及30分钟Session、Q-S06的inactive旧媒体和文件补偿、Q-S07的路由/字段/标签编码/编辑省略/复合失败顺序已在本稿给出；这些契约已获独立G3确认，不代表业务实测。Q-S09/Q-S10环境与缺陷分级留S4—S6。
