# 数据接口

所有行情请求为 GET。默认地址 `http://127.0.0.1:8000`，认证启用时传 `X-API-Key`；不要把密钥放在 URL、报告或提交到仓库。

| 路径 | 参数/用途 |
|---|---|
| `/api/v1/stocks/000001` | 六位或 sh600000 / 600000.SH，单股与元数据 |
| `/api/v1/quotes` | limit 1..10000、offset、exchange sh/sz/bj、q、sort_by、order |
| `/api/v1/rankings` | metric change_pct/change/price/volume/amount/turnover_pct；order asc/desc；limit 1..500 |
| `/api/v1/status` | no_data/stale/degraded/ok、最后错误与采集时间 |
| `/healthz` | 存活，不证明行情可用 |
| `/readyz` | 快照存在且未过期；demo 也可能 ready |

成功行情含 `meta` 和 `data`。重点检查 `meta.is_demo`、`stale`、`age_seconds`、`source`、`coverage`、`version`、`collected_at`。股票数据含 code、name、price、change_pct、change、open/high/low/prev_close、volume、amount、turnover_pct、quote_time。缺失为 null。

错误结构为 `error.code/message/details/request_id`。401 认证；404 股票或路径不存在；409 快照更新；422 参数非法；503 无数据、过期或存储不可用。`require_fresh=true` 可拒绝过期行情。

分页使用第一页的 meta.version 作为 `expected_version`；409 时丢弃已读分页重新开始，最多重试一轮后说明变化过快，避免无限循环。不要合并不同版本当作同一时刻的全市场。

状态响应和单股响应可能跨一次更新；单股研究以股票响应 meta 为行情依据，另一次状态请求只做诊断。研究 helper 正是这样处理。
