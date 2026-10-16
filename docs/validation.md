# 第一阶段验收记录

这是日期显示与 UI 改版之前的历史记录（当时为 45 项测试、8 张指标卡）。当前版本为 61 项测试、5 张核心卡片；请同时参阅 [UI 改版验收](ui_revision.md) 与 [发布前检查](release_check.md)。源字段单位以 [当前展示规则](data_contract.md#ui修订后的单位展示规则2026-10-16) 为准，下面的价量关系推断不等于物理单位认证。

执行日期：2026-10-16（Asia/Taipei / Asia/Shanghai，UTC+08:00）。这是本机实际执行记录，不保证公开接口未来可用。

## 环境与依赖

| 项目 | 状态 | 实际依据 |
| --- | --- | --- |
| 复用虚拟环境 | 通过 | 项目 `.venv/bin/python` 为 Python 3.11.17；系统 python3 为3.14.6，未使用或升级系统Python |
| 机器 | 通过 | Intel x86_64，macOS15.6.1 |
| 安装依赖 | 通过 | `.venv/bin/python -m pip install -r requirements.txt`；安装后固定实际版本 |
| 兼容性检查 | 通过 | `.venv/bin/python -m pip check` → `No broken requirements found.` |

验证版本：AKShare1.19.1、NumPy2.4.6、Pandas2.3.3、Plotly6.9.0、Streamlit1.66.0、pytest8.4.2。

## 离线自动测试

命令：

```bash
.venv/bin/python -m pytest -q --tb=short
.venv/bin/python -m compileall -q app.py quantmind scripts
```

**通过：45 passed in 4.55s**。最后一次输出保存在 `logs/pytest-final.txt`；编译检查成功。默认测试阻断真实socket连接与真实行情适配器，用人工TEST样本和临时SQLite，不因公开行情源失败而改变结果。

覆盖：规范化、缺字段、坏日期、非数值/非有限值、非正价格、负成交量/额、OHLC关系、重复与未来日期；SQLite更新与删除上游移除行、前导零代码、来源和复权隔离、复权整段替换；覆盖不足与缓存删除缺口补取、断网降级和无缓存失败；进程超时与返回范围；MA完整窗口、Wilder初值及单边/横盘、EMA闭式预期与MACD预热、独立样本方差公式、仅选区回撤和不足样本；图表序列与报告12项数值一致性；Streamlit启动状态、查询成功、成功后查询另一标的失败时清除旧结果、表单修改不自动抓取。

预期指标使用可手算序列或独立闭式公式；测试代码仍全部保留。

## 真实接口

### 新浪实际端到端验证：通过

```bash
.venv/bin/python -m scripts.verify_live --source sina
```

| 代码 | 真实展示区间 | 日线数 | 前置历史 | 价量单位关系核验 | 结果 |
| --- | --- | ---: | ---: | --- | --- |
| 510300 | 2025-01-02～2025-12-31 | 243 | 484 | 727个非零量样本，100%通过 | 通过 |
| 510500 | 2025-01-02～2025-12-31 | 243 | 484 | 727个非零量样本，100%通过 | 通过 |
| 159915 | 2025-01-02～2025-12-31 | 243 | 484 | 723个非零量样本，100%通过；零量行保留提示 | 通过 |

请求范围为2023-01-02～2025-12-31（含预热），实际2023-01-03起。每只成功生成K线/MA/成交量、RSI、MACD共3个Figure（5/1/3条轨迹）、真实CSV和Markdown报告。证据：`reports/live_validation_sina.json`、`logs/live-sina-validation.log`、`data/QuantMind_*_sina.csv`、`reports/QuantMind_*_sina.md`。均为本地运行产物，已Git忽略。

### 东方财富：部分请求通过，带预热请求失败

初次直接调用适配器，510300的2025全年成功返回243条日线，首日2025-01-02（close3.909），末日2025-12-31（close4.753）；新浪同区间首尾OHLC相同，成交量数量级约相差100倍。

随后执行 `.venv/bin/python -m scripts.verify_live --source eastmoney`，三只标的的含预热范围请求均失败，上游错误为 `requests.exceptions.ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`。证据在 `reports/live_validation_eastmoney.json`。没有将这些失败改写成成功，也没有生成模拟行情补位。工作台真实使用时保留该原因，转到新浪获取整段真实数据。

单位核验是价量关系推断；新浪文档“手”与实际数据存在冲突，详见 `data_contract.md`。这一核验不能代替交易所原始数据字典认证。

## Streamlit 与浏览器

| 验收 | 状态 | 实际依据 |
| --- | --- | --- |
| 服务启动 | 通过 | `.venv/bin/python -m streamlit run app.py --server.port 8501`；Streamlit服务监听127.0.0.1:8501；当时验收代码已重新启动 |
| 健康端点 | 通过 | `curl -fsS http://127.0.0.1:8501/_stcore/health` → `ok` |
| 实际页面 | 通过 | Playwright打开真实Chrome页面，中文标题、8项指标、3个Plotly图表可见；修复标题/图例重叠并检查截图 |
| 最终浏览器控制台 | 通过 | 重启服务后的独立Playwright会话：`Total messages: 0 (Errors: 0, Warnings: 0)` |
| 真实查询 | 通过 | 510300：所选2025-10-16～2026-10-15，242条日线，484条预热；东财失败后新浪成功，报告包含来源和原始失败原因 |
| 数值抽查 | 通过 | 收盘4.2420、20日价格收益率−8.52%、年化波动率12.50%、所选区间回撤−16.68%、RSI14为20.5639；界面与下载内容一致 |
| 报告下载 | 通过 | 浏览器点击下载，实际保存4398字节UTF-8 Markdown；解析全部12项指标并与缓存重新计算结果一致，包含来源、复权、日期及收益口径 |
| 表单不自动抓取 | 通过 | 浏览器仅修改ETF选择，SQLite抓取批次7→7，仍显示先前已提交结果；离线AppTest另作覆盖 |
| 失败与样本不足状态 | 通过 | 离线AppTest及核心测试验证；真实浏览器未人为制造网络故障 |

本地浏览器证据：`output/playwright/workbench-final.png`、`output/playwright/downloaded-report.md`，以及 `.playwright-cli/` 中的快照、控制台和下载记录。后续交互、重启与重新抓取会改变页面或抓取批次数，这些数字仅对应本次测试时刻。

## 明确限制和未验证项

- **未验证**：严格交易日完整性。当前没有可靠交易日历，10个自然日范围/间隔只是启发，长假也会再次补取。
- **未验证**：交易所原始字段级单位认证及新浪全部历史权益事件；当前保留单位冲突与推断说明。
- **未验证**：其他操作系统、其他浏览器和持续长期稳定运行；本次只在当前Intel Mac执行。
- **失败**：本次东方财富含预热的批量请求；真实备用源成功，完整本地研究流程可运行。
- **通过**：所有生产报告使用真实数据；人工样本只存在测试路径；未执行Git提交、推送或创建远程仓库。
