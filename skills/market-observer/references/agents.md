# OpenClaw / Hermes / Codex

## 加载本 Skill（本仓库已提供）

将整个 `market-observer` 文件夹交给 Agent 的 Skill 加载器，包括 scripts/references/assets。它使 Agent 学会部署观市、获取行情证据并按研究流程生成报告；推理、网页搜索和文档读取使用该 Agent 自己的已配置能力。

- Codex：复制到配置的 skills 目录（常见为 `~/.codex/skills/market-observer`）。
- OpenClaw：当前文档支持 `openclaw skills install ./skills/market-observer --as market-observer`，加载器与版本相关，安装前可查看本机帮助。[官方 Skills 文档](https://docs.openclaw.ai/tools/skills)
- Hermes：完整复制到当前 profile 的 `~/.hermes/skills/market-observer`，或使用该版本支持的 Skill 安装方式。私有仓库先经用户已登录的 GitHub 工具克隆，不把访问令牌写进 URL。[官方 Skills 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

尚未在用户的 OpenClaw / Hermes 实例中执行端到端验证，不能声称已自动连通这两个 Agent。

## UI 调用 Agent（后续集成，不属于当前已实现功能）

这与“加载 Skill”方向相反。OpenClaw Gateway 可提供兼容 HTTP 端点，Hermes 可开启 API Server，后台可把任务交给其中一个 Agent，再展示报告。附带 UI 尚未实现这段调用、报告存储或任务队列。

若用户请求实现：先确定 Agent 所在主机、实际版本、端点和认证方式；读取官方当前文档并做只读连通性检查。地址不是模型 ID，不能把模型供应商的 API Key 当成 Agent Gateway 令牌。WSL、Docker、远端主机的 localhost 不等于 Windows 本机。

完成桥接时，令牌仅保存在后端配置，按任务隔离会话，处理长任务超时、错误和取消，核查成功结束状态再保存报告。使用专门研究 Agent/工具权限，避免让新闻正文触发任意系统操作。不要为了连接而默认把观市绑定公网或关闭已有认证。

参考：[OpenClaw HTTP](https://docs.openclaw.ai/gateway/openai-http-api)、[Hermes API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)。
