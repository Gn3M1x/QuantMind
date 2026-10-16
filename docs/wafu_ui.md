# 日式和风 UI 与图表工作区验收

执行日期：2026-10-16，Asia/Shanghai。现有 Python 3.11.17 `.venv`、Streamlit 1.66.0、Plotly 6.9.0；没有增加运行依赖。

## 参考与设计

用户给定的 TradingView 布局地址返回403 / Chart Not Found；随后实际打开并截图了 [TradingView NVDA 公开图表页](https://cn.tradingview.com/chart/?symbol=NASDAQ%3ANVDA)。参考其主图优先、右侧价格轴、轻网格、OHLC栏、图表控件和分层指标的组织方式。没有接入其行情、账户或交易功能。

整体采用日式和风：暖纸白 `#F6F5F0`、纸色面板 `#FDFCF8`、墨绿 `#293C35`、朱红 `#B55245`，以金茶、灰蓝、淡紫区分均线与指标。印章标识、衬线标题、细边框和区块留白形成研究手帖的视觉。字体使用系统回退，不依赖第三方字体服务。样式在 `quantmind/assets/workbench.css`；原生控件保留键盘与侧栏展开入口。

实现参考 [Plotly 共享轴子图](https://plotly.com/python/subplots/)、[悬停格式](https://plotly.com/python/hover-text-and-formatting/)、[Streamlit segmented_control](https://docs.streamlit.io/develop/api-reference/widgets/st.segmented_control) 与 [原生主题配置](https://docs.streamlit.io/develop/concepts/configuration/theming-customize-colors-and-borders)。

## 行为与边界

- `build_workspace` 复用同一 `Analysis` 的原始 OHLC、完整精度 MA、MACD、RSI 与成交量；K线/MA、成交量、MACD、RSI统一到一个图表。共享分类横轴保留真实日期间距规则，价格轴移至右侧，增加最后收盘色签。
- 双副图760px、单副图640px、仅价量540px。所有副图同步缩放/平移；鼠标悬停显示完整日期和当前面板数据。保留图例开关、滚轮缩放、双击恢复、图片导出与全屏按钮。
- 快捷视窗按最后一条记录回溯1/3/6个自然月，只设置视窗，不裁掉传入记录，不重算研究区间、顶部指标或报告。可切换副图和开关均线，均不会调用行情接口。
- 最大4个自动横轴刻度，使390px页面下含年份日期标签仍可分开。空指标保留NaN/None；没有补行情、改价或提前舍入。
- 保留真实来源、数据截至、已提交范围、接口失败、缓存使用/抓取时间、陈旧警告、未核实单位与日期完整性提示。报告、历史表和数据说明继续使用相同分析快照。
- 本轮没有改动 `market_data.py`、`quality.py`、`storage.py`、`indicators.py`、`analysis.py`、`report.py`。没有提交、推送或创建远端仓库。

## 实际执行的验证

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q app.py quantmind scripts
git diff --check
.venv/bin/python -m scripts.verify_live --symbols 510300 --start 2025-10-16 --end 2026-10-15 --source sina
.venv/bin/python -m scripts.verify_live --symbols 510300 --start 2025-10-16 --end 2026-10-15 --source eastmoney
```

- **离线通过**：最终67 passed in 8.83s。原61项保留；新增共享图表的日期/OHLC不变、四种面板轴匹配、均线开关、自然月视窗、样本不足与报告区间不变检查。AppTest验证切换副图/均线不请求行情、不改变当前标的和报告；默认测试仍禁止真实网络。
- **通过**：依赖兼容、编译与补丁空白检查。第一轮2项新增断言误把MACD识别成MA，已改为明确检查MA5/20/60，最终无失败。
- **真实接口通过**：新浪和东方财富分别独立刷新510300，实际2025-10-16至2026-10-15，各242条展示记录及484条前置历史。抓取时间分别为13:21:19、13:26:35（+08:00）。各自来源独立保存，没有混用两源序列；两源数量单位仍按原有规则标未核实。
- **浏览器通过**：独立Playwright/Chrome实际打开本地8501工作台，查看空状态、查询真实行情、切换视窗/副图/均线、打开历史行情与数据说明、下载Markdown报告。
- **数据对照通过**：浏览器9条轨迹的242个日期逐条等于所选来源真实缓存；OHLC绝对误差容限1e-14，所有均线/指标和缩放成交量与`Analysis`/展示单位变换的绝对误差容限1e-13。5张卡片和下载报告12项指标与相同来源重算一致。
- **交互通过**：1个月视窗从2026-09-15开始，仍保留242条底层记录；4个面板范围都是[224.5,241.8]。实际点击放大后4个范围同为[228.825,237.475]，点击恢复后回到该月视窗。实际悬停显示2026-09-30完整日期与OHLC/MA。
- **布局通过**：1512px、1024px和390px宽度均无页面/主区域横向溢出。手机5卡为两列，控件纵向排列；最终手机日期标签边界实测无交叠。截图分别保留常规屏高和为完整展示页面所用的加长屏高。
- **控制台通过**：最终独立浏览器会话0 Errors、0 Warnings。最初参考站点403及开发服务器重启时的旧会话日志不算入最终会话。

浏览器检查过程中发现并修复了刷新按钮悬浮说明遮挡查询按钮、手机日期刻度挤压；说明改为侧栏常驻文字，图表刻度密度降低。Playwright对隐藏switch输入的直接点击曾超时，改点实际可见的“均线”标签后切换成功。

## 证据与限制

根目录 `output/playwright/`（Git忽略）保存：

- `tradingview-reference.png`：公开参考页。
- `wafu-empty-desktop.png`：留白首页。
- `wafu-workspace-final.png`：最终桌面整页；`wafu-workspace-1024.png`：1024px布局。
- `wafu-workspace-mobile.png`：390×844首屏；`wafu-mobile-full.png`：390px宽度加长截图。
- `wafu-hover-desktop.png`、`wafu-chart-desktop.png`：悬停与图表。
- `wafu-history-desktop.png`、`wafu-report-desktop.png`、`wafu-source-desktop.png`：功能页。
- `wafu-report.md`：浏览器实际下载报告；`wafu-validation.json`：数值/日期/布局核对。

`reports/live_validation_sina.json`、`reports/live_validation_eastmoney.json` 为本轮接口验证；数据、报告、截图均为本地运行产物，不入Git。

本轮浏览器覆盖本机Chrome桌面与窄屏仿真，未测试实体手机、Safari、Firefox或其他操作系统。没有重新进行受控网络故障浏览器演练；相关缓存回退和旧结果清除由原有离线测试回归。交易日历完整性与源字段物理单位仍未严格核实。本地服务启动于 `http://127.0.0.1:8501`；其他机器需按README自行启动。
