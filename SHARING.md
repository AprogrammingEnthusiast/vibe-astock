# 共享投研与个人账号

同一个网站入口：完成的市场复盘和个股深挖供所有已登录成员阅读；AI 对话、自选、盯盘、持仓、交易日志、个人验证条件和模型凭证按账号隔离。阅读共享结果不会执行 AI。生成复盘、深挖和追问使用发起者的配置，没有配置时直接报错。

每个账号使用独立容器、网络和数据卷。网关通过服务端会话选择实例；浏览器传来的用户编号、后端访问密钥不能改变归属。工作实例不发布端口，不挂载 Docker socket，也不继承项目 `.env` 中的凭证。只有公共市场分析产物进入网关数据库，按作者和内容保留版本。

适合少量受邀朋友。每个闲置实例实际约 120–150 MiB，网关约 45 MiB；分析时会增加。账号配置保存在服务器的私人实例中，服务器管理员仍有管理文件的能力。这个托管方案不是 OpenAI 提供的网站 OAuth 产品；Codex 设备登录和订阅是否可用受账户权限影响。

## 部署（在项目根目录运行）

```powershell
docker build -t vibe-astock-shared:local .
docker volume create vibe-astock-accounts
docker run --rm --user root -v vibe-astock-accounts:/home/app/sharing vibe-astock-shared:local chown 1000:1000 /home/app/sharing
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "${PWD}:/app" vibe-astock-shared:local python sharing_admin.py add-user owner --owner
docker compose -f .sharing/compose.json up -d
```

默认监听 `127.0.0.1:8910`，供现有 HTTPS 反向代理或隧道使用；反向代理必须保留原始 Host，禁止直接发布工作实例端口。Cookie 默认 Secure、HttpOnly、SameSite=Strict。纯本机 HTTP 测试时，生成配置可加 `--port 18910 --local-http`，正式 HTTPS 部署移除 `--local-http`。

管理员邀请写入 `.sharing/owner-invite.txt`。在网站选择“首次使用”，输入账号、一次性邀请码并设置自己的密码。不要把管理员邀请发给朋友。

`.sharing/compose.json` 包含实例之间的内部密钥；整个 `.sharing` 已从 Git 和 Docker 构建上下文排除，不要分享此目录。

## 添加朋友

管理员登录后，点击左下角亮度旁的「设置」，进入「邀请成员」，输入朋友的网站账号并生成邀请码，再点击「复制邀请」交给对应朋友。页面显示剩余名额和成员激活状态；普通成员无法访问邀请接口。邀请码仅显示一次，激活后失效。

网页邀请使用预先启动的独立账号空间，网站本身不持有 Docker 控制权限。首次准备或名额用完后，在服务器补充名额（例如 5 个）：

```powershell
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "${PWD}:/app" vibe-astock-shared:local python sharing_admin.py add-slots 5
docker compose -f .sharing/compose.json up -d --remove-orphans
```

每个空闲名额也占用一个私人实例的内存，适合少量朋友使用。实例健康检查通过后才会发放邀请；未准备好时页面提示重试，不消耗名额。下面的命令行方式仍可直接创建指定账号。

把 `friend01` 换成朋友的网站账号（3–32 位小写字母、数字、下划线、短横线，字母开头）：

```powershell
docker run --rm -v vibe-astock-accounts:/home/app/sharing -v "${PWD}:/app" vibe-astock-shared:local python sharing_admin.py add-user friend01
docker compose -f .sharing/compose.json up -d --remove-orphans
```

把网站链接和 `.sharing/friend01-invite.txt` 中的邀请交给对应朋友。朋友激活网站账户后可直接阅读公共复盘；需要 AI 时在“接入 AI”授权自己的 Codex，或填写自己的 API Key 并保存。后台复盘也使用这里保存的配置。

每次生成配置都明确使用同一端口和 HTTPS/本机 HTTP 模式；命令默认回到正式配置 `8910 + Secure Cookie`。

## 原有数据迁移

迁移前停止原实例和新 owner 实例，保留原数据卷作为备份。只将原来的 `.duanxian-agents`、`.vibe-research` 和 `.codex/auth.json` 复制到 owner 的独立数据卷，绝不能复制给朋友。新实例的卷名可在 `.sharing/compose.json` 的 `worker-<id>` 下找到。

owner 启动时会把已有可用复盘导入公共版本库。新生成的公共产物先写本人的磁盘，再发布到网关；发布失败保留待发送文件并每 15 秒重试。原交易日志、持仓、盯盘记录仍留在 owner 私人实例中。

浏览器里的旧自选和研究记录：用 owner 登录，在“接入 AI”点击“导入原有浏览器自选和记录”。只有管理员能看到此入口；普通朋友不会自动接收旧浏览器数据。旧的浏览器 API Key 不会自动分配给任何新账号，请在本人账号重新保存。

## 退出、恢复与备份

- “退出网站账号”撤销当前网站会话；不影响其他人的会话或正在执行的任务。
- 左下角「退出登录」与设置页的退出操作相同；侧栏收起时仍保留退出图标。
- “断开我的 Codex”清除本人实例的订阅登录和模型配置；后台复盘或深挖未结束时拒绝断开。
- Codex 首次连接或重连成功后自动弹出模型选择，选择模型并点「保存并完成连接」；暂未读到模型目录时可以重试获取或保存 CLI 默认模型。
- 忘记网站密码：运行上述管理命令，将 `add-user` 改为 `reset-invite`；该用户旧会话立即失效，新邀请码用于重新设置密码。
- 停用账号：将 `add-user` 改为 `disable`，再执行 `up -d --remove-orphans`；保留其数据卷，公共历史版本保留作者。
- 备份 `vibe-astock-accounts` 卷与各个账号的数据卷，备份同样包含敏感凭证，应限制访问。
- 更新：重新构建镜像，再对 `.sharing/compose.json` 执行 `up -d`。原 `compose.yaml` 仍是单用户模式，不应作为共享网站入口重新启动。

## 验证

```powershell
docker run --rm -e VIBE_ACCOUNTS_DB=/tmp/test-accounts.sqlite3 -v "${PWD}:/app" vibe-astock-shared:local python -m pytest tests/test_sharing.py tests/test_codex_device_auth.py tests/test_cli_model_selection.py -q
node frontend/tests/codex-reconnect.mjs
```

检查身份伪造、跨账号自选访问、CSRF、邀请复用、退出撤销、密码限流、独立实例路由、流式响应、公共版本共享、无凭证拒绝调用和发布失败重试。测试使用假凭证，不消耗真实订阅额度。
