# 开发、验证与运行

文中代码路径以仓库根目录为基准。

## 代码导航

- 启动、配置、产品口径：先读 `README.md` 对应章节；依赖与脚本以 `requirements.txt`、`frontend/package.json` 为准。
- Web 复盘与深挖：入口 `server.py`；CLI 入口 `main.py`；数据、指标、复盘图和保存逻辑在 `duanxian/`，单股分析在 `duanxian/deepdive/`。
- 行情、资讯、盯盘和对话：读 `vr/app.py` 及对应模块。`server.py` 将 VR 的 `/api/*` 路由并入同一服务；保留现有导入方式，避免破坏从上游同步的结构。
- 前端：从 `frontend/src/router.tsx` 找页面；请求和状态逻辑在 `frontend/src/lib/`，复用组件在 `frontend/src/components/`。
- 共享账号、邀请、凭证、部署或迁移：先读 `SHARING.md`；网关 `sharing.py`、管理 `sharing_admin.py`、实例同步 `sharing_worker.py`、公共字段白名单 `sharing_schema.py`。
- 新版网页 AI：`review_agent/api.py` 管理任务，`review_agent/runtime.py` 运行隔离模型，`frontend/src/lib/agent-api.ts` 保存本人连接；共享适配见 `sharing_worker.py`。
- 旧版 CLI 模型接入：复盘走 `duanxian/config.py`、`duanxian/cli_llm.py`；对话与 CLI 运行时看 `vr/chat.py`、`vr/cli_runtime.py`。修改模型选择或凭证处理时检查两条调用链。

## 修改与验证

- 开始修改前查看 `git status --short`，保留已有未提交工作；沿入口读到实现，并搜索所有调用方，再在公共路径修复根因。优先复用已有函数、标准库和已安装依赖。
- Python 文件保留原有换行与 UTF-8 编码。接口改动同步检查前端类型、请求、流事件和错误展示。
- 后端逻辑改动运行相关 `tests/test_*.py`；新增分支或修复回归时补最小可运行用例。`tests/conftest.py` 禁止出站网络，数据源、交易日与 CLI 使用替身，测试文件写入临时目录。
- 前端改动运行构建；涉及交互时检查对应页面的成功、空数据和错误状态。纯文档修改核对路径、命令和 diff 即可。
- 接口改动验证请求字段、响应类型、HTTP/流内错误与前端显示能对上；数据展示改动覆盖 null、0、负数、非有限值、单位和历史日期，不能只检查页面能渲染。
- 长任务或状态切换改动验证重复点击、旧请求晚返回、切换日期/股票、卸载清理、失败后重试；账号相关改动额外验证跨账号访问和退出撤销。
- UI 改动在浏览器检查明暗主题、窄屏、键盘操作和浏览器错误；图表检查空集、仅单一方向及布局变化。构建通过不能替代交互验证；无法完成必要检查时报告阻塞，不能视为测试通过。
- 当前前端 package.json 没有 lint/test 脚本；使用已有构建与 `frontend/tests/*.mjs` 检查，不虚构命令或为普通改动添加测试框架。需要新回归检查时沿用现有 Python pytest 或 Node assert。
- 按 [AGENTS.md 的约束条件](../AGENTS.md#约束条件) 执行完成门槛。交付时说明变更、实际测试结果、部署目标和部署后验证结果；受阻时说明未完成项，测试数量与通过状态以当次输出为准。

常用命令（从仓库根目录运行，`python` 指已安装项目依赖的解释器；Windows 虚拟环境通常为 `.venv\Scripts\python.exe`）：

```powershell
python -m pytest tests backtest/tests research_data/tests -q
node --test frontend/test/*.test.ts
npm --prefix frontend run build
node frontend/tests/codex-reconnect.mjs
node frontend/tests/sector-flow.mjs
```

上游 Node 测试覆盖新版网页逻辑；两个额外 Node 检查分别用于新版 Codex 重连与本人配置保存、板块资金图，按改动范围选择。共享账号、登录或模型配置变更至少覆盖 `tests/test_sharing.py`、`tests/test_codex_device_auth.py`、`tests/test_cli_model_selection.py`。

单用户启动用 `python server.py`（后端默认 8910，服务 `frontend/dist`）；开发前端用 `npm --prefix frontend run dev`（默认 5910，代理至 `127.0.0.1:8910`）。共享部署按 `SHARING.md` 使用生成的 `.sharing/compose.json`；根目录 `compose.yaml` 是单用户模式。

## 更新部署

- 测试通过后，按已确认的部署目标和现有部署方式更新服务；共享部署的操作步骤见 [SHARING.md](../SHARING.md)。
- 部署后检查服务健康、启动日志及本次改动涉及的关键流程，确认运行的是本次更新的版本。失败则排查修复，并重新执行受影响的测试与部署验证。
