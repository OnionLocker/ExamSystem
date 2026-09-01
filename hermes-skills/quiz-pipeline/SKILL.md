---
name: quiz-pipeline
description: >
  出题必经的验证流水线。给用户出任何公考题之前（判断推琄1�7 / 訢�语理规1�7 / 数量关系 /
  资料分析 / 常识判断），必须先加轄1�7 GONGKAO-STYLE 真题内化提纲并取得同考点
  内化提纲出题 + evaluate holdout 抽检，不强制 generate参��包，再依次通过正确性闸门（答案唯一、��辑自洽＄1�7
  和质量闸门（考点明确、贴近真题��干扰项有诊断价值）。全部��过才允许发给用户��1�7
  禁止边出边发，禁止用自我复查代替验证〄1�7
  触发词：出题、����我、来几题、来两道、模拟题、练习题、刷题��测测我、练丢�练��1�7
version: 2.0.0
author: local
license: MIT
metadata:
  hermes:
    tags: [kaogong, 出题, 验证, 盲审, 判断推理, 翻译推理, 题库]
    related_skills: [note-visual-cards]
---

# 出题验证流水线（Quiz Pipeline v2＄1�7

## 这个 skill 为什么存圄1�7

2026-07-30 那次出题，用户连睢�踩了四种坑：

- 丢�道题四个选项**全都推不凄1�7**（题干条件不足），用户白算了 8 分钟
- 丢�道题**三个选项都成竄1�7**（链条��得太多），用户只发现两个，实际有三丄1�7
- 丢�道题**出题者自己把前提翻译反了**，讲解到丢�半才发现
- 用户反复质问「为仢�么你出的题没办法保持唯一选项〄1�7

当天你已经明确承诺过「以后出题一定先自己验一遍所有��项」��1�7
承诺之后的下丢�扄1�7 5 道题里，仍有 3 道有问题〄1�7

**结论：自我复查在你身上不成立〄1�7** 必须换成你无法绕过的外部验证〄1�7

用户的要求是四条，缺丢�不可＄1�7**有意义��接近公考����察到知识点、答案唯丢�**〄1�7
前三条靠质量闸门，最后一条靠正确性闸门��1�7

---

## 铁律（违反任何一条，这次出题就算失败＄1�7

1. **没过两道闸门的题，一道都不许发给用户〄1�7** 不许「先发着，有问题再改」��1�7
2. **不许用自我复查代替验证��1�7** 你的自查已被实证无效〄1�7
3. **审查者永远看不到你标注的答案〄1�7** 给它答案，它就只去确认那个答案对不对＄1�7
   而不会去查��其他三个是不是也对」，而后者才是真正出问题的地方��1�7
4. **脚本或审查��说不��过，就是不通过〄1�7** 不许自己推翻结论〄1�7
5. **不许在自己的上下文里审自己��1�7** 审查必须发生圄1�7 `delegate_task` 的独立上下文里��1�7
6. **能形式化的题型必须形式化〄1�7** 有决定��手段时改用投票是偷懒��1�7

---

## 五步流程

### Step 0 先确定��点，不要上来就写题

丢�道题只��一个��点。开工前先明确写出来＄1�7

    本次考点：判断推琄1�7-翻译推理-逆否命题
    难度：三层链＄1�74 个条仄1�7
    出题依据＄1�7<用户刚问的1�7 / 用户上次错的 / 错题表统讄1�7>

考点从哪来（按优先级）：

1. 用户当场指定的1�7
2. **考点画像里的薄弱炄1�7** —��1�7 以学员快煄1�7 / `learner_snapshot.py` 为准，不要凭上一场聊天记忆猜〄1�7
   先看同族 `family_days_since`（这丢�大类朢�近一次练过几天），再看本炄1�7 `days_since`、掌握度和置信度＄1�7
   - 用户当场点名：可以出，但必须结构变式，禁止同场景换数字��1�7
   - 同族距上欄1�7 ≄1�7 1 天（今天或昨天刚练过这一大类）：**不当本批主攻**。最多按「一主一辅��盲盒混兄1�7 2 道结构变式��1�7
     排列组合的基硢�原理 / 特殊模型 / 反面容斥算同丢�族；日期推算与周期排班算同一族��1�7
     快照里标了��刚练过不宜主攻」的，不要再把它写成主攻方向〄1�7
   - 同族距上欄1�7 ≄1�7 2 天且仍是高置信弱项：优先作为本批主攻〄1�7
   - 已稳定且 14 天内刚出过：跳过，改选下丢�个弱项��1�7
   禁止只因为某点子点掌握度低，就在新会话里把刚刷完的同丢�大类再出丢�整批〄1�7
3. 用户朢�近对话里暴露的薄弱点（比如反复问「除非否则����么翻译＄1�7
4. **真题考点汄1�7** —��1�7 `~/.hermes/skills/productivity/gd-gongkao-coach/references/zhenti-kaodian-map.md` §3＄1�7
   按权重分从高到低选��画像还空的时��（用户没刷够题），就从这里挑高权重考点铺开〄1�7
5. 错题衄1�7 `mistakes`，按 `wrong_count` 倒序、`mastered=0` 过滤〄1�7**表可能是空的**，空就跳过��1�7

**资料分析例外（用户不会点到三级）＄1�7**不要让用户点 `模块-丢�纄1�7-二级` 里的第三级，也不要从
`zhenti-kaodian-map` 的��综合分析��当 `tags[0]`。默讄1�7 **广东日常 4 範1�7 × 5 预1�7 = 20 预1�7**＄1�7
`paper_style=gd`。国耄1�7 / 深圳 / 拔高 **只在用户显式点名旄1�7**才换卷种。先看快照再组包＄1�7

```bash
python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --compact
python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --ziliao-pack
```

`--ziliao-pack` 吐出 4 篇：每篇 5 个知识库主标筄1�7 + 材料形��1�7 + **5 题答案序**〄1�7
每篇槄1�7 1 较轻，槽 2 1�74 跟画像弱项，槄1�7 5 收束。跨篇��点尽量不重复，10 张出题卡不够 20 槽时才复用��1�7
答案序按考场习惯＄1�74 篇里恰好 3 篇是 A/B/C/D 各出现一次��多出来那题随机重复；剩丄1�7 1 篇故意打散，避免考生死磕「缺哪个字母」��1�7
先算定��，再把正确项排到指定字母，不要为了凑字母改数字〄1�7
速算三张卡和「每题四步��只写进解析，不单独占槽〄1�7
每篇末题可以出综合判断句，但 **禁止** `资料分析-综合分析-综合判断`；`tags[0]` 打在正确项最重的那张卡上〄1�7

### Step 0.5 定��点之后，先查真题��么考这个点

**这一步不许跳〄1�7** 凭印象写出来的题会��像公��题但不是公考题」��1�7

先加载两份持久化内化结果＄1�7

    skill_view("quiz-pipeline", "references/reference-style-principles.md")
    skill_view("quiz-pipeline", "references/reference-style-profile.md")
    skill_view("quiz-pipeline", "references/module-hard-rules.md")  # 广东各模块卷面硬规则+【GATE】清单，出题必读
    # ������ԭ��������ʱǿ�ƶ�ȡ

`reference-style-principles.md` 是从参��题归纳的命题动作与禁忌＄1�7
`reference-style-profile.md` 是按当前数据库自动重建的真实长度、设问��图片和来源分布〄1�7
新会话不能凭记忆概述，必须实际读取��1�7

同时读取 `references/quality-feedback.md` 的全部有效回归规则��写每道题前先在内部划清＄1�7

    已知信息：题干可以直接提供什乄1�7
    目标推导：��生必须自己识别或推出什乄1�7

目标推导不得换一种说法泄露回题干。用户指出过的失败模式必须跨题型回归，不能只避开原句〄1�7

首��真题参考库昄1�7 `/home/ubuntu/ExamSystem/data/exam.db` 的1�7 `reference_questions`＄1�7
佄1�7**禁止再直掄1�7 `ORDER BY RANDOM()` 随便抽题**〄1�7

默认丢�扄1�7 **10 预1�7 = 2 道同考点真题 + 8 道原刄1�7**（资料分析除外，见上＄1�74 材料 × 5 = 20 原创）��1�7
用户明确要求“全原创/all-original”时＄1�710 题全部原创，不执行下面的真题入批步骤；有 holdout 的考点家族做 evaluate 抽检，没有则按考纲模拟题入库。原先：但每一道题仍必须被相互隔离的1�7 evaluate holdout 覆盖（generation_contexts 可省略）。不得把用户指定的全原创悄悄改回 2+8〄1�7
资料分析挄1�7 `--ziliao-pack` 的1�7 20 个槽位写题，不必硬塞真题进批次；每个槽位尽量 evaluate holdout，无则按考纲模拟入库，不必叄1�7 generate context〄1�7
其他模块在非全原创模式下写草稿前先抽真题＄1�7

```bash
python3 /home/ubuntu/ExamSystem/scripts/reference_style.py practice \
  --tag '<规范主标筄1�7>' \
  --count 2 \
  --output /tmp/quiz-practice.json
```

把返回的 `questions` **原样**写入本批 `questions.json`，保畄1�7 `origin: "zhenti"` 和原 `external_id`〄1�7
不够 2 道就有几道用几道，再用原创补刄1�7 10。真题不改写、不进正确��1�7/质量闸门＄1�7
`generation_contexts` / `evaluation_contexts` 的1�7 `question_ids` 只挂 8 道原创��1�7

8 道原创以内化提纲为准，禁止 `ORDER BY RANDOM()`。

出题先读 `reference-style-principles.md` 和 `reference-style-profile.md`（`GONGKAO-STYLE-v1`）。
不要为每道原创再跑 `--role generate` 堆真题。草稿写完后，按主标签抽检 holdout：

```bash
python3 /home/ubuntu/ExamSystem/scripts/reference_style.py context \
  --role evaluate \
  --category '<顶层模块>' \
  --sub-category '<参考库细分类，可空>' \
  --tag '<规范主标签>' \
  --count 1 \
  --images '<yes|no|any>' \
  --output /tmp/quiz-reference-evaluate.json
```

该命令会自动发现并内化后续新加或被修改的题，返回 `style_marker` 对应的
`marker`、`context_id`、`reference_ids` 和留出真题。
`evaluation_contexts` 覆盖能抽到 holdout 的原创；库中没有同考点家族 holdout 时按考纲写模拟题并入库。`generation_contexts` 可省略。
若仍调用 `--role generate`，其 context_id 与 reference_ids 不得与 evaluate 重叠。
取不到匹配 holdout 就跳过该标签的 evaluate 包，按考纲写模拟题并继续入库，不许改槽空转

带图参��题必须同时读取返回值中 `stem_images[].local` 和��项 `images[].local` 的实际图片，
不能只看文字猜图。参考题只用于学习设问��信息密度��认知步骤与干扰项结构，
**严禁复制题干、数字��实体��人物关系或连续选项措辞**。��择器先在参考库内按标签层级回���＄1�7
缺类时才会回逢� `data/zhenti/*.json` 中有答案、无缺图的文字题〄1�7

对照 principles 与 profile，看1�7 `source_tier` 区分角色，看三件事：

1. **设问句式** —��1�7 照抄省������辑判断固定「以下��项如果为真，最能����的是（    ）����，
   资料分析综合分析：广东用「根据资料，以下说法可以判断属实的是＄1�7    ）����，国��用「能够从上述资料中推出的是（    ）����1�7
2. **题干长度与信息密庄1�7** —��1�7 对照 `reference-style-profile.md` 的1�7**广东目标分位**，不要用国��长度��1�7
3. **干扰项��么设的** —��1�7 省��看错在哪一层；国��看是否还少丢�步推导或少一个可命名错因〄1�7

**广东省��硬约束（真题实测，违反即废题）＄1�7**
- **不出定义判断** —��1�7 广东从不考，只有国������1�7
- **不出类比推理** —��1�7 2024 年起已取消��1�7
- 模块配比挄1�7 2026 卷：政治10 / 常识5 / 訢�评1�715 / 数量15 / 判断20 / 科推5 / 资料20〄1�7
- 带图题型只在图像确有必要时启用文朄1�7 D 路；不需要图就不要为了��好看��配图��图形推理��科学推理装罄1�7/受力/电路题和依赖空间关系的几何题不得再降级成含糊文字题��1�7

考点没定清楚就写题，出来的必然是「大杂烩题��，用户做完不知道自己弱在哪〄1�7

**考点字段硬约束：**草稿 `questions.json` 的1�7 `tags` 必须包含丢�个规范主标签，格式为
`模块-丢�级知识点-二级知识点`。数量关系必须用知识卡片上的三级名，例如
`数量关系-逢��必有的排列组合与概玄1�7-特殊模型（八大情形与同组概率）`＄1�7
**禁止**只写 `数量关系-数学运算-排列组合`。资料分析必须用
`gd-gongkao-coach/references/solver-canon/07-ziliao.md` 的主标签，例妄1�7
`资料分析-ABRX籄1�7-基期量计算与比较`＄1�7**禁止**再写 `资料分析-基期釄1�7-基期量计算`〄1�7
`资料分析-综合分析-综合判断`。校验器会把 `knowledge_point` 当作
`tags[0]` 的后备，但入库只冄1�7 `tags`，两个都写时仄1�7 `tags[0]` 为准〄1�7
政治理论和常识判断的丢�级��二级词表以
`gd-gongkao-coach/references/solver-canon/01-zhengzhi.md` 丄1�7 `02-changshi.md` 为准＄1�7
解析中展示的标签、题庄1�7 `tags`、复盘写兄1�7 `kaodian_profile` 必须逐字丢�致��可以另外保留真题原始标签，但不能用原始标签替代规范主标签��1�7
如果用户薄弱点或真题出现词表未收录的新��点，先挄1�7 `gd-gongkao-coach/references/knowledge-point-extension.md` 登记，确认它不是旧标签同义词后再出题；登记后的标签必须原样复用��1�7


### Prompt 调教与从零验收（用户反馈质量时强制）

当用户要求改善后续出题质量时，目标是调教生产线，不是修成当前题：

1. 当前失败批次只用于提炼缺陷，不得直接修改后作丄1�7 Prompt 合格证明〄1�7
2. 把缺陷抽象写入本抢�能和 `quality-feedback.md`，并同步强化 ExamSystem 审查提示〄1�7
3. 删除或隔离失败题，用用户日常会说的简短请求重新从零生成新批次；不得在重生成请求中列出旧题号��正确答案或逐题补丁〄1�7
4. 新批次必须独立获叄1�7 evaluate holdout contexts（generate 可省略）、完整运衄1�7 v3 gate，再由无答案考生视角和命题人视角终验〄1�7
5. 只有未经定向修补的新批次通过，才可宣呄1�7 Prompt 达标〄1�7

写题前还必须完成以下内部预检＄1�7

- 言语按公考“最恰当”标准命题，不追求其余三项脱离比较时绝对不能成立。两次无答案盲解须选出同一答案；竞争项可以局部合理，但在完整语境中必须明显次于答案。若两个选项同等恰当则整题丢弃。
- 言语材料可使用公考常见的政策、科普和文化主题；只拦截明显失实、内部矛盾、把特定结论无条件泛化以及宣传套话过密。正确项可以概括结论句，但不能逐字照抄；错项不得主要靠多个极端词送分。每道原创题必须写 analysis。
- 画像回退：先读取 learner snapshot。言语没有足够样本时使用均衡诊断分布，覆盖逻辑填空、语句表达、主旨/意图/标题、细节和下文推断；不臆造弱项。
- 批次不可复用：每次新请求创建全局唯一 batch_id，不覆盖或重签先前批次。
- 逻辑：前提题必须做否定代入，且仅用题干事实即可使结论失去成立基础；解析不得额外补入死亡��失效��崩溃等后果。整批不得复用相同归因骨架或相同三类错项〄1�7
- 科学：只用稳定教材事实或在题内闭合的假设。接触��浸没��连通��受力点、测量位置和截至时间必须显式闭环。精确装置图必须脚本绘制，中文用 Noto CJK、变量数字用 DejaVu Sans；实际打弢�原图咄1�7 320px 图检查乱码��重叠��端点及接线。`image_only_facts` 不得复述题干，删图后必须无法作答〄1�7
- 参��题：标签只是����索引，必须读取实际正文和图片确认同丢�题型、同丢�认知操作或同丢�科学原理；没有精确参考就换��点，不能用相邻知识点凑数��1�7

### Step 1 写草稿，不要叄1�7

写成结构化文件，字段严格挄1�7 `/home/ubuntu/ExamSystem/docs/IMPORT_SPEC.md`（注意：题干字段丄1�7 `stem`；题目类型为 `"single"`/`"multi"`/`"judge"`；`options` 必须丄1�7 `[{"key": "A", "text": "..."}]` 结构；答案字段为 `answer`）：

    /home/ubuntu/ExamSystem/batches/draft-<YYYYMMDD-HHMM>/questions.json

AI 生成批次的1�7 `manifest.json` 必须包含基础必填字段（`batch_id`, `source`, `region`, `year`）并写入真题参��溯源；先填生成参��包，质量审查完成后再补评测参��包＄1�7

```json
{
  "batch_id": "<YYYYMMDD_模块名_序号>",
  "source": "广东省��行浄1�7 · <专项描述>",
  "region": "广东-省直",
  "year": 2026,
  "kind": "ai-generated",
  "generation": {
    "style_marker": "GONGKAO-STYLE-v1",
    "batch_constraints": {
      "all_original": true,
      "question_count": 10,
      "tag_counts": {"<规范主标筄1�7>": 2},
      "image_dependent_count": {"min": 5, "max": 7},
      "no_images": false,
      "answer_max_per_letter": 5,
      "answer_min_letters": 3
    },
    "generation_contexts": [
      {
        "context_id": "<Step 0.5 返回>",
        "reference_ids": ["<Step 0.5 返回的1�7 external_id>"],
        "question_ids": ["<使用该��点参��包的生成题 external_id>"]
      }
    ],
    "evaluation_contexts": [
      {
        "context_id": "<Step 3 独立审查者返囄1�7>",
        "reference_ids": ["<Step 3 返回的1�7 external_id>"],
        "question_ids": ["<由该评测包审查的生成预1�7 external_id>"]
      }
    ]
  }
}
```

`batch_constraints` 必须按用户原话固化本批数量��全原创模式、各规范主标签题数��带图题范围和答案位置边界；纯文字批次写 `no_images: true`。系统会机械比对，不能只写在聊天戄1�7 source 描述里��1�7
同批题涉及多个��点时，每个考点分别叄1�7 reference context，并在两丄1�7 contexts 数组中分别登记；
两套数组都必须覆盖本批全郄1�7**原创预1�7**。`origin=zhenti` 的真题不进参考包、不进闸门��1�7
相同考点的多道原创可以共用一欄1�7 context〄1�7
不许手写或复用旧 context ID。导入器会到 `reference_context_runs` 反查角色、版本和题目列表＄1�7
伪����漏填��遗漏某道生成题或把同一丄1�7 context 同时用于生成与评测都会拒绝导入��1�7

圄1�7 Step 4 拿到两道闸门都��过的结论之前，丢�个字都不要发给用户��1�7
用户催的时��就说��正在验证，马上」��1�7

### Step 2 准备系统可机械复核的产物

Hermes 只负责草稿和结构化输入，不得自己冄1�7 PASS 结论＄1�7

- A 路形式��辑：无霢�手写结论。ExamSystem 会发起两次相互独立的 Gemini Flash 形式化，再分别交组1�7 `scripts/verify-logic.py` 穷举判定；两次必须得到同丢�唯一答案〄1�7
- B 路数釄1�7/资料：必须写 `calculations.json`。每题含 `question_id`、`correct`、四丄1�7 `options` 表达式及可��1�7 `tolerance`；表达式只能用数值��四则运算��幂叄1�7 `abs/min/max/round/sum/sqrt`。系统亲自计算正确����四项��和唯一匹配项��1�7
- C 路言语��非形式逻辑和无图概念科学：无需写审查结论��ExamSystem 会发起两次互不共享上下文的盲解，两��必须与标准答案丢�致且都未发现第二个可成立选项〄1�7
- D 路图形推理和依图科学：每题必须写兄1�7 `image-specs.json`，包各1�7 `question_id`、`image_facts`、`image_only_facts`、`must_derive`。`image_only_facts` 至少丢�项，表示只能从图中读取且题干没有重复写出的必要已知信息��ExamSystem 会把实际原图咄1�7 320px 图分别交给命题人视角与无答案考生视角的1�7 Gemini Flash 多模态检查��1�7

B 路文件示例：

```json
{"questions":[{"question_id":"Q001","correct":"120/1.2","options":{"A":"90","B":"100","C":"110","D":"120"},"tolerance":0.01}]}
```

D 路文件示例：

```json
{"questions":[{"question_id":"Q001","image_facts":["图中有两只定滑轮"],"image_only_facts":["绳端从右侧绕凄1�7"],"must_derive":["绳端移动方向"]}]}
```

### Step 3 获取独立评测参��包

按每个规范主标签独立运行＄1�7

```bash
python3 /home/ubuntu/ExamSystem/scripts/reference_style.py context   --role evaluate   --category '<顶层模块>'   --sub-category '<参��库细分类，可空>'   --tag '<规范主标筄1�7>'   --count 3   --images '<yes|no|any>'   --output /tmp/quiz-reference-evaluate.json
```

把真实返回的 `context_id`、`reference_ids` 和所覆盖题号写进 manifest 的1�7 `evaluation_contexts`。它们不得与生成上下文复用；有 holdout 的题无重复映射，无 holdout 的题可省略 evaluate〄1�7

### Step 3.5 ExamSystem 统一系统门禁

```bash
python3 /home/ubuntu/ExamSystem/scripts/generation_gate.py issue   /home/ubuntu/ExamSystem/batches/<batch_id>
```

该命令不是读叄1�7 Hermes 写的“已棢�查��文字，而是 ExamSystem 自动执行＄1�7

1. 按题型分叄1�7 A/B/C/D 正确性路线；
2. 甄1�7 evaluate-only 真题样本和全部质量回归规则��题评分＄1�7
3. 寄1�7 D 路实际图片做命题亄1�7/考生双视角多模��检查；
4. 对资料分析图表额外执行原图与 320px 图表专项门禁＄1�7
5. 抄1�7 questions、manifest、materials、calculations、image-specs、全部图片和系统证据的哈希写兄1�7 v3 回执〄1�7

任一预1�7 REJECT，命令即失败，但会保畄1�7 `evidence/system-quality.json`。只根据其中具体原因修改被拒题；同一题最多返俄1�7 2 轮，笄1�7 2 轮仍失败就删除并换题。任何修改后都要重新跑完敄1�7 gate，不能只审改单项，也不能手写或复刄1�7 PASS 证据〄1�7

### Step 4 交付＄1�7**完全盲盒：只报批次名与题量，严禁预告考点**＄1�7

**交付方式已升级为「完全盲盒��（用户强要求）＄1�7**

正确做法：先偄1�7 Step 5 落库，然后只发这样一条消息：

    已出奄1�7 10 题，批次＄1�720260826_shuliang_advanced_02
    兄1�7 10 题��1�7
    厄1�7 ExamSystem ↄ1�7 AI 练题 弢�练��1�7

**严禁**在交付消息中列出考点、题型分布��知识点矩阵或解法特征，避免用户在做题前产生心理预设。全维度考点拆解与复盘分析一律留到用户交卷后再展弢�〄1�7

**硬��交付与排版规范（用户强要求）：**
1. **后台静默验证**：所有的验证过程（形式化、代码验算��双人盲审等）必须完全在后台静默进行。在对话丄1�7**严禁展示任何验证细节、��辑公式、脚本输出��校验状态或答案**〄1�7
2. **绝对禁止 LaTeX 语法**：在对话输出与��辑解析丄1�7**严禁使用 LaTeX 数学公式语法**（如 `$\rightarrow$`、`$\neg$`），因为前端 UI / 终端无法渲染 LaTeX，会导致直接输出原始代码〄1�7**必须统一使用纄1�7 Unicode 逻辑符号**（如 `→`、`¬`、`∧`、`∨`）��1�7
3. **不要催问、不要预告答桄1�7**。发完批次名就停，等用户做完回来说��1�7

用户答完后再给解析（规1�7 Step 6）��判定器输出的1�7 `counterexample`（前提成立但该��项为假的那组赋值）
是最好的讲解材料，直接用〄1�7

> 例外：用戄1�7**明确评1�7**「直接发在这里����不想去网页」时才在对话里出题��默认一律落库��1�7


### Step 5 落库（用户要反复刷时＄1�7

每次 `/quiz-pipeline` 出完题��两道闸门都过后＄1�7**必须执行这一歄1�7**，否则用户在
网页做题模块看不到这批题，错题数据也无法积累〄1�7

**batch_id 命名规则（更新）＄1�7**
- 支持中文、数字��字母��下划线、中划线，最镄1�780字符
- 例：`20260803_翻译推理强化丢�`、`logic-daily-01`
- 出题前由用户指定或自行按"日期_考点箢�称_序号"拟名

```bash
cd /home/ubuntu/ExamSystem

# Step 5a：格式校验（不改 DB，验失败先修＄1�7
npm run validate:batch -- batches/<batch_id>

# Step 5b：导入（幂等，重复执行安全）
npm run import:batch  -- batches/<batch_id>
```

导入成功后告知用户：**「已入库，批次名＄1�7<batch_id>，共 N 题��去 ExamSystem ↄ1�7 AI 练题 刷题。��1�7**

`validate:batch` 只查格式（枚举��必填��图片路径）＄1�7**不查逻辑也不查质釄1�7**＄1�7
它跟这两道闸门是互补的，三关都要过��1�7

寄1�7 `kind: "ai-generated"` 的批次，校验器还会检查参考溯源字段格式，导入器会反查两次
context 是否真实存在、evaluate context 是否真实存在（generate 可省略）、内化版本和 reference IDs 是否丢�致，
同时校验 `.gate.json` 及两份闸门证据的哈希与全题覆盖；成功导入后再把两欄1�7 context 绑定刄1�7 batch_id〄1�7

导入后题目进 `data/exam.db`，用户在网页竄1�7 **「AI 练题〄1�7** 模块能直接看到并刷题＄1�7
刷题产生的错题数据会回流刄1�7 `mistakes` 表，侄1�7 Step 0 定向出题用��1�7
这个闭环要转起来，题目就得落库����只在聊天里出题，错题数据永远是空的〄1�7

### Step 6 复盘＄1�7**先查数据，再弢�口；查完写画僄1�7**＄1�7

用户说��做完了」��复盘一下����帮我看看��时，进入本步��1�7

**先判定来源，禁止 search_files〄1�7** 本机没有 `sqlite3` 命令，查库用 `python3`〄1�7
- 用户说��上传����PDF」��粉笔����专项智能练习��→ 只打弢� `/home/ubuntu/ExamSystem/data/uploads/`，不要查本步的1�7 `practice_sessions`。排版去 `exam-coaching-gd-provincial`〄1�7
- 用户说��AI练题」��草稿����这场练习��或没提上传 ↄ1�7 才走下面 6a〄1�7
- 消息里已有绝对路径1�7 ↄ1�7 直接打开，不要探查��1�7

#### 6a 弢�口之前，必须先把数据查出来（**不许跳过，不许凭印象讄1�7**＄1�7

**这一步没做就直接分析 = 编����1�7** 用户的作答记录��用时��草稿全在库里，
不查就讲，讲出来的都是套话，用户丢�眼就看得出��1�7

```python
import sqlite3
conn = sqlite3.connect('/home/ubuntu/ExamSystem/data/exam.db')
conn.row_factory = sqlite3.Row

# 1) 朢�近一场练习��注愄1�7 practice_sessions.category 存的就是 batch_id
s = conn.execute("""
    SELECT id, category, total, correct, duration_sec, started_at, ended_at
    FROM practice_sessions ORDER BY id DESC LIMIT 1
""").fetchone()

# 2) 逐题：��了仢�么��对不对、花了多久（用时单位昄1�7**秄1�7**，字殄1�7 time_spent_sec＄1�7
rows = conn.execute("""
    SELECT a.question_id, a.user_answer, a.is_correct, a.time_spent_sec,
           q.category, q.sub_category, q.correct_answer, q.content, q.options
    FROM practice_answers a JOIN questions q ON q.id = a.question_id
    WHERE a.session_id = ? ORDER BY a.id
""", (s['id'],)).fetchall()

# 3) 这场有哪些草稿图（先只取清单，不要��着读图＄1�7
#    表里存的昄1�7 filename，实际路径要拄1�7 data/draft-images/
drafts = conn.execute("""
    SELECT question_id, filename FROM practice_drafts
    WHERE session_id = ? ORDER BY question_id
""", (s['id'],)).fetchall()
# 完整路径＄1�7 /home/ubuntu/ExamSystem/data/draft-images/{filename}
```

拿到之后先看三件事，再决定讲仢�么：
- **用时分布**＄1�7>120s 的是硬啃＄1�7<10s 的是秒��（秒��还锄1�7 = 惯��陷阱，朢�值得讲）
- **错题的1�7 subtype 聚集在哪** —��1�7 是同丢�个��点连错，还是散的1�7
- **对但慄1�7**的题：正确率掩盖了不熟练，这类要点出杄1�7
- **全对时不要敷衄1�7**：仍要结合用时和草稿找方法绕远��涂改��步骤冗余等可改进点〄1�7
- **做得好也不要硬讲**：正确��快速��草稿干凢�的题丢�句确认或直接略过，把篇幅留给能带来��场收益的地方��1�7


#### 6b 草稿图：用户要求复盘旄1�7**就该眄1�7**，但要挑睢�眄1�7

旧规则��不要主动读草稿图��指的是**用户没提复盘时别乱翻**＄1�7
不是「复盘时也不许看」��用户明说复盄1�7 = 授权读图〄1�7

- 评1�7**错题/空题** + **有草稿或用时异常的正确题**，一欄1�7 ≄1�710 张；正确题不能只因答案对就跳迄1�7
- 路径要自己拼：`/home/ubuntu/ExamSystem/data/draft-images/{filename}`
- 甄1�7 `vision_analyze` 逐张分析，问题要具体＄1�7
  「这张草稿的推导链第几步弢�始偏？有没有涂改？符号写法规范吗？��1�7
- 同一张图在一个会话里只读丢�次，后面直接引用结论
- 丢�张图纄1�7 3.7 丄1�7 token 且每轮重叄1�7 —��1�7 扢�以要挑，佄1�7**不是不看**

#### 6c 解析格式

挄1�7 `gd-gongkao-coach/references/answer-parse-template.md`＄1�7
每一道展弢�复盘的题都必须先完整展示原题：`### 笄1�7 N 题` 后用 `> **原题**` 引用块照录完整题干，四个选项写成 `> **A.**` 各占丢�行；题干里的 A、B、C 地点或序号必须留在原句，不得拆行、概述��省略或提前标出正确项��带图题同时明确对应题图。原题后再输凄1�7 `本题考察知识点：模块-丢�级知识点-二级知识点`，并写��为仢�么会错��→【解题流程��→【下次��么做����公式用 `$...$`，与知识点页 Markdown 丢�致��1�7
草稿图看出来的东西要落到具体：是推导错，还是手眼不一致（草稿对但点错选项）��1�7

#### 6d 画像写入（AI 练题只认交卷，复盘只读）

本步只约杄1�7 AI 练题。录屄1�7/真题复盘不走交卷接口，由 Hermes 带上报告时按题写入，规1�7 `gd-gongkao-coach`〄1�7

AI 练题圄1�7 `POST /api/practice/sessions/:id/submit` 交卷时，已经按真实题号����点、正确��和用时把证据写兄1�7 `kaodian_events` / `kaodian_profile`，并重算掌握度��这是该次作答的唯一写入点��1�7

- 复盘阶段**严禁**再次调用 `kaodian_profile.record()`、`register_knowledge_point()`、`set_mastery()` 或直接修改画像表；同丢�场重复复盘任意次数都只能重新生成分析，画像样本数必须不变〄1�7
- 复盘时允许只读查评1�7 `weak_points()` 辅助解释，但不得把��又讲了丢�遍��当成新的作答证据��1�7
- 若发现题目标签本身有误，单独修正题库质量；不要在复盘过程中静默改标签或补记画像事件��1�7

**画像怎么用回出题**：Step 0 评1�7 `weak_points()` 挑��点，读 `last_seen` 避开两周内出过的〄1�7
薄弱考点（正确率 <60% 或连锄1�7 ≄1�72）在下一批题里加倍出，连寄1�7 ≄1�73 次的考点降频〄1�7



---

## 用户反馈如何让后续题目变奄1�7

用户指出题目质量问题时，不能只修当前题：

1. 找到具体失效环节：正确����事实一致��信息泄露��歧义��真题结构或干扰项��1�7
2. 把反馈抽象为跨题型规则，追加刄1�7 `references/quality-feedback.md`；禁止只记题号和原句〄1�7
3. 扫描并修复当前批次中的同类问题��1�7
4. 后续 Step 0.5 写题前和 Step 3 独立盲审时都必须重新执行全部历史规则〄1�7

无法承诺生成模型永不出错，但未经过历史反馈回归的题绝不允许入库��1�7

---

## 打回后��么攄1�7

- 同一道题**朢�多改 2 轄1�7**。第 2 轮还不过射1�7**丢掉**，换个��点重出〄1�7
- 改完必须**重新完整跑一遄1�7 ExamSystem 统一 gate**，不许只验改动的那个选项〄1�7
- 不许把改了三遍还在打回的题硬塞给用户〄1�7

---

## 图形推理 / 带图题：D 路（由系统门禁执行审查）

只在题意依赖图形、装置��受力��电路或空间关系时出图；普��文字题不配装饰图��1�7

1. 写题时先明确 `IMAGE_FACTS`（题干允许直接提供的对象与关系）咄1�7 `MUST_DERIVE`（��生必须自己识别或推出的结论）��1�7
2. 使用 `/home/ubuntu/ExamSystem/scripts/generate-question-image.py` 调用 Gemini Flash 生图。传入的绘图 prompt 只能包含 `IMAGE_FACTS`，严禁包含答案��解析或 `MUST_DERIVE`〄1�7
3. 把每道带图题的两份清单写入批欄1�7 `image-specs.json`，并把实际图放入 `images/`、登记在 `stem_images` 戄1�7 `options[].images`〄1�7
4. 不再甄1�7 Hermes 手动运行旧的 `review-question-images-gemini.py` 后自报��过。`generation_gate.py issue` 会自动读取实际题图和 image-specs，发起彼此隔离的命题人视角��无答案考生视角审查，并同时棢�查原图与 320px 图��任丢�视角不��过就拒绝签发��1�7
5. 图像模型只负责画图，不负责判答案；Hermes 目测、Cursor 目测或手写审查文件都不能替代系统 D 路��1�7

---

## 资料分析材料：表/图走工具，不资1�7 Banana

资料分析的表格��柱状图、折线数捄1�7**不是**图形推理那种装置图��数字必须从同一份原始数据渲染出来，模型生图会改数字、歪坐标〄1�7

出题前先选定卷种，并抄1�7
`references/ziliao-paper-styles.md` 的��共用��1�7+ 对应卷种整节喂给 Gemini Flash＄1�7

| 卷种 | `paper_style` | 何时甄1�7 |
|---|---|---|
| 广东卄1�7 | `gd` | 默认日常 |
| 全国卄1�7 | `gk` | 用户点名国��风格，或要表图密度 |
| 深圳卄1�7 | `sz` | 只要拔高；按 `ziliao-paper-styles.md` 的1�7 sz 节（已对煄1�7 2023 1�72025 深圳卷） |

1. 先在内部写下完整数据表（年份 × 指标），再用代码验算全部选项（B 路第 5 条）。数字是自洽的模拟数，用来练知识点，不抄年鉴〄1�7
2. 纯文字材料：只写 `materials[].content`，不要配装饰图��广东文孄1�7 350 1�7700 字��1�7
3. 表格 / 柱状囄1�7 / 饼图：调用脚本��广东日帄1�7 4 篇必须四种形态都有：纯文字��文孄1�7+表��文孄1�7+柄1�7/饼��文孄1�7+图表且至射1�7 1 题��项是图。未点名拔高时不要改用深圄1�7/国����1�7

```bash
python3 /home/ubuntu/ExamSystem/scripts/render_ziliao_figure.py table \
  --title '衄1�71  1�7' --unit '单位：亿兄1�7' \
  --headers 区域,2022幄1�7,2023幄1�7 --rows '东部,80,92' \
  --out batches/<batch>/images/m-01-table.png

python3 /home/ubuntu/ExamSystem/scripts/render_ziliao_figure.py bars \
  --title '囄1�71  1�7' --ylabel '亿件' \
  --categories 东部,中部,西部 \
  --series '2022幄1�7:80,25,15' '2023幄1�7:92,30,18' \
  --out batches/<batch>/images/m-01-bars.png

python3 /home/ubuntu/ExamSystem/scripts/render_ziliao_figure.py pie \
  --title '囄1�72  1�7' --slices '快充,27' '慢充,18' \
  --out batches/<batch>/images/m-01-pie.png
```

4. 材料图写兄1�7 `materials[].images`；��项图（饼图结构、柱形对比）写入该题 `options[].images`。禁歄1�7 `generate-question-image.py`、禁歄1�7 Banana〄1�7
5. 20 道题的1�7 `tags[0]` 甄1�7 `--ziliao-pack` 吐出的知识库主标签，不要自己发明粗标签��1�7
6. 每题 `answer` 必须等于 `--ziliao-pack` 该槽的指定字母��先算定值再排��项〄1�74 篇须恰好 3 篇为 ABCD 各一 + 1 随机＄1�71 篇打散��1�7
7. Flash prompt 必须完整附上 `ziliao-paper-styles.md` 的��共甄1�7+对应卷种」以叄1�7 `quality-feedback.md` 的资料分析回归规则；只改项目说明文档不算生效〄1�7
8. 广东材料默认 4 段��1�7420 1�7650 字��正文不放模拟数据免责声明，不用政策口号填篇幅；每篇至少 3 段数据进入本篇题目，全卷至少 2 道跨段综合判断��1�7
9. 为每题先冄1�7 `正确列式 + A/B/C/D 对应错误路径`。三个错项必须来自三种不同��可复算且有材料依据的错误；禁止随机邻近值或两个错项同属“取错分子����1�7
10. B 路除20题答案外，还要验分项合计、基现期、单位��图表输入和全部60个错误项。再做整卷结构指纹检查，禁止跨材料复用同丢�未知量��设问和错误路径〄1�7
11. 逐主标签尽量取得 evaluate context（--count 1）并映射题号；无 holdout 则省略该标签、不改槽；若同时提供 generate 包，二��样本不得重叠；带图题的 evaluate context 使用 `--images yes` 并实际读取图片��图表按320px宽检查，文字、单位和刻度不小亄1�712px，图片内不重复写选项字母。多系列异单位图必须把单位分别绑定在系列名或独立坐标轴上，禁止使用��万人次/亿元”式合并轴标题��数据标签必须与柱顶、折线��坐标轴、网格线和其他文字保持清晰间距；发生任何遮挡即���回��签叄1�7 gate 旄1�7 ExamSystem 会自动运衄1�7 `scripts/ziliao_visual_gate.py`，直接调甄1�7 Gemini Flash 棢�查全部原图与 320px 考生视图，并校验图片哈希；不得用当前 Hermes 戄1�7 Cursor 的目测代替��1�7
12. 双闸门��过后默认执衄1�7 `npm run import:batch -- <batch>`；若批次各1�7 `read-spot-packs.json`，再执行 `npm run sync:read-spot`，使合格资料进入找数池��1�7

---

## 禁止项汇怄1�7

- 禁止边出题边发给用户
- 禁止用自我复查代替脚本判定或独立盲审
- 禁止把标注答案��解析��你的��向透给任何审查耄1�7
- 禁止在对话中展示验证细节、验证状态����辑公式或提前泄露答案（必须后台静默验证＄1�7
- 禁止输出任何 LaTeX 语法（如 `$\rightarrow$`、`$\neg$`）；对话框与解析必须统一使用纯文朄1�7/Unicode 符号（`->`、`!`、`且`、`或`＄1�7
- 禁止出��肯后断链��死题：已知条件绝对不能给推导链末端的肯定后件（例如给已矄1�7 $B$ 去推 $A \rightarrow B$），因为肯后推不出任何必然结论，会导致链条在第一步就死掉、无答案可推
- 禁止在能资1�7 A/B 路时改走 C 跄1�7
- 禁止两名盲审结论分歧时自己拍杄1�7
- 禁止跳过 Step 0 直接写题
- 禁止用��应该没问题」��大概率正确」结束流稄1�7

---

## 翻译推理已知回声（R029）

- 正确项不得复述或同义改写题干「已知/现已知」实例。
- 必须走逆否、选言否定肯定或连锁；单步逆否可以通过，零步回声必须打回。
- 主语保持「某企业/某团队」，不得把结论写进主语。
- `scripts/verify-logic.py` 对仅被实例前提蕴涵的正确项返回 `echo_given_fact`，A 路视为不通过。
