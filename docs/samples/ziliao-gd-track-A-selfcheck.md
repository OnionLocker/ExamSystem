# 轨 A 实跑验收（2026-09-27）

**本批通过。** Gemini 实际生成4篇材料、20题；完整质量闸门、独立盲解、图表审核及人工逐题核查完成。未入库、未合并、未部署。

- 模型：gemini-3.8-flash-high；批次：20260927_hermes_ziliao_f91707eb。
- 标签：粤考日练-资料分析-mid-20260927。
- [完整题目和解析](ziliao-gd-track-A-20260927.md) · [JSON 原始对象及自检数据](ziliao-gd-track-A-20260927.json)。
- 生成代码：a91d42d；表头重渲染：a94ea69；最终全闸门复核：2d56b79。重渲染未改题干、选项、答案、解析或材料数据。

| 验收项 | 结果 |
|---|---|
| 细节/定位/排除 | 4题，含未提及、统计口径不包括、读图定位 |
| 综合问法 | M01属实 / M02无法推出 / M03正确的有几个 / M04能够推出 |
| 配额 | 细节4、综合4、比重/加减4、增长3、基期/两期比重2、平均/比较2、混合1 |
| 难度 | {1: 4, 2: 9, 3: 6, 4: 1}；来自考官实际评级，未统一写3 |
| 答案 | A/B/C/D各5题 |
| 材料数字 | 表格五列合计核对一致；两个柱图无等差数列或等差增量；金额/增速未混用可比价口径 |
| 图表 | 1表2柱图，标题、标签、数值与正文一致；长表头/分类换行，柱顶留白 |
| 审核 | Gemini独立盲解20/20、逐句解析核查20/20、视觉3/3通过；收据哈希验证通过 |

## 独立复算摘录

| 题号 | 复算 | 对应答案 |
|---|---|---|
| M02-Q2 | 632.1 ÷ (11428.3−632.1) = 5.85484% | B，约5.9% |
| M02-Q3 | 872.4 ÷ 1.104 = 790.2174亿元 | A，790.2 |
| M03-Q2 | 11547.3 × 0.089 ÷ 1.089 = 943.7187亿元 | D，944 |
| M03-Q3 | 57.6 × (0.146−0.104) ÷ 1.146 = 2.11099个百分点 | C，上升2.1个百分点 |
| M04-Q4 | 19.43 ÷ (7.14/1.075 + 12.29/1.042) − 1 = 5.38885% | A，约5.4% |

另外核对了9市五列合计、研发经费总增速（10.262%）、9市平均营收排序、2019—2023年全部增量，以及综合题的数值上下界。M01-Q4精确乘33.3%得54.2124万千瓦；解析用1/3估算约54.3，能唯一选B，属允许的估算。

## 实跑记录与可复现性

原批次目录：/home/ubuntu/ExamSystem/data/manual-ziliao-pr13/2026-09-27/20260927_hermes_ziliao_f91707eb。timing.json记录完整 runner 用时约150秒、首次闸门1次通过。随后在同一套题上重渲染长表头，并重新调用完整 Gemini 闸门。复核曾因盲解返回省略空 issues 列表被拒，已保留失败证据并补回归；独立答案、逐选项依据、唯一性检查仍为必需。

原始题目、材料、计算清单、签发收据及 system/visual 证据保存在批次目录；完整SHA-256见JSON的 acceptance.sha256。之前被拒批次与旧样本回归证据保存在 data/manual-ziliao-pr13/，未混入本样本。

~~~bash
python3 scripts/test_normalize_ai_batch.py
python3 scripts/test_ziliao_tracks.py
python3 scripts/test_quality_gate.py
python3 scripts/test_ziliao_render.py
python3 scripts/ziliao_parallel_runner.py --track gd --count 20 --materials 4 --difficulty mid --no-import --db /home/ubuntu/ExamSystem/data/exam.db --output-dir /home/ubuntu/ExamSystem/data/manual-ziliao-pr13
~~~

运行前按环境已有方式加载 CLIPROXY_API_KEY，不要把密钥写入仓库。轨B继续标为经典计算加练。图表匹配选项图尚未实现。本报告证明本批验收通过，后续批次仍须过闸门。
