# 发布前检查记录

执行日期：2026-10-16。范围为日期显示修复与 UI 改版后的本地源码；本轮只修改 README、历史验收说明及 Git 忽略规则，新增此记录，业务代码与测试未改动。未执行 Git commit、Git push 或创建 GitHub 仓库。

## 结论

**通过：当前源码可以上传 GitHub，未发现阻碍源码发布的问题。** 运行数据、日志、本地报告和浏览器证据不在建议上传范围。此结论针对检查时的文件集合；以后新增文件需要重新检查。

## 实际检查结果

| 检查 | 状态 | 依据 |
| --- | --- | --- |
| 当前代码完整离线测试 | 通过 | `.venv/bin/python -m pytest -q --tb=short` → `61 passed in 6.58s` |
| 干净源码副本 | 通过 | 只复制当时 28 个待上传文件，不带虚拟环境及运行目录；使用现有已验证依赖，移除 `PYTHONPATH`、`QUANTMIND_DB_PATH` 覆盖，确认导入副本源码；同样命令 → `61 passed in 6.06s`。之后仅新增本检查文档 |
| 依赖兼容性 | 通过 | `.venv/bin/python -m pip check` → `No broken requirements found.`；requirements 中 6 个版本逐项与已安装版本匹配 |
| 语法编译 | 通过 | `.venv/bin/python -m compileall -q app.py quantmind scripts` → 退出码 0 |
| 真实验证命令入口 | 通过 | `.venv/bin/python -m scripts.verify_live --help` → 退出码 0；参数与 README 一致 |
| 忽略规则 | 通过 | `git check-ignore --no-index --stdin -z` 检查 45 条路径：27 条运行/敏感配置路径被忽略，18 条源码/离线样本路径可追踪；已追踪的被忽略文件为 0 |
| 敏感内容及文件体积 | 通过 | 最终待上传文件扫描未发现疑似密钥、密码、Token、私钥、带凭证 URL、个人绝对路径、邮箱或手机号；所有候选均为 UTF-8 文本，无符号链接、二进制或超过 2 MiB 文件 |
| README 与本地文档链接 | 通过 | 安装、启动、离线及真实验证命令与实现一致；本地 Markdown 目标文件存在；旧版 45 项记录标为历史，当前 61 项与 UI 验收分别链接 |
| 本轮重新请求公开行情 | 未验证 | 本次发布检查没有发起真实行情请求；保留此前新浪成功、东方财富含预热请求失败的实际记录，见下面链接 |
| 本轮重新执行浏览器流程 | 未验证 | 本轮未修改 UI 业务代码，未重复浏览器验收；1440/1024px、月/年区间、悬停/缩放、下载及受控失败的既有记录见下面链接；本轮 AppTest 随离线测试再次通过 |
| 全新虚拟环境安装 | 未验证 | 复用既有 Python 3.11.17 环境；干净源码测试不等同于从零联网安装依赖 |

原始检查输出保存在本机 `output/release-check/`，已忽略，不随源码上传。Git 当前尚无提交，检查范围是未跟踪、未忽略的候选文件；不存在可扫描的历史提交或已暂存内容。敏感扫描仅记录位置和类型，不保存疑似凭证原文。

## 建议上传清单

共 29 个文本文件：

```text
.env.example
.gitignore
.streamlit/config.toml
AGENTS.md
README.md
app.py
pytest.ini
requirements.txt
docs/
  data_contract.md
  release_check.md
  ui_revision.md
  validation.md
quantmind/
  __init__.py
  analysis.py
  charts.py
  indicators.py
  instruments.py
  market_data.py
  presentation.py
  quality.py
  report.py
  storage.py
scripts/
  verify_live.py
tests/
  conftest.py
  test_adapter.py
  test_chart_dates_presentation.py
  test_indicators_report.py
  test_quality_storage.py
  test_service_app.py
```

`.env.example` 只有无需 API Key 的说明，未包含凭证。测试样本在 `tests/conftest.py` 中人工构造并标为 TEST；它们属于源码验收材料，应保留。

不上传 `.venv/`、Python/pytest 缓存、`.env` 及其本地变体、`.streamlit/secrets.toml`、根目录 `data/`、`reports/`、`logs/`、`output/`、根目录数据库及其旁文件、根目录日志，以及 `.playwright-cli/`、`playwright-report/`、`test-results/`。不使用强制添加将这些运行文件纳入 Git。

## 保留的数据说明与限制

- 数据来源、字段和单位证据见 [数据契约](data_contract.md)。东方财富与新浪缓存隔离，每次分析仅使用一个来源。当前成交量/额的物理单位仍未得到权威定义核实，展示保留“原始单位（未核实）”，价量关系推断不等于认证。
- 统一不复权，收益为价格收益率，**不含现金分红，不是总收益率**；分红、拆分等会影响连续性与统计值。
- 没有可靠交易日历，分类轴只紧凑排列真实返回记录，未严格验证应有交易日完整性；不填造 OHLC。
- 历史真实接口与最初验收见 [第一阶段记录](validation.md)，改版后的实际浏览器验收见 [UI 修订记录](ui_revision.md)。公开接口未来可用性及其他操作系统尚需实际验证。
- 本地截图、真实数据和下载报告未随源码上传；新目录通过工作台查询或独立真实验证脚本生成运行数据。

上述限制已在 README 与界面说明中保留，不阻碍当前本地研究工作台源码发布。
