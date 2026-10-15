# A 股全市场监控与 HTTP API

**新增中文图形界面「观市」**：本机打开 `http://127.0.0.1:8000/`，或双击 `open_ui.cmd`。支持市场概览、搜索排序、自选、排行榜、股票详情和 CSV 导出，详见 [UI_GUIDE.md](UI_GUIDE.md)。

根据历史会话中的功能需求重建，版本 1.0.0。历史 a_share_monitor.zip 的源码和附件无法从会话引用中恢复，因此这不是对原 ZIP 的逐文件补丁，也不声称与未知的旧参数、目录、告警逻辑完全兼容。此包提供可独立运行的持续行情采集、快照持久化、历史保留、JSON/CSV 导出，以及四类 HTTP 查询接口。

**先用离线演示验证安装，再开启真实采集。示例数据不是当前行情。** 实时模式没有数据时返回 503，不会自动拿示例数据冒充行情。外部免费行情源的可用性、延迟和覆盖范围不受本项目控制。

## 1. 项目内容

```text
a_share_monitor/        配置、格式解析、采集、数据库、API、命令行
examples/quotes.csv     文件导入示例（虚构价格）
tests/                  无网络自动化测试
scripts/                演示启动、真实 TCP 并发测试
README.md               Windows/Linux 使用与接口说明
TEST_REPORT.md          本次交付的实际验证结果
pyproject.toml          安装入口和固定的直接依赖版本
.github/workflows/      Windows/Linux 测试矩阵（需提交到 GitHub 才会执行）
```

架构：东方财富/新浪 → 独立采集进程 → SQLite WAL 事务快照 → 一个或多个 API 进程 → HTTP 客户端。接口不抓取上游，每次请求读取同一份完整快照；多个 API 进程共享本机数据库，无各自后台抓取或内存缓存不同步问题。

## 2. Windows 安装与离线运行

使用 Python 3.11 或以上；本次实际验证版本见 TEST_REPORT.md。解压 ZIP，进入包含 pyproject.toml 的 `a_share_monitor` 文件夹。在 PowerShell 执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
$env:MONITOR_DB = Join-Path (Get-Location) 'data\demo.sqlite3'
.\.venv\Scripts\python.exe -m a_share_monitor collect --source demo --once
.\.venv\Scripts\python.exe -m a_share_monitor serve
```

无需激活虚拟环境，也无需调整系统脚本执行策略。服务前台运行，保持窗口打开；按 Ctrl+C 停止。浏览器访问：

- 交互接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 全部示例行情：[http://127.0.0.1:8000/api/v1/quotes?limit=10000](http://127.0.0.1:8000/api/v1/quotes?limit=10000)
- 状态：[http://127.0.0.1:8000/api/v1/status](http://127.0.0.1:8000/api/v1/status)

另开 PowerShell 查询：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/stocks/000001'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/rankings?metric=change_pct&order=desc&limit=10'
curl.exe 'http://127.0.0.1:8000/api/v1/status'
```

示例有 6 条，`meta.is_demo=true`、名称带示例标记；仅采集一次时 15 分钟后变成 stale，属于预期行为。演示数据库与真实数据库请分别使用不同路径。

## 3. Linux 安装与离线运行

以已安装 Python 3.11+ 的 Linux 为例；Debian/Ubuntu 如提示缺少 venv，请先安装对应版本的 python3-venv 软件包。

```bash
cd a_share_monitor
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
export MONITOR_DB="$PWD/data/demo.sqlite3"
.venv/bin/python -m a_share_monitor collect --source demo --once
.venv/bin/python -m a_share_monitor serve
```

另开终端：

```bash
curl 'http://127.0.0.1:8000/api/v1/quotes?limit=10000'
curl 'http://127.0.0.1:8000/api/v1/stocks/600000.SH'
curl 'http://127.0.0.1:8000/api/v1/rankings?metric=amount&limit=10'
```

## 4. 开启真实持续采集

安装额外行情依赖：

```powershell
# Windows：在项目目录执行
.\.venv\Scripts\python.exe -m pip install -e ".[live,test]"
$env:MONITOR_DB = Join-Path (Get-Location) 'data\live.sqlite3'
.\.venv\Scripts\python.exe -m a_share_monitor collect --source auto --interval 300 --timeout 180
```

另开窗口，在同一个项目目录使用同一个数据库路径：

```powershell
$env:MONITOR_DB = Join-Path (Get-Location) 'data\live.sqlite3'
.\.venv\Scripts\python.exe -m a_share_monitor serve --host 127.0.0.1 --port 8000 --workers 2
```

Linux 采集终端：

```bash
.venv/bin/python -m pip install -e '.[live,test]'
export MONITOR_DB="$PWD/data/live.sqlite3"
.venv/bin/python -m a_share_monitor collect --source auto --interval 300 --timeout 180
```

Linux API 终端：

```bash
export MONITOR_DB="$PWD/data/live.sqlite3"
.venv/bin/python -m a_share_monitor serve --workers 2
```

`auto` 先尝试东方财富，失败或覆盖检查不通过时再尝试新浪；整批替换，不混合两源行情。也可明确指定 `--source eastmoney` 或 `--source sina`。不依赖同花顺账号、Cookie 或付费 Token。

默认每轮结束后等待 300 秒，不是每 300 秒保证产出一份数据；全市场分页耗时会叠加。每个来源有独立的 180 秒总超时，auto 一轮最多约两倍该超时再加本地处理。失败后指数退避，等待上限约 3600 秒再加少量随机延时。实时模式最低间隔 60 秒仅为本项目保护值，不是上游承诺的免费配额；建议使用默认 300 秒起步。采集不自动排除节假日或盘后，盘后返回的数据可能仍是上个交易日行情。

默认实时结果至少 4000 行，且不能比上一个真实快照少超过 20%，否则拒绝覆盖。`--min-rows` 可调整，但这是异常检测，**不是完整性证明**；不提供证券主表逐代码对账，`coverage=provider_unverified`。停牌、缺失和上游漏页仍需业务侧核对。

单次采集、诊断及导出：

```bash
# 以下 python 指项目虚拟环境内的解释器；Windows 可替换成 .\.venv\Scripts\python.exe
python -m a_share_monitor collect --source auto --once
python -m a_share_monitor doctor --source eastmoney --timeout 180
python -m a_share_monitor doctor --source sina --timeout 180
python -m a_share_monitor export data/latest.json
python -m a_share_monitor export data/latest.csv
```

`doctor` 只输出来源、条数和前两条样本，不改变数据库；失败退出码为 1。日常日志输出到终端，可通过 `> collector.log 2>&1` 重定向。

## 5. 接入已有监控文件

不知道旧项目的确切文件格式时，优先保留其采集进程，再用此服务导入其输出。文件模式每轮读取指定的本地文件，不从 URL 下载，也不允许通过 HTTP 上传或任意指定路径。

```powershell
$env:MONITOR_DB = Join-Path (Get-Location) 'data\import.sqlite3'
.\.venv\Scripts\python.exe -m a_share_monitor collect --source file --file .\examples\quotes.csv --volume-unit shares --interval 10
```

支持 UTF-8、UTF-8 BOM、GB18030；扩展名决定格式，不对内容作含糊猜测：

| 格式 | 支持布局 |
|---|---|
| JSON | 对象数组；`{"data":[...]}` / `{"quotes":[...]}` / `{"records":[...]}` |
| pandas JSON | records、split、columns、index，以及带 data 数组的 table |
| JSONL/NDJSON | 每个非空行一个行情对象 |
| CSV/TSV | 有表头，逗号/制表符分隔；CSV 内含逗号的数字需用引号包围 |

不支持 pickle、Excel、Parquet、压缩包或无表头文本；先由原程序导出上述格式。不自动推断百分数是否为小数比例，也不猜测“万/亿”等单位。

必需字段为 `code/代码/股票代码/symbol`、`name/名称/股票名称`、`price/最新价/trade`；价格字段必须存在但可为空。标准代码保存为六位字符串；也接受 sh600000、600000.SH、CSV 数字 1（还原为 000001）。过滤范围为沪深京 A 股代码规则，拒绝 ETF、B 股或交易所前缀冲突；未来规则变化需更新 formats.py。

可选字段及中文别名：涨跌幅→change_pct、涨跌额→change、今开→open、最高→high、最低→low、昨收→prev_close、成交量→volume、成交额→amount、换手率→turnover_pct、时间戳→quote_time。未知列被忽略。重复股票代码、非数值脏数据、缺列、负价格/成交量等拒绝整批，保留旧快照；`-`、`--`、NaN、Infinity、空字段转换为 JSON null。缺失值不会伪造为 0。

价格和金额均为元；API 成交量统一为**股**。东方财富适配器将手乘 100，新浪保持股；导入文件必须用 `--volume-unit shares` 或 `lots` 明确原始单位。`change_pct=1.5` 表示 1.5%，不是 0.015。

上游文件建议“同目录写临时文件 → 关闭 → 原子重命名”，不要边写边让导入器读取。解析失败会保留旧快照，但直接覆盖文件仍可能产生语法合法的半份数据，程序无法凭空判断是否完整。单个文件最多 32 MiB、最多 20000 行。文件的 `observed_at` 使用文件修改时间，反复读取旧文件不会刷新数据年龄；它不是交易所时间，复制旧文件可能改变修改时间。导出 JSON/CSV 再导入同样按文件修改时间计算，原元数据不会被当作可信实时证明。

## 6. HTTP 接口

默认监听 `127.0.0.1:8000`，只读 GET；OpenAPI 为 `/openapi.json`，交互文档 `/docs`。

| 路径 | 用途 | 主要参数 |
|---|---|---|
| `/api/v1/quotes` | 当前快照全部股票的分页、搜索和排序 | limit=100（1..10000）、offset=0、exchange、q、sort_by、order |
| `/api/v1/stocks/{code}` | 单只股票 | 六位或交易所前后缀代码 |
| `/api/v1/rankings` | 涨跌幅/价格/成交量/成交额等排行榜 | metric=change_pct、order=desc、limit=20（1..500）、exchange |
| `/api/v1/status` | 数据新鲜度、采集错误、来源及时间窗口估计 | 无 |
| `/healthz` | API 进程存活，不要求已有数据 | 无，始终免 API Key |
| `/readyz` | 有快照且未过期，否则 503 | 无 |

`exchange` 可为 sh/sz/bj；`q` 匹配代码或股票名称，最长 64 字符。
`sort_by` 可为 code、price、change_pct、change、volume、amount、turnover_pct；`metric` 为除 code 外的相同字段；`order` 为 asc/desc。榜单忽略该指标为空的股票，同值按代码升序稳定排序。普通排序中 null 永远在末尾。

所有行情接口接受 `require_fresh=true`，过期返回 503；默认仍返回旧行情，但 `meta.stale=true`。`/readyz` 仅检查快照年龄，有示例数据也可 ready，因此生产调用方应同时检查 `is_demo=false`、来源和 coverage。

行情响应结构示意（不是当前行情）：

```json
{
  "meta": {
    "version": "每次发布唯一标识",
    "source": "demo",
    "is_demo": true,
    "coverage": "sample",
    "count": 6,
    "collected_at": "带时区的 UTC 时间",
    "observed_at": "采集结束时间或文件修改时间",
    "age_seconds": 2.3,
    "stale": false,
    "exchange_timestamp_verified": false
  },
  "total": 6,
  "offset": 0,
  "limit": 100,
  "data": [{"code":"000001","exchange":"sz","name":"平安银行（示例）","price":10.0}]
}
```

实际行情还包含 symbol、涨跌、开高低昨收、成交量/额、换手率和 quote_time；meta 另含单位、过期阈值、collector_error。`quote_time` 仅保留上游原文，可能只有时分秒或为空，不推定其日期。`stale=false` 表示最近采集/文件修改，不证明行情为当前交易日、逐笔实时或无延迟。

全市场一次获取可设 `limit=10000` 并核对 `len(data)==total`；如果大于单页上限请分页。跨页设置 `expected_version` 等于第一页 meta.version；如期间更新会返回 409，客户端应丢弃已读分页并重新开始。API 不提供历史版本查询。

`status` 的状态是 no_data / stale / degraded / ok，按此优先级判断。market_clock 为上海时区的星期/时间窗口估计，**未接入法定休市日历**，不等同真实开市判断。不会拿本机所在时区计算交易时段。

错误响应统一：

```json
{"error":{"code":"NO_DATA","message":"暂无有效快照，请先运行采集器并查看 /api/v1/status","details":null,"request_id":"请求追踪 ID"}}
```

401：API Key 不正确；404：路径或股票不存在；409：快照已变化；422：参数无效；503：无行情、强制新鲜度失败或数据库不可用；500：内部错误。客户端应检查 HTTP 状态码。响应头 X-Request-ID 可匹配服务日志，服务器堆栈不会通过 API 暴露。

## 7. Python 和浏览器调用

Python 示例仅使用标准库：

```python
import json
from urllib.request import Request, urlopen

url = 'http://127.0.0.1:8000/api/v1/quotes?limit=10000'
request = Request(url)  # 若开启认证，加 headers={'X-API-Key': '你的密钥'}
with urlopen(request, timeout=10) as response:
    result = json.load(response)
print(result['meta']['source'], result['meta']['stale'])
for stock in result['data']:
    print(stock['code'], stock['name'], stock['price'])
```

浏览器跨域调用前，设置允许的前端 origin 后**重启 API**：

```powershell
$env:MONITOR_CORS_ORIGINS = 'http://localhost:3000,http://127.0.0.1:5173'
$env:MONITOR_API_KEY = '替换为你自己的长随机密钥'
.\.venv\Scripts\python.exe -m a_share_monitor serve
```

```bash
export MONITOR_CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:5173'
export MONITOR_API_KEY='替换为你自己的长随机密钥'
.venv/bin/python -m a_share_monitor serve
```

```javascript
const response = await fetch('http://127.0.0.1:8000/api/v1/rankings?limit=10', {
  headers: { 'X-API-Key': '与你设置的密钥一致' }
});
const body = await response.json();
if (!response.ok) throw new Error(body.error.message);
console.table(body.data);
```

CORS 默认关闭跨域。支持显式 origin 或 `*`，不启用 Cookie/credentials。允许 GET、OPTIONS 和 X-API-Key 头，错误响应也包含适当 CORS 头。origin 必须包含协议与端口，不能带路径。CORS 不是认证；前端内嵌的共享密钥也不能当作用户权限系统。

启用密钥后所有业务接口和 readyz 需要 X-API-Key；healthz、docs、openapi.json 公开。Swagger 文档页点击 Authorize 输入配置的密钥后即可测试；未启用密钥时无需填写。

## 8. 配置、并发和持久化

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| MONITOR_DB | 当前目录 data/market.sqlite3 | 推荐绝对路径，采集器与 API 完全一致 |
| MONITOR_STALE_SECONDS | 900 | 1..604800 秒，控制过期标记 |
| MONITOR_CORS_ORIGINS | 空 | 逗号分隔的 origin |
| MONITOR_API_KEY | 空 | 非空则开启业务接口共享密钥认证 |

程序读取真实环境变量，**不自动读取 .env**。修改设置后重启相关进程。

同一数据库只允许一个采集器，跨进程文件锁防重复启动；进程退出或崩溃后操作系统释放锁，锁文件留存是正常现象。SQLite WAL + 事务保证读者不会看到半份快照，忙时最多等待 10 秒，HTTP 存储错误为 503。API 支持多 worker，且永远不启动采集器。数据库应放在本机磁盘，不使用网络共享或同步盘，勿在运行时只复制 sqlite3 主文件作备份，应停止所有进程后复制或使用 SQLite backup API。

每次成功采集保存整份历史快照，默认最多 24 份，可用 `collect --keep 100` 修改。失败不删除旧行情。删除历史行会复用 SQLite 空间，但数据库文件不会立即缩小。需要长期审计时自行增加保留量或定时导出；API 只查询当前快照。JSON/CSV 导出以临时文件+原子替换写入。

Ctrl+C/SIGTERM 停止后不启动下一轮；若正在调用行情库，会等待本次受限超时的抓取结束，auto 模式可能包含第二来源的尝试。外部请求放在子进程，到达 timeout 会终止并回收子进程，避免线程超时后仍无限抓取。

## 9. 常驻部署

本机使用保持两个终端打开即可。Windows 可用任务计划程序分别创建采集、API 两个任务：程序设为完整路径 `.venv\Scripts\python.exe`，起始目录设为项目根目录；参数分别用 `-m a_share_monitor collect --source auto` 和 `-m a_share_monitor serve`。在任务所调用的脚本中设置同一个绝对 MONITOR_DB，启用失败重启，避免重复实例。

Linux 可用两份 systemd unit，下面是一份采集器示例；将路径和 User 改成实际值，另存 API unit，把 ExecStart 改为 `.../.venv/bin/python -m a_share_monitor serve --workers 2`。

```ini
[Unit]
Description=A-share collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/a_share_monitor
Environment=MONITOR_DB=/opt/a_share_monitor/data/live.sqlite3
ExecStart=/opt/a_share_monitor/.venv/bin/python -m a_share_monitor collect --source auto
Restart=on-failure
RestartSec=30
TimeoutStopSec=400

[Install]
WantedBy=multi-user.target
```

```bash
# 保存为 /etc/systemd/system/a-share-collector.service 及 a-share-api.service 后
sudo systemctl daemon-reload
sudo systemctl enable --now a-share-collector a-share-api
journalctl -u a-share-collector -f
```

局域网访问可用 `serve --host 0.0.0.0`，客户端用服务器实际 IP，不是 0.0.0.0。开放防火墙端口和配置认证后再使用。面向公网时在反向代理配置 HTTPS、访问控制、限流；此轻量服务不含按用户配额或公网抗压设计。不要把未经授权的上游行情转售或公开分发；具体许可由数据提供方决定。

## 10. 测试与排障

```powershell
# Windows
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\smoke_http.py
```

```bash
# Linux
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_http.py
```

测试覆盖格式、编码、前导零、缺失值、非法值、单位、重复代码、分页、过滤、排名、404/422/503、过期、CORS、认证、并发读写、进程锁、超时、来源切换、覆盖率保护及导出回读。真实 TCP 脚本使用临时数据库、两个独立 API 进程和 100 个并发任务，不需要行情源，不触碰日常数据库。

- **503 / NO_DATA**：先运行 collect；确认 API 与采集器 MONITOR_DB 完全一致，再看 status/采集日志。
- **stale**：采集器可能停止、失败或文件长时间未更新。盘后时间戳不证明交易日新鲜度；不要只把阈值调大来掩盖故障。
- **实时源失败**：运行 doctor 查看终端诊断。上游封禁、断连、字段变更均可能发生，不保证永久免费可用或毫秒级延迟。
- **ProxyError**：检查 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY 是否指向有效代理。本次测试环境曾存在无效代理配置。若所在网络支持直连，可仅在当前 PowerShell 会话执行 `Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY -ErrorAction SilentlyContinue` 后重试；Linux 可用 `env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY .venv/bin/python -m a_share_monitor doctor --source sina`。企业网络需要代理时修正代理地址，不关闭 TLS 验证。
- **another collector**：已有采集器使用同一数据库，停止多余进程或换数据库；删除锁文件不是解决办法。
- **端口占用**：`serve --port 8001`；浏览器和调用地址同步修改。
- **乱码**：使用 UTF-8 文件；PowerShell 可设置 `$env:PYTHONUTF8='1'`，终端显示问题不代表 JSON 字节损坏。
- **依赖测试警告**：固定依赖组合可能有弃用提示，是否影响运行以 TEST_REPORT.md 为准。

## 11. 来源与范围

实现参考 AKShare 的公开文档中两种行情接口及成交量单位，不使用付费接口：

- [AKShare 股票数据文档](https://akshare.akfamily.xyz/data/stock/stock.html)
- [AKShare 东方财富适配实现](https://github.com/akfamily/akshare/blob/master/akshare/stock_feature/stock_hist_em.py)
- [AKShare 新浪适配实现](https://github.com/akfamily/akshare/blob/master/akshare/stock/stock_zh_a_sina.py)
- [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)
- [FastAPI lifespan 测试](https://fastapi.tiangolo.com/advanced/testing-events/)

AKShare 文档提示新浪重复调用可能被暂时封 IP，未给出稳定统一的免费调用配额。这里的重试和节流是应用策略，不是对供应商实时性、完整性、商用许可的保证。本项目不是逐笔行情、Level-2、交易执行或交易所行情授权服务。
