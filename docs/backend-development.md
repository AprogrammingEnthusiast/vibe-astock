# 后端设计与开发规范

文中路径以仓库根目录为基准；仅文件名或局部路径按所在段落说明解析。通用协作规则及其他任务文档入口见 [AGENTS.md](../AGENTS.md)。

后端使用本地文件持久化；共享账号网关使用 SQLite。

## 分层与任务编排

- 路由负责请求校验、权限、任务启动和响应；取数、计算、存储放在对应业务模块。复盘数据链路是 `fetchers.py` 取数 → `data.py` 缓存、降级与文本化 → 指标/分析师 → 裁判 → `review_store.py` 序列化与保存，避免在路由和前端重复实现指标公式。上述文件均位于 `duanxian/`。
- 每日复盘由 `duanxian/roles.py` 的 `ROLES` 注册表驱动，五个分析师目前串行进入裁判。新增角色同步检查注册表、`duanxian/state.py`、`main.py` 初始状态、序列化和前端展示；稳定 key 与展示标题分开。
- 个股深挖由 `duanxian/deepdive/graph.py` 编排：四分析师串行 → 正反方辩论 → 裁判；共享一次行情快照。节点返回各自状态字段，辩论轮数复用 `duanxian/debate.py` 的路由。调整并发前核对状态依赖和模型限流。
- 新版 Web 复盘、深挖和页面问答使用 `review_agent/api.py` 的启动接口及状态轮询，旧 CLI 入口仍保留。复用 `review_agent/` 的锁、幂等任务编号、取消及超时机制：启动检查与状态更新必须原子化，旧任务的收尾只能修改自己的 job_id；失败必须释放运行状态并保留错误。
- 阻塞取数、文件操作和同步模型调用沿用同步路由/工作线程；写 `async def` 时将阻塞操作移到线程或使用异步客户端。后台启动与清理由 FastAPI lifespan 管理，不能只写在 `__main__`，否则通过 uvicorn 导入时不会执行。

## 接口、数据源与存储

- API 保持 `/api/*`，新增路由声明在 SPA 兜底之前；不存在的 API 返回 JSON 404。VR 合并只复制路由，不自动继承其应用中间件；改鉴权时检查 `server.py` 的 `_vr_guard` 和 `sharing_worker.install()`，不能只改 `vr/app.py`。
- 请求边界沿用 Pydantic 模型或明确校验：股票代码用六位字符串保留前导零，日期用 `validate_trade_date()`，文件名用 `safe_join()`，数值校验类型、有限性与业务范围。更新接口区分“字段未传”和“显式清空”；表单字段要一路透传到存储。
- 保持各接口已有响应结构，不能全局套新 envelope。`vr/app.py` 常用 `detail`，复盘接口常用 `error`；调用端须处理对应错误。输入错误、未授权、任务冲突与内部失败使用相应非 2xx 状态；可恢复的数据缺失用现有 `available/reason` 或 `warnings` 明示，HTTP 200 不等于数据可用。
- 新版页面问答通过 `/api/review-agent/chat-jobs` 启动与轮询，所有页面使用本人 `agent-api.ts` 连接。旧 VR `/api/chat` 是 `application/x-ndjson`，每行一个 `tool/delta/done/error` 事件；配置错误在开流前返回 HTTP 错误，运行中失败用流内 error。协议修改同步 `vr/app.py`、`vr/chat.py`、`frontend/src/lib/llm.ts`；上游模型的 SSE 不等于浏览器侧协议。
- 数据源请求设置明确超时，复用当前模块的会话、缓存、代理和回退策略。保留交易日、来源、单位和获取时间；实时缓存与历史归档分开。`duanxian/fetchers.py` 先加载配置再决定代理，不能为修一条行情请求擅自修改整个进程的代理环境。
- JSON 写盘优先复用 `duanxian/util.py` 的 `atomic_write_json()`；用户数据必须检查其返回值，失败不能报保存成功。读—改—写的整个过程加锁，原子替换本身不能防止并发丢更新；参照 `duanxian/journal.py`。
- 当前持仓由 `duanxian/positions.py` 聚合交易日志 fills，账本是唯一来源，不新增另一份持仓存储。账本、持仓和风险统计不接入 AI prompt。
