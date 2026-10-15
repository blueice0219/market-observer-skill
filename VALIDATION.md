# Skill 验证记录

验证日期：2026-10-15。Windows，Python 3.14.5。

| 项目 | 结果 |
|---|---|
| skill-creator quick_validate | 通过：frontmatter、名称、入口结构 |
| Skill 助手测试 | 10 passed |
| 打包应用测试 | 50 passed；1 条 Starlette/httpx 弃用警告 |
| 真实 TCP 冒烟测试 | 两个 API 进程、100 个并发查询任务、跨进程快照更新通过 |
| 个股研究证据助手 | 从本机现有服务取得 000001 的新浪行情，写入临时证据文件成功 |
| 运行数据分离 | 临时证据文件、数据库、日志和虚拟环境不纳入仓库 |

助手测试包括：拒绝覆盖部署目录、静态资源复制、非法股票代码拒绝、真实 HTTP 读取、密钥不写入证据、旧证据不覆盖、demo 拒绝、陈旧提示、非本地明文认证拒绝、引用文件存在性。

## 尚未验证或未实现

- 本地未执行 Linux；GitHub Actions 配置提供 Ubuntu / Windows × Python 3.11 / 3.14 的离线测试。云端结果以仓库 Actions 页面为准。
- 尚未在 OpenClaw / Hermes 运行时中加载并端到端研究；安装方法以对应官方文档和本机版本为准。
- 研究工作流依赖宿主 Agent 的真实搜索与文档能力；本 Skill 不附赠搜索服务或模型额度。
- 应用 UI 未实现自动 Agent 网关调用、报告历史与 PDF 导出；不能将工作流说明误称为这些功能已开发完成。

原应用的联网测试及 UI 验证详情见 `skills/market-observer/assets/app/TEST_REPORT.md`，属于开发时的观测记录，不代表后来部署环境的网络可用性。
