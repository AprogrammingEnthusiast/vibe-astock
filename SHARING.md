# 共享投研与个人账号

同一个网站入口：完成的市场复盘和个股深挖供所有已登录成员阅读；AI 对话、自选、盯盘、持仓、交易日志、个人验证条件和模型凭证按账号隔离。阅读共享结果不会执行 AI。生成复盘、深挖和追问使用发起者的配置，没有配置时直接报错。

一套应用进程服务所有账号，服务端登录会话决定账号上下文。个人文件、模型运行目录和内存任务状态按账号隔离；浏览器传来的用户编号、访问密钥不能改变归属。公共市场分析产物进入共享数据库，按作者和内容保留版本。

账号数据库沿用 `vibe-astock-accounts` 卷中的 `accounts.sqlite3`，本人 HOME 位于同卷的 `homes/<账号ID>`。容器不挂载 Docker socket，也不继承项目 `.env` 中的凭证。账号空间由站点服务器托管，管理员仍有管理文件的能力；应用隔离不等于独立操作系统容器。Codex 设备登录和订阅是否可用受账户权限影响。

以下是后续部署操作说明；修改代码或运行测试不会自动迁移、更新线上服务。

## 部署（在项目根目录运行）

```powershell
docker build -t vibe-astock-shared:local .
docker volume create vibe-astock-accounts
docker run --rm --user root -v vibe-astock-accounts:/home/app/sharing vibe-astock-shared:local chown 1000:1000 /home/app/sharing
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "${PWD}:/app" vibe-astock-shared:local python sharing_admin.py add-user owner --owner
docker compose -f .sharing/compose.json up -d
```

默认监听 `127.0.0.1:8910`，供现有 HTTPS 反向代理或隧道使用；反向代理必须保留原始 Host。Cookie 默认 Secure、HttpOnly、SameSite=Strict。纯本机 HTTP 测试时，生成配置可加 `--port 18910 --local-http`，正式 HTTPS 部署移除 `--local-http`。

管理员邀请写入 `.sharing/owner-invite.txt`。在网站选择“首次使用”，输入账号、一次性邀请码并设置自己的密码。不要把管理员邀请发给朋友。

生成的配置只有一个 `gateway` 服务，启用 `VIBE_SHARED_APP=1`，挂载账号卷及临时公共行情缓存。整个 `.sharing` 包含邀请等敏感资料，已从 Git 和 Docker 构建上下文排除，不要分享此目录。

## 添加朋友

管理员登录后，点击左下角亮度旁的「设置」，进入「邀请成员」，输入朋友的网站账号并生成邀请码，再点击「复制邀请」交给对应朋友。页面显示成员激活状态；普通成员无法访问邀请接口。邀请码仅显示一次，激活后失效。

邀请直接创建账号，无需预分配名额、启动新容器或重启应用。旧 `add-slots` 操作已取消；数据库中旧名额记录仅保留兼容，不再限制邀请。

把 `friend01` 换成朋友的网站账号（3–32 位小写字母、数字、下划线、短横线，字母开头）：

```powershell
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "${PWD}:/app" vibe-astock-shared:local python sharing_admin.py add-user friend01
```

把网站链接和 `.sharing/friend01-invite.txt` 中的邀请交给对应朋友。朋友激活网站账户后可直接阅读公共复盘；需要 AI 时在“接入 AI”授权自己的 Codex，或填写自己的 API Key 并保存。后台复盘也使用这里保存的配置。

每次生成配置都明确使用同一端口和 HTTPS/本机 HTTP 模式；命令默认回到正式配置 `8910 + Secure Cookie`。

## 原有数据迁移

迁移前停止新旧应用及后台写入，备份原账号卷与每个旧账号数据卷。沿用原 `vibe-astock-accounts`，不要重新创建已有账号；数据库中的账号 ID、密码、会话和公共版本保留，旧 worker 字段不再用于路由。

先根据旧 `.sharing/compose.json` 核对账号与 `vibe-astock-shared-<账号ID>` 卷的一一对应关系。对每个已有账号，将其旧 HOME 卷只读挂载到 `/legacy`，显式执行以下命令；将占位符替换为该账号的真实卷名和网站账号，不能把 owner 数据复制给朋友：

```powershell
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "旧账号卷名:/legacy:ro" vibe-astock-shared:local python sharing_admin.py import-home 网站账号 --source /legacy
```

命令复制完整旧 HOME（包括 `.duanxian-agents`、`.vibe-research`、`.vibe-astock-agent` 和 `.codex` 等现有数据），不读取或打印凭证内容，不修改源卷。目标固定为该已有账号的 `homes/<账号ID>`；源必须为普通目录且不能包含符号链接、目录联接或特殊文件，目标已有则拒绝覆盖或合并。复制先在账号卷内暂存，成功校验后才重命名为目标目录；失败不会留下半份可用账号空间。新应用一旦为账号创建目录便不能直接导入，请在首次启动新应用前完成迁移。

全部导入并核对后，再生成单应用配置并启动；沿用已确认的端口和 Cookie 模式：

```powershell
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "${PWD}:/app" vibe-astock-shared:local python sharing_admin.py render
docker compose -f .sharing/compose.json up -d --remove-orphans
```

旧容器可移除，但旧数据卷继续保留，禁止 `down -v` 或清理卷。上线后核对原账号登录、公共版本和各账号私有记录；保留备份直到迁移确认。新公共产物先写本人磁盘，再发布到共享数据库；发布失败保留待发送文件并重试。

浏览器里的旧自选和研究记录：用 owner 登录，在“接入 AI”点击“导入原有浏览器自选和记录”。只有管理员能看到此入口；普通朋友不会自动接收旧浏览器数据。旧的浏览器 API Key 不会自动分配给任何新账号，请在本人账号重新保存。

## 退出、恢复与备份

- “退出网站账号”撤销当前网站会话；不影响其他人的会话或正在执行的任务。
- 左下角「退出登录」与设置页的退出操作相同；侧栏收起时仍保留退出图标。
- “断开我的 Codex”清除本人账号空间的订阅登录和模型配置；后台复盘或深挖未结束时拒绝断开。
- Codex 首次连接或重连成功后自动弹出模型选择，选择模型并点「保存并完成连接」；暂未读到模型目录时可以重试获取或保存 CLI 默认模型。
- 忘记网站密码：运行上述管理命令，将 `add-user` 改为 `reset-invite`；该用户旧会话立即失效，新邀请码用于重新设置密码。
- 停用账号：将 `add-user` 改为 `disable`，无需重启；保留其账号空间，公共历史版本保留作者。
- 备份 `vibe-astock-accounts` 卷（含数据库与所有 `homes`），并保留迁移前的旧账号卷，备份同样包含敏感凭证，应限制访问。
- 更新：重新构建镜像，再对 `.sharing/compose.json` 执行 `up -d`。原 `compose.yaml` 仍是单用户模式，不应作为共享网站入口重新启动。

## 验证

```powershell
docker run --rm --init --network none -e VIBE_ACCOUNTS_DB=/tmp/test-accounts.sqlite3 -v "${PWD}:/app:ro" vibe-astock-shared:local python -m pytest tests/test_sharing.py tests/test_single_instance.py tests/test_sharing_admin.py tests/test_codex_device_auth.py tests/test_cli_model_selection.py -q -p no:cacheprovider
node frontend/tests/codex-reconnect.mjs
```

检查身份伪造、跨账号自选访问、CSRF、邀请复用、退出撤销、密码限流、同进程账号上下文隔离、流式响应、公共版本共享、无凭证拒绝调用和发布失败重试。测试使用假凭证，不消耗真实订阅额度。

## 合并上游新版后的升级说明

新版首页、复盘、深挖和问答统一使用「AI 接入」的连接测试与保存流程。网站登录、成员邀请与公共复盘继续保留；新版连接配置按网站账号保存在本人账号空间，浏览器恢复记录同样按账号隔离。旧 API 配置保留原件，需在新版接入页重新测试保存。

升级会将本人账号空间已有的 Codex 登录复制到本人的新版运行目录（旧文件保留）；新旧登录都在该账号的 HOME 目录内。点击「断开我的 Codex」会撤销这两份本地登录，进行中的任务会阻止断开。新授权使用新版的官方登录页面，成功后选择模型并测试保存。

共享部署保持原 VR_DATA_DIR（默认 ~/.vibe-research），个人记录不会因上游默认目录变化而隐藏；新 Agent 数据位于本人 HOME 的 ~/.vibe-astock-agent。两处都应纳入备份。镜像增加上游 runtime、review_agent、backtest 和 research_data，仍使用原 .sharing/compose.json 更新，禁止删除数据卷。

共享部署的新版 Codex 登录使用设备码授权：点击「登录 ChatGPT」后，在官方页面输入网站显示的一次性验证码，无需访问 localhost:1455。授权成功后回到设置选择模型并测试保存；失败或取消不会替换原有登录。
