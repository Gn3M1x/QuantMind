# 数据接口核对记录

当前展示以文末“UI修订后的单位展示规则”为准；下文价量推断是来源诊断记录，不代表字段单位已核实。

核对环境：2026-10-16，Intel macOS 15.6.1，Python 3.11.17，AKShare 1.19.1。

## 一手依据

- [AKShare 官方基金接口文档](https://akshare.akfamily.xyz/data/fund/fund_public.html#etf)（查看 ETF基金历史行情-东财、基金历史行情-新浪）。
- [AKShare 东财实现源码](https://github.com/akfamily/akshare/blob/main/akshare/fund/fund_etf_em.py)。本机同时通过 `inspect.getsource(ak.fund_etf_hist_em)` 和 `inspect.getsource(ak.fund_etf_hist_sina)` 核对安装版本，线上 main 后续可能改变。
- 实际请求返回的 OHLC、volume、amount，以及成交额/成交量的价格区间关系。

## 东方财富：主要数据源

接口 `ak.fund_etf_hist_em(symbol="510300", period="daily", start_date="20250101", end_date="20251231", adjust="")`。
代码六位字符串，开始结束日期为 YYYYMMDD，`daily` 映射 `klt=101`；`adjust=""`、`qfq`、`hfq` 分别映射 `fqt=0/1/2`，本项目仅请求空字符串（不复权）。

上游 `https://push2his.eastmoney.com/api/qt/stock/kline/get`，沪市 `secid=1.代码`、深市 `secid=0.代码`。字段依次含日期、开盘、收盘、最高、最低、成交量、成交额；本项目显式按字段名规范为 date/open/high/low/close/volume/amount，不按列位置误配。

官方该字段表未标成交量及成交额单位。本项目将价格解释为人民币元/份，以 `amount/(volume×100)` 对照同日 low/high（2% 容差）核验：符合时将 volume 解释为手、1手=100份，amount 解释为元。这是基于价量关系的推断，并非交易所原始数据字典认证；核验不足则标单位未核实，保留原始值。

## 新浪财经：真实备用数据源

接口 `ak.fund_etf_hist_sina(symbol="sh510300")`，沪市 sh、深市 sz 前缀。单次返回全部历史；无日期及复权参数，项目在返回后按日期筛选，不作价格调整。

已安装版本上游为 `https://finance.sina.com.cn/realstock/company/sh510300/hisdata_klc2/klc_kl.js`，用 AKShare 内置 JS 解码器解码。返回 date/open/high/low/close/volume；本次版本实际还返回 amount，存在时保存，缺少时明确标未提供。

**文档冲突**：官方文档将新浪 volume 标为手，但本次 510300 的同日返回约为东财 volume 的100倍；`amount/volume` 落入当日价格区间，故解释为份，保留原始数值、在界面及报告注明推断与冲突，绝不把两来源的原始 volume 直接合并。无复权参数和抽样 OHLC 与东财不复权一致，是本项目使用原始价格的依据；未独立核实全部分红/拆分事件，不宣称验证了全历史权益处理。

## 收益与来源隔离

统一不复权。所有收益仅为收盘**价格收益率**，不含现金分红及再投资；分红、拆分会影响价格连续性、波动率和回撤。每次分析仅使用一个来源，同代码不同来源独立存储，不自动拼接两个来源。

每批记录接口、上游 URL、AKShare 版本、复权、单位及核验说明、抓取时间（Asia/Shanghai 时区）、请求范围与实际覆盖范围。公开接口缺少可信交易日历，不对周末和节假日创造“缺失行”；超过10个自然日的间隔仅触发提示及下次查询补取，不等于确定缺失。


## UI修订后的单位展示规则（2026-10-16）

上文的手/份/元解释是第一阶段保存的关系推断记录，不是已核实单位。本轮重新核对官方文档后，缺省与冲突仍未得到权威字段定义的解决；因此当前展示不会据此转换为“万份/亿元”。

`quantmind/presentation.py`对旧缓存一律按未核实处理。只有适配器提供 `*_unit_verified=True`、合法的 `*_unit_base` 及非空 `*_unit_evidence` 三项时，才显示物理单位。否则采用“万/亿原始单位（未核实）”数量缩写，图表轴可简写为“亿原值”，旁注明确未核实；原始存储、分析结果和报告数值不受影响。测试中使用明确标TEST的权威字段示例覆盖万份、亿份、万元和亿元的格式化，不能把该示例当作生产数据的单位依据。

日期轴仅表示返回记录顺序。不存在周末记录不是完整交易日验证；缺少可靠交易日历时，仍保留范围、记录间隔和数据新鲜度提示，不将所有未返回日期归类为休市。
