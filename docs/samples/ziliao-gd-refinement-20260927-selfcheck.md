# 资料分析轨A改进版自检与复核交接

- 日期：2026-09-27；代码 PR：https://github.com/OnionLocker/ExamSystem/pull/14（待复核，未合并部署）
- 批次：20260927_hermes_ziliao_15c7e407
- 线上题组：粤考日练-资料分析-mid-20260927-改进版
- 实跑模型：gemini-3.8-flash-high；4篇材料、20题；已入库，线上逐题内容及3张图片一致。

## 本轮修改

复用既有框架、runner及闸门。统一初次出题与回炉要求，独立审核额外返回设计核验依据；正文口径引用须真的出现在注释之前。比较/平均需要逐个算比值时最多4个明确候选；简单读图/减法比较按真实负担判断。明确区分本期增长量误用A*r与预测下一期增长量正确使用A*r。

材料允许真实精度内的舍入误差，不强制制造0.1–0.3缺口；金额柱图整列整十会拒绝，计数允许整数。水平网格线改为轴上短刻度，保留数字标签，解决视觉反复指出的标签粘连。所有材料本地拒绝也写入证据。

## 样本核查

- 四篇主题：财政收支、规上工业、外贸、社会消费品零售。
- 四篇Q5依次为属实、无法推出、正确的有几个、能够推出。
- M01-Q2只有预算完成率，无金额且无法反推；M04-Q2判断具体经营活动是否纳入社零统计，不复读范围句。
- M02平均题仅做年均增加量，M03比较题为5次简单减法；没有九市逐个算人均。
- M01-Q5、M03-Q5、M04-Q5含百分点与百分比辨析；M02-Q5验证整体大于等于非负部分，不把范围扩大一律判错。
- 三篇图表均有正文未列出的明细取数点，最终视觉验收全部通过。
- 13道数值题独立复算及4道综合题逐项核查通过，见manual-math-checks.json。
- 难度分布：1分4题、2分8题、3分6题、4分2题；答案A/B/C/D各5题。
- family：detail 4、judge 4、share_add 4、growth 3、base_share 2、avg_cmp 2、mix_pull 1。

## 打回与人工干预记录

本轮启动2个批次。0dd83505在材料阶段被人工终止：M02/M04仅在注脚写口径而审查通过，修复正文引用核验后重跑；未入库。

最终15c7e407批次完成6次整套闸门：
1. runner gate-attempts/1：题目审核PASS，M03视觉标签/网格线重叠REJECT。
2. runner gate-attempts/2：金额柱图整列整十，被本地规则拒绝。
3. manual-refinement/gate-1：题目审核PASS，M03视觉REJECT。
4. manual-refinement/gate-2：题目审核PASS，M03视觉再次REJECT。
5. final-validation/gate-1：盲解额外返回空E选项，严格结构校验REJECT，未放宽校验。
6. final-validation/gate-final：全部PASS，签发有效回执后入库。

因此完成的整套验收是5次未通过、第6次通过；不等同于20道题都重写5次。材料阶段的重试另计：初始M02/M03因正文口径缺失打回，M04因反推基期过整齐打回；人工要求M01补真正半给指标、M03换自然精度数据。中间各版在gate-attempts、manual-refinement和final-validation保留。人工还让Gemini重写M04-Q2为具体场景，并修正M02-Q5非负量包含关系的严格不等号。

## 复核范围与证据

本批已入库；本PR代码尚未合并，Hermes线上runner仍是PR13版本。用户可先审核新样本，再决定代码合入。图表匹配chart_match仍未启用。百分比尾数与主题自然度按材料审查判断，没有用固定小数比例替代合理性；精确合计不是自动拒绝项。

批次目录：/home/ubuntu/ExamSystem/data/manual-ziliao-gd-refinement/2026-09-27/20260927_hermes_ziliao_15c7e407

关键文件：sample.md/json、manual-math-checks.json、evidence/system-quality.json、evidence/ziliao-visual-quality.json、import-result.json、final-validation/gate-final/run.json及gate.log。before-import.db为一致性SQLite备份。

离线回归：29项轨道测试、13项工作流测试、quality gate regression、渲染回归全部通过。最终生成代码提交bb58709。
