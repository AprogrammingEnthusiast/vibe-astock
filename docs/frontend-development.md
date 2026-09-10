# 前端设计与开发规范

文中路径以仓库根目录为基准；仅文件名或局部路径按所在段落说明解析。通用协作规则及其他任务文档入口见 [AGENTS.md](../AGENTS.md)。

## 页面、状态与请求

- 页面在 `pages/`，可复用业务面板在 `components/`，基础展示组件在 `components/ui/`，布局在 `components/layout/`，请求、类型和共享逻辑在 `lib/`（均相对 `frontend/src/`）。只服务一个页面的小组件可与页面同文件，出现实际复用再提取。
- 新入口同步 `frontend/src/router.tsx` 与 `Layout.tsx` 的导航分组；设置子页使用 `SettingsLayout.tsx` 的嵌套路由，权限入口跟随账号角色。站内导航使用 Router 的 Link/NavLink，保留 basename 子路径支持。
- 保持 `main.tsx` 中 AccountGate 先确认身份、加载本人配置，再挂载业务页面的顺序。页面局部状态优先 useState/useRef，派生值直接计算或按需 useMemo；跨页自选、研究记录和模型配置复用现有 lib 模块，不另存一套。依赖中有 Zustand 不代表每个页面都需要全局 store。
- 所有后端地址经过 `frontend/src/lib/base.ts` 的 `apiUrl()`。VR 请求扩展 `lib/api.ts`，复盘请求复用 `lib/agent.ts` 的 agentFetch/agentPost，新版任务复用 `lib/agent-api.ts` 的 agentRequest，对话复用 `lib/llm.ts` 的 chatStream；保留鉴权、账号绑定与 CSRF 行为，避免页面各写一套请求客户端。
- TypeScript 沿用严格检查、无未使用变量/参数和 `@/` 路径别名，配置见 `frontend/tsconfig.json`。接口类型跟随所属客户端定义；不靠新增 any 或类型断言掩盖不确定响应，外部数据用 unknown 校验，复用 finite/safeArray/safeRecord。
- 异步页面明确区分加载、成功、空结果、错误、降级和任务执行中；已复盘/尚未收盘属于状态提示。日期、股票或版本切换时防止旧响应覆盖新结果，参考 `AgentReview.tsx` 的请求编号与存活标记；不能把上一个标的/日期的数据留作当前结果。
- effect 在卸载或依赖变化时清理定时器、监听器和图表；轮询防重入，聊天关闭或切换时传递 AbortSignal。兼容 StrictMode 的重复挂载，昂贵分析和写操作由用户动作触发，不能在挂载 effect 中重复启动。
- 模型文本优先用现有 ReactMarkdown + remark-gfm。深挖已有 HTML 字段依赖 `duanxian/review_store.py` 的 md_to_html 先转义；不得把外部新闻、模型原文或用户输入直接放进 dangerouslySetInnerHTML。图表 tooltip 同样按不可信文本处理。

## 视觉、数据展示与交互

- 延续暖橙主色、玻璃卡片和密集数据面板；颜色、圆角、字体与阴影以 `frontend/src/index.css` 和 `frontend/tailwind.config.ts` 为源，优先语义 Tailwind 类，类名使用完整静态字符串。新增主题值在这两处定义，不在各页面复制另一套 token。
- 主题切换复用 `frontend/src/hooks/useDarkMode.ts`：CSS 根变量是暗色，`.light` 覆盖为亮色，hook 在无保存偏好时默认暗色。两种主题都要检查正文、表格、表单和图表对比度，不能仅按 CSS 注释判断实际默认主题。
- 页面优先复用 PageHeader、GlassCard、Caliber、Disclaimer 等现有组件；类名组合使用 `cn()`，图标使用 lucide-react。主内容沿用 Layout 的 workspace-content 与页边距，面板按需响应式分栏；窄屏长表和复杂图表在自身容器横向滚动，避免挤坏整页。
- A 股红涨绿跌：文字、条形和强弱标记统一使用 `frontend/src/lib/colors.ts` 的 pctColor/barColor/countColor/strengthColor 及方向常量。涨跌家数按含义而非数字正负选色；操作成功/失败的状态色与市场涨跌语义分开判断。
- 数字显示复用 `lib/agent.ts` 的 finite、ratioPct、pct：0～1 比率与已是百分数的值分开格式化。未知值显示 `—` 或明确原因，真实零值显示 0；表格数字右对齐并使用 tabular-nums 或等宽字体，金额、单位、时间与口径说明放在读数附近。
- 图表沿用 ECharts 按需注册（参考 `SectorFlowPanel.tsx`），简单迷你趋势可用现有 SVG。实例跟随容器 resize，卸载 dispose；只对有效有限值计算范围，历史缺口断线，不能补零或跨缺口连线。Top N 在方向筛选后截取，面积用绝对值时同时保留正负标签和单位。
- loading、空数据和错误要有可见文本；不能只靠颜色或 toast 告知关键失败。操作按钮展示提交中并防重复提交；原生 button/input/select 优先，表单有 label，图标按钮有可访问名称，保留键盘焦点样式。
- 可展开内容维护 aria-expanded/aria-controls，弹层支持 Escape 和合理焦点处理；筛选按钮用 aria-pressed。参照 Caliber、AccountGate 和 SectorFlowPanel 的交互实现，新增动效遵循 prefers-reduced-motion；不要复制旧组件缺少键盘操作的可点击 div。
