# 观市 · Market Observer Skill

把 A 股行情工作台与可追溯的个股研究流程封装成一个可携带的 Agent Skill。仓库包含全部应用源码，Windows/Linux 运行教程、中文 UI、测试及研究助手脚本。

## 能做什么

- **已有可执行功能**：沪深京行情采集、SQLite 快照、四类 HTTP 接口、中文 UI、自选、排行、CSV 导出。
- **Skill 研究流程**：调用宿主 Agent 的搜索/文档能力补充公告、财务与新闻；以引用支持事实、推断及条件化情景，生成 Markdown 个股报告。
- **未实现的功能**：UI 自动调用 OpenClaw/Hermes、报告历史页面、定时 AI 报告、内置 PDF 导出。安装 Skill 不会凭空配置模型和搜索服务。

## 安装 Skill

私有仓库需先登录拥有访问权限的 GitHub 账号：

```text
gh repo clone blueice0219/market-observer-skill
```

需要安装的是完整的 `skills/market-observer` 文件夹，而不是单独 SKILL.md。

| 宿主 | 安装位置/方法 |
|---|---|
| Codex | 复制到当前配置的 skills 目录，通常为 `~/.codex/skills/market-observer` |
| OpenClaw | 在仓库根目录运行 `openclaw skills install ./skills/market-observer --as market-observer`；先确认本机版本支持此命令 |
| Hermes | 完整复制到当前 profile 的 `~/.hermes/skills/market-observer`；已有同名 Skill 时先比较而非覆盖 |

Codex 识别后可用 `$market-observer`，其他 Agent 按其 Skill 调用方式使用。示例请求：

> 使用 market-observer，查询 000001 的行情，结合最近公告、新闻及已披露财报，生成一份带来源与数据截止时间的观察报告。

## 独立运行应用

无需 Agent 也能运行行情 UI。进入 Skill 目录，复制应用并安装：

```text
python scripts/bootstrap.py --target /your/empty/deployment/path --install
```

Windows 可将目标写为 `D:\apps\market-observer`，然后在部署目录双击 `open_ui.cmd`。Linux 按 [完整应用教程](skills/market-observer/assets/app/README.md) 启动采集器和 API。默认页面 `http://127.0.0.1:8000/`。

若本机已经安装观市，可直接使用现有服务，不需要重装。

## 仓库结构

```text
skills/market-observer/
  SKILL.md                 Agent 入口
  agents/openai.yaml       Codex 界面元数据
  references/              运行、API、研究流程、报告结构和 Agent 接入
  scripts/                 新部署与个股证据助手
  assets/app/              完整行情应用、UI、测试及教程
tests/                     Skill 助手行为测试
.github/workflows/         跨平台离线验证
```

## 验证与边界

应用部分 Windows 已验证 50 项测试及真实新浪数据。Skill 的结构与脚本另外验证，见 [验证记录](VALIDATION.md)。Linux 执行以 GitHub Actions 的实际结果为准；未在 OpenClaw/Hermes 实例中做运行验证。行情源延迟、数据完整性及长期可用性无保证；财务与消息分析必须核验资料，不执行证券交易。

不会随仓库提供本机虚拟环境、数据库、日志、自选记录、API 密钥、用户报告或私有 Agent 配置。
