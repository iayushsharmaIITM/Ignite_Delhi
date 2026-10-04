# 接口梳理：`POST /api/chats`（会话持久化 / 全量重写 turns）

> 由 `api-logic-analysis` 技能产出。所有末端事实（表名、端口、地址、行号）均在本次
> 分析中重新在代码/配置里核对，未引用任何历史文档结论。
> **与技能模板的一处刻意偏离**：代码引用使用仓库相对路径 + 行号（如 `app.py:627`）而非
> `file:///绝对路径`，因为该仓库的 `AGENTS.md` 与文档卫生检查不允许把个人主目录写进被
> 提交的文档；这是有意选择，不是遗漏。仓库根：`/Users/.../Kestrel_brains`（本机路径不入文档）。

## 一、接口概览

| 项目 | 内容 |
|---|---|
| 路径 | `POST /api/chats`（无类级前缀；`app.py:627`） |
| 入口 | `chats_upsert(request)` — `app.py:628`（`async def`，仅此处 await 请求体） |
| 鉴权 | `require_tenant(request)`（`app.py:243`）：`AUTH_MODE=clerk` 时校验 `Authorization: Bearer <Clerk JWT>`；`AUTH_MODE=off` 时放行（仅限显式指定的测试通道；未设置时默认为 clerk） |
| 数据集授权 | `require_dataset_access(request, brain)`（`app.py:299`）→ 内部走 `brain_allowed`（`app.py:272`） |
| 入参 | 请求体 JSON：`{id, title, turns[], trim?, created?}`；`brain` 取自 query `?brain=` 否则取 body 的 `brain`（`app.py:645`）；隐式入参 = 登录态 `identity.org_id / identity.user_id`（`app.py:643-644`） |
| 返回 | `dict`（`storage.upsert_chat` 原样透出：`{"ok": true, "id": ..., "turns": N}`） |
| body 中的 `org_id` | **被忽略**。SEC-5：归属由服务端盖章，客户端自报的 org 不作为依据（`app.py:641-644`，`storage.py:336-344`） |

## 二、主要功能

把客户端持有的一整段对话写回服务端。语义是**全量重写**：先 `DELETE` 该 chat 的全部
turns，再按数组下标 `idx` 逐条 `INSERT`。因此本接口同时是三条历史保护规则的执法点：
CH-1（不得静默截短）、CH-2（已删除的 id 不得复活）、S1（不得覆写他人 chat）。

分支划分依据：进入 `storage.upsert_chat` 之前全是**入参与授权校验**；之后是**事务内的
四条守卫 + 重写**。

## 三、业务逻辑

### 3.1 入口层校验（`app.py:629-670`，无独立业务编排层）

FastAPI handler 直接调用 `storage` 模块函数，本仓库**没有** Service/Biz 中间层；
`app.py` 就是编排层。顺序与短路点：

| 顺序 | 行 | 检查 | 不通过 |
|---|---|---|---|
| 1 | 629 | `require_tenant` 鉴权 | 401（在 `auth`/`require_tenant` 内） |
| 2 | 632-636 | body 必须是合法 JSON 且为对象 | 400 |
| 3 | 637-638 | `id` 必填 | 422 |
| 4 | 639-640 | `storage.available()` | 503 |
| 5 | 645 | `safe_dataset()` 归一化 brain 名（`app.py:343`） | 400/404 |
| 6 | 650 | CH-6：**把 chat 归档到某个 brain 本身就是一次 brain 访问** | 403 |
| 7 | 653-661 | `turns` 必须是 list、每项必须是 object，且 `len ≤ MAX_TURNS` | 422 / 413 |
| 8 | 663-669 | CH-9：单条 `text ≤ 100_000`；`sources/attachments/steps` 序列化后各 `≤ 500_000` | 413 |

CH-6 的存在理由（`app.py:646-649` 注释）：此前该路由只盖章不做门禁，租户可以把会话
塞进别人的 brain 里，归属记录从此就是错的。

### 3.2 存储层事务（`storage.py:264-391`，单连接单事务，非 autocommit）

进入时先在**同一事务**里按顺序执行，任何一条命中即抛自定义异常、整体回滚：

| 步 | 行 | 语句/动作 | 作用 |
|---|---|---|---|
| a | 285-289 | `from memory_layer import _is_smalltalk, _is_social_reply`；对 `role=="bot"` 且命中的 turn 置 `sources=[]` | 寒暄/问候回复不携带文档依据，存下来的引用按定义是陈旧的。二者均为本地正则/词数判断（`memory_layer.py:93-97`、`memory_layer.py:240-246`），**不产生远程调用** |
| b | 297 | `psycopg.connect(...)`，不使用模块级 autocommit helper（`storage.py:116`） | SEC-10：中途崩溃必须回滚到旧 turns，而不是提交出空会话 |
| c | 312-314 | `SELECT org_id, created_by FROM chats WHERE id=%s **FOR UPDATE**` | 行锁是后面两条守卫成立的前提：CH-1/CH-2 是"先读后写"，READ COMMITTED 下没有锁就能被并发 delete/save 插进中间 |
| d | 315-319 | 已存在且归属不匹配 → `OwnershipError` | S1：知道 id ≠ 拥有它；legacy 双 NULL 行先到先得 |
| e | 324-326 | `SELECT 1 FROM deleted_chats WHERE id=%s` → `ResurrectError` | CH-2 墓碑 |
| f | 330-334 | `SELECT count(*) FROM turns` 与 `len(turns)` 比较，变短且未声明 `trim` → `TruncationError` | CH-1 防截断 |
| g | 336-344 | `INSERT INTO chats ... ON CONFLICT (id) DO UPDATE SET title/updated/brain, org_id=COALESCE(...)` | 首次盖章 org/creator，之后不被降级覆盖 |
| h | 346 | `DELETE FROM turns WHERE chat_id=%s` | 全量重写的删 |
| i | 349-373 | 逐条 `INSERT INTO turns (chat_id, idx, role, text, sources, attachments, at, steps, worked_ms, stopped, error)` | `idx` 即顺序；`json.dumps` 落 jsonb 列；`_ts()`/`_ms()` 归一化时间戳 |

事务在 `with conn` 退出时提交；`finally` 关闭连接。返回 `{"ok": True, "id", "turns"}`。

### 3.3 异常 → HTTP 契约（`app.py:672-696`）

`OwnershipError`→404（与"不存在"不可区分，避免探测他人 id）；`TruncationError`→409（并在
detail 中告知 `trim=true` 的出路）；`ResurrectError`→410 Gone（客户端必须换新 id，
React 侧照做）；`storage.db_error`（= `psycopg.Error`，`storage.py:84`）→ 先
`mark_down()` 标记存储降级（`storage.py:87`）再 503。

## 四、涉及存储

连接串来源：`storage.py:36-37` 读取环境变量 `DATABASE_URL`，默认值指向
`localhost:5433/kestrel`（凭据不在此记录）。当前 `.env` 同样使用 5433 上的 `kestrel` 库。

| 库/实例.表 | 访问方式 | 用途 |
|---|---|---|
| `kestrel.chats` | `storage.py:312`（`SELECT ... FOR UPDATE`）、`storage.py:336`（`INSERT ... ON CONFLICT DO UPDATE`） | 会话头 + 归属盖章（org_id / created_by / brain / brain_id） |
| `kestrel.turns` | `storage.py:330`（count）、`storage.py:346`（delete）、`storage.py:349`（insert） | 全量重写的消息体 |
| `kestrel.deleted_chats` | `storage.py:324`（读）；写在同文件的删除路径 `delete_chat`（`storage.py:448`）事务内 | CH-2 墓碑；保留 90 天（`storage.py` init 段裁剪） |

未在本接口路径中触达的相邻表：`brain_access`（经 `require_dataset_access` →
`brain_allowed`，`app.py:272` 读取归属做门禁）。

## 五、远程调用接口

本接口路径上只有**一次**可能的跨进程调用，且在鉴权环节、带进程内缓存：

| 类型 | 标识 | 地址（按环境） | 说明 |
|---|---|---|---|
| HTTP GET | Clerk JWKS | 由 `CLERK_JWKS_URL` 给出；未设置时按 issuer 拼为 `https://ample-skink-6708.clerk.accounts.dev/.well-known/jwks.json`（`auth.py:50-52`） | 验签 Bearer JWT；`urllib.request.urlopen(..., timeout=10)`（`auth.py:55-62`）；缓存 TTL 600s（`auth.py:67-73`）。缓存命中时零远程调用 |

无 Cognee / LLM 调用：写会话不触碰 brain，也不做语义缓存（本项目的红线：引用生成路径
上永不语义缓存）。测试态可用注入缝 `_jwks_client` / `inject_jwks_for_test` 完全绕开网络
（`auth.py:16`、`auth.py:81`）。

## 六、缓存与异步消息

| 类型 | Key / Topic | 用途 |
|---|---|---|
| 进程内缓存 | `_JWKS_DATA[url]` + `_JWKS_TS[url]`，TTL 600s（`auth.py:67-73`） | 公钥缓存，避免每次请求打 Clerk |
| 消息 | 无 | 本接口不生产/消费任何消息 |

## 七、上游调用方

- React 客户端：`frontend/src/lib/api.ts` 的 `saveChat(...)`，带 `trim` 标志并按
  `status` 区分 409 / 410（410 换新 id 重存，409 保持本地）。
- 遗留 vanilla 客户端：`static/index.html` 的保存路径（`TURN_CAP=500` + `trim`）。
- 测试：`tests/test_chat_integrity.py`（CH-1..CH-9，写入 `itest-*` 并自清理）、
  `test_auth_isolation.py::test_chat_isolation`（跨 org 不可见 + 墓碑）。
- 无定时任务或消息消费者调用此接口。

## 八、异常处理

- 入口层：`json.JSONDecodeError` 等一律收敛为 400（LOW-6：畸形 JSON 不得变成 500）。
- 业务异常：`OwnershipError` / `TruncationError` / `ResurrectError`（定义于
  `storage.py:49-83`）由 handler 显式映射为 404 / 409 / 410。
- 存储异常：`storage.db_error` → `mark_down()` + 503；`storage.available()` 为假同样 503。
  列表接口 `chats_list` 此前会在存储不可用时返回 200 + 空数组，已统一为 503
  （见 `BUGS_AUDIT.md` Round 3 R3-8）。

---
**小结**

1. **分层差异点（如实记录，不按模板惯例抹平）**：本项目没有独立业务编排层。FastAPI
   handler 即编排层，直接调用 `storage` 的模块级函数；持久化不是 ORM，而是 psycopg3 +
   手写 SQL。因此本接口的"Service 层"信息应到 `app.py:628-696` 查，不存在别的类。
2. **写放大**：一次保存 = 1 次 chat upsert + 1 次全表 delete + N 次 insert（N ≤ 500）。
   当前规模可接受，但如果将来 turns 变长，应改为增量写；这也是 `MAX_TURNS` 与
   `413` 上限存在的原因（`app.py:653-656`，`storage.py:46`）。
3. **并发语义靠行锁兜住**：`FOR UPDATE`（`storage.py:313`）让 CH-1/CH-2 的"先查后写"
   成立；只读路径 `get_chat` 用 `FOR SHARE` 与之对称，避免读到"chat 在、turns 没了"的
   撕裂状态（`BUGS_AUDIT.md` R3-3）。
4. **依赖面很小**：仅鉴权处可能出网一次（且缓存 600s），其余为本地数据库事务——这使
   它成为整个应用中最容易证明正确性的路径，也正是回归测试密集的原因。
