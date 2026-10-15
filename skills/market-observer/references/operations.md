# 运行与维护

## 新部署

需要 Python 3.11+。从 Skill 根目录执行，目标必须不存在或为空：

```text
python scripts/bootstrap.py --target /absolute/path/market-observer --install
```

`--install` 创建目标目录内 `.venv`，安装应用和行情依赖；无此参数仅复制源文件。开发测试再安装 `.[test]`。已经有运行实例时直接使用它；不要因为调用 Skill 就重复安装、复制数据库或启动第二个采集器。

进入部署目录，用虚拟环境解释器运行（Windows 为 `.venv\Scripts\python.exe`，Linux 为 `.venv/bin/python`）：

```text
python -m a_share_monitor collect --source auto --interval 300 --timeout 180
python -m a_share_monitor serve --host 127.0.0.1 --port 8000
```

两条命令在不同进程运行，并设相同的绝对 `MONITOR_DB`。UI 位于 `/`，接口文档位于 `/docs`。Windows 可在部署后使用 `open_ui.cmd` 开应用窗口，`stop_local.cmd` 停止该启动器管理的进程。

完整的 Windows/Linux 命令、文件兼容与故障说明见 [应用 README](../assets/app/README.md)。

## 配置与错误

环境变量：MONITOR_DB、MONITOR_STALE_SECONDS、MONITOR_CORS_ORIGINS、MONITOR_API_KEY。不会自动读取 .env。环境代理默认沿用，Windows 本机启动器提供直连模式；只在用户网络需要时调整其启动参数，不改变系统代理。

第一次测试可指定独立的 demo 数据库和 `collect --source demo --once`，明确告知是示例。实时源 auto 使用东方财富，失败后新浪。失败退避而非无限立即重试；诊断每个源至多一次后根据错误调整，不持续轰击源站。

旧文件使用 `collect --source file --file path --volume-unit shares`，确认单位为股或手。支持 CSV/TSV、JSON 多种布局、JSONL；错误拒绝整批。生产方应写临时文件后原子替换，合法但截断的数据无法凭解析成功判定完整。

数据和日志留在部署目录，不放进 Skill 或 Git。不要运行中单独复制 SQLite 主文件作为完整备份。Linux 分支原始交付未在本机运行，仓库 CI 提供后续可核查验证。
