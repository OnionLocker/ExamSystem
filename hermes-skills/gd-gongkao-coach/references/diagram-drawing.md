# 讲解示意图（画图能力）

用途：讲知识点、复盘错题时，用一张图把“结构”讲清楚。图由脚本按固定模板画，Hermes 只负责选模板、填数字。
ExamSystem 网页里的 Hermes 面板会直接显示图片；终端里只能看到图片链接。

## 什么时候画（自己判断，不用等用户要求）

画：结构本身就是难点，文字很难一眼看清时。按考法选模板：

| 结构 | 模板 | 典型考法 |
|---|---|---|
| 集合重叠 | `venn2` / `venn3` | 两集合、三集合容斥，“只/仅/恰好”辨析，切片方程；翻译推理里“有的/所有”的集合关系 |
| 部分与整体 | `bar` | 反向极值、比例分配、和差倍比、工程分量、牛吃草存量与消耗、资料分析构成拆分 |
| 直线位置与运动 | `line` | 相遇追及、多次往返、流水行船、年龄差、植树间隔 |
| 环形位置与运动 | `circle` | 环形跑道同向追及、反向相遇、钟表指针 |
| 排位与格子 | `slots` | 排列组合：捆绑、插空、隔板、特殊位置优先、错位排列 |
| 分步与分类 | `tree` | 概率分步乘法、不放回抽取、对立事件；分类计数；比赛晋级路径 |
| 推理链 | `chain` | 翻译推理串联、逆否、“只有…才…”方向辨析 |
| 混合比例 | `cross` | 浓度混合、平均分混合、增长率混合（十字交叉） |
| 二维表格 | `grid` | 古典概型样本空间（骰子、抽牌）、匹配推理打勾表、日历/周期、循环赛对阵 |
| 时间安排 | `gantt` | 工程交替/中途加入/中途离开、统筹安排、分段计时 |
| 几何图形 | `geometry` | 平面：三角形、矩形、圆与扇形、阴影面积、勾股、相似；立体：长方体/正方体切割与拼接、圆柱、表面积与体积 |

不画：
- 一行公式就能算完的题（图只会拖慢考场动作，正文里直接说“这题不画图”）。
- 模板表达不了的结构。不要改用 ASCII 字符画、表格拼图或 Mermaid 代替，宁可不画。
- 图形推理、空间推理、科学推理的题图。本能力只画讲解示意图，不是出题生成器，不改变这些模块的出题限制。

数量：一次回答通常 0–2 张，复盘整场最多 3 张，挑最能说明问题的题。

## 怎么画

一次调用出一张图，规格用 JSON 从标准输入传入：

```bash
python3 /home/ubuntu/ExamSystem/scripts/draw_diagram.py --slug rongchi-q3 <<'EOF'
{ ...规格... }
EOF
```

- 成功：输出 `{"ok": true, "markdown": "![标题](/q-images/diagrams/...svg)", ...}`。把 `markdown` 字段**原样**单独成段贴进回答，放在对应讲解之前。不要改路径，不要写成绝对文件路径或代码块。
- 失败：输出 `{"ok": false, "errors": [...]}`。通常是数字对不上（例如某圈各块加起来不等于题目给的总数）——这说明你的解题数字算错了，先重算，再改规格重画。不要为了出图去改题目条件；两次仍失败就不放图，正文照常讲。
- `--slug` 用英文或拼音短词，如 `rongchi-q3`、`xingcheng-xiangyu`。

## 通用字段

| 字段 | 说明 |
|---|---|
| `template` | `venn2` `venn3` `bar` `line` `circle` `slots` `tree` `chain` `cross` `grid` `gantt` `geometry` |
| `title` | 一句结论，≤18 字，例如“三集合切片：先钉中心 w” |
| `subtitle` | 出处或条件，≤24 字，例如“10月7日第3题 · 70人” |
| `notes` | 0–3 行算式或一句关键提醒，第一行加粗；大段讲解写正文，不写进图 |

区域、段、箭头都可以带 `role`，决定颜色：
- `base`（默认）米色：普通区域
- `given` 金色：题目直接给的量
- `key` 赭色：解题突破口（设的未知数、先钉的中心）
- `answer` 深棕：所求
- `dim` 淡色：与本题无关、可以忽略的区域

一张图里 `given` / `key` / `answer` 各用 0–2 处，别把所有区域都上色。

## venn2 两集合

区域键：`a` 只A，`b` 只B，`ab` 两者都，`none` 都不。

```json
{"template":"venn2","title":"两集合：问“仅环境”要再减交集","subtitle":"10月7日第9题 · 120家",
 "names":{"A":"操作规范 64","B":"环境卫生 44"},
 "sets":{"A":64,"B":44},"total":120,
 "regions":{"a":{"v":46,"text":"仅操作\n46"},
            "b":{"v":26,"text":"仅环境\n26","role":"answer"},
            "ab":{"v":18,"text":"都有\n18","role":"given"},
            "none":30},
 "notes":["120 − 30 = A + B − 18 → A + B = 108","仅环境 = 44 − 18 = 26"]}
```

- 区域可以直接写数字（`"none":30`），也可以写 `{"v":数值,"text":"显示文字","role":...}`。`text` 里用 `\n` 换行，每行 ≤5 个字。
- 未知量可以只写文字不写 `v`，例如 `{"text":"x","role":"key"}`；这时该区域不参与验算。
- `sets` 写题目给的各集合总数，`total` 写全集。写了就会验算：每个圈的区域之和必须等于 `sets`，所有区域加 `none` 必须等于 `total`。数字都已知时一定要写上，让脚本帮你验算。

## venn3 三集合

区域键：`a` `b` `c` 只一项；`ab` `ac` `bc` 恰好两项（花瓣，不含中心）；`abc` 三项都（中心）；`none` 都不。

```json
{"template":"venn3","title":"三集合切片：先钉中心 w","subtitle":"10月7日第3题 · 70人，都不参加8人",
 "names":{"A":"公文 40","B":"数据 26","C":"调研 29"},
 "sets":{"A":40,"B":26,"C":29},"total":70,
 "regions":{"a":{"v":18,"text":"仅A\n18","role":"answer"},"b":{"v":8,"text":"仅B\n8"},"c":{"v":8,"text":"仅C\n8"},
            "ab":{"v":7,"text":"x=7","role":"given"},"ac":{"v":10,"text":"z=2w\n=10","role":"given"},
            "bc":{"v":6,"text":"y=6"},"abc":{"v":5,"text":"w=5","role":"key"},"none":8},
 "notes":["B圈 − C圈：y 消掉 → 2w = 10","A圈：a + 7 + 10 + 5 = 40 → a = 18"]}
```

讲公式型（标准型 vs 非标准型）时，可以不写数字，只写“被数几次”：例如花瓣 `"text":"×2"`、中心 `"text":"×3"`；标准型把三片花瓣和中心都标 `given`（两两交集含中心），非标准型只把花瓣标 `given`、中心标 `key`。

## bar 分段条形

```json
{"template":"bar","title":"四项都过至少 32 人","subtitle":"10月7日第5题 · 没过的人尽量错开",
 "total":120,
 "segments":[{"label":"公文没过","value":12},{"label":"数据没过","value":22},
             {"label":"沟通没过","value":25},{"label":"应急没过","value":29}],
 "rest":{"label":"四项都过","role":"answer"},
 "brackets":[{"from":0,"to":88,"label":"没过人次 88"}],
 "total_label":"120 人",
 "notes":["120 − (12 + 22 + 25 + 29) = 32"]}
```

- `segments` 按从左到右的顺序排，`value` 必须是数字，合计不能超过 `total`。
- `rest`：自动把剩下的部分补成一段。
- `brackets`：在条形上方画括号，`from` / `to` 是累计刻度（从 0 开始）。
- 段太窄放不下文字时，标签会自动移到条形下方。

## line 线段图

```json
{"template":"line","title":"相遇：两人合走一个全程","subtitle":"AB 相距 60 km，甲 4 km/h，乙 6 km/h",
 "length":60,
 "points":[{"at":0,"label":"A"},{"at":24,"label":"相遇点"},{"at":60,"label":"B"}],
 "arrows":[{"from":0,"to":24,"label":"甲 4×6 = 24","role":"given"},
           {"from":60,"to":24,"label":"乙 6×6 = 36","row":-1,"role":"key"}],
 "notes":["相遇时间 = 60 ÷ (4 + 6) = 6 h"]}
```

- `length` 是数轴总长，`points[].at` 必须在 0 到 `length` 之间。
- `arrows` 的 `from` → `to` 决定箭头方向；`row` 为 1、2 时画在线段上方，为 -1、-2 时画在下方。同方向的多段运动放在同一侧的不同行。

## 图里文字的写法

图片里的字原样显示，不渲染公式。排列组合写 `A(4,2)`、`C(9,2)`，分数写 `3/5`，幂写 `2^3`，乘号用 `×`。
不要用 `$...$`、`\frac` 等 LaTeX，也不要用 ₂ ₄ ⁴ 这类上下标字符（脚本会拒绝并提示）。正文里照常用 LaTeX。

## circle 环形跑道

```json
{"template":"circle","title":"环形反向相遇：合走一圈","subtitle":"跑道 400 m，甲 3 m/s，乙 5 m/s，同点反向",
 "length":400,
 "points":[{"at":0,"label":"起点"},{"at":150,"label":"相遇"}],
 "arcs":[{"from":0,"to":150,"label":"甲 150 m","role":"given","ring":1},
         {"from":400,"to":150,"label":"乙 250 m","role":"key","ring":2}],
 "center":"400 ÷ (3+5) = 50 s"}
```

- `length` 是一圈长度；位置从顶部起点 0 开始顺时针计。
- `arcs`：`from` → `to` 增大是顺时针，减小是逆时针（反向跑就从 `length` 往回写）。单段不能满一圈，跑了几圈写进 label，弧只画最后不满一圈的部分。
- `ring` 1、2、3 让多条弧分层不重叠；`center` 写在圆心，放一行关键算式。

## slots 格子与位置（排列组合）

```json
{"template":"slots","title":"捆绑法：甲乙相邻先绑成一个","subtitle":"5 人排队，甲乙必须相邻",
 "items":[{"text":"甲","role":"key"},{"text":"乙","role":"key"},"丙","丁","戊"],
 "bundles":[{"from":0,"to":1,"label":"内部 A(2,2) = 2","role":"key"}],
 "notes":["看成 4 个元素全排：A(4,4) × A(2,2) = 48"]}
```

- `items`：1–14 个格子，从左到右；可写字符串或 `{text, role}`。
- `bundles`：把相邻几格框成一组（捆绑），`from` / `to` 是格子序号，从 0 开始。
- `gaps`：标记空位。`"all"` 是包括两端的全部空位（插空），`"inner"` 是只算中间的空隙（隔板），也可以写序号列表，0 表示最左边。
- `gap_style`：`"insert"` 画三角表示插空（默认），`"divider"` 画竖线表示隔板。`gap_label` 写一句说明，例如“4 个空里选 2 个：A(4,2) = 12”。
- `captions`：每格下方的小字，例如特殊位置优先时写每格的可选数“3种”“4种”，个数必须和 `items` 一样。

插空示例：`{"template":"slots","items":["男","男","男"],"gaps":"all","gap_label":"4 个空里选 2 个放女生：A(4,2) = 12"}`
隔板示例：`{"template":"slots","items":["书","书","书","书","书","书","书","书","书","书"],"gaps":"inner","gap_style":"divider","gap_label":"9 个空隙插 2 块板：C(9,2) = 36"}`

## tree 树状图（概率分步、分类计数）

```json
{"template":"tree","title":"不放回抽两次，至少一红","subtitle":"袋中 3 红 2 白","check":true,
 "root":{"label":"开始","children":[
   {"edge":"3/5","label":"红","children":[
      {"edge":"2/4","label":"红","role":"answer","result":"3/5×2/4 = 3/10"},
      {"edge":"2/4","label":"白","role":"answer","result":"3/5×2/4 = 3/10"}]},
   {"edge":"2/5","label":"白","children":[
      {"edge":"3/4","label":"红","role":"answer","result":"2/5×3/4 = 3/10"},
      {"edge":"1/4","label":"白","role":"dim","result":"2/5×1/4 = 1/10"}]}]},
 "notes":["至少一红 = 1 − 两白 = 1 − 1/10 = 9/10"]}
```

- 最多 4 层、16 个叶子；分支太多时只画一支代表，其余写在正文里。
- `edge` 写在分支线上，可以是概率（`3/5`、`0.4`、`40%`）或方法数（`C(3,1)`）。
- `check: true`：检查每个节点下各分支概率之和是否等于 1。概率树一定要开。
- `result` 写在叶子右侧，放这一路的乘积。不发生的情况标 `dim`。

### 分类决策树（题型识别、考法选择）

知识点总览里“先看题干特征，再选考法”这类分流图，同样用 `tree`。用 `levels` 给每层加列标题，`result_title` 给右侧口诀加标题，`legend: false` 关掉颜色图例（这里颜色不表示“题目给的/关键量”）：

```json
{"template":"tree","title":"工程问题：先看题干特征，再选考法","subtitle":"总量 W = 效率 P × 时间 T","legend":false,
 "levels":["","题干特征","考法"],"result_title":"口诀",
 "root":{"label":"工程问题","role":"key","children":[
   {"label":"静态平稳施工","children":[{"label":"基础特值型","role":"given","result":"给时间赋总量 / 给比例赋效率"}]},
   {"label":"循环轮班交替","children":[{"label":"交替轮流与周期","role":"given","result":"打包整周期 + 步进扣余量"}]},
   {"label":"多方案或人员变动","children":[{"label":"多方案与人员分段变动","role":"given","result":"总量守恒列方程"}]}]}}
```

每个节点建议不超过 12 个字，口诀不超过 16 个字；列宽按最长的文字自动排，整图太宽时脚本会报错，按提示缩短文字即可。

## chain 推理链（翻译推理）

```json
{"template":"chain","title":"翻译推理：串成链，再逆否",
 "rows":[{"label":"原链","nodes":["A",{"text":"B","role":"key"},"C"],"edges":["",""]},
         {"label":"逆否","nodes":["非C",{"text":"非B","role":"key"},"非A"],"edges":["",""]}],
 "notes":["肯前必肯后，否后必否前；肯后、否前推不出"]}
```

- 每行 1–6 个节点，最多 5 行，箭头一律从左指向右。
- `edges` 是箭头上方的小字，例如“只有…才…”的翻译依据；不需要就写空字符串，个数等于节点数 − 1。
- “或”“且”这类关系直接写进节点，例如 `"A 或 B"`。

## cross 十字交叉（混合比例）

```json
{"template":"cross","title":"十字交叉：浓度混合求比例",
 "a":{"name":"甲","label":"甲溶液","value":20},"b":{"name":"乙","label":"乙溶液","value":50},
 "mix":{"label":"混合后","value":30},"unit":"%",
 "notes":["差值交叉：离混合值越近的，用量越多"]}
```

- 脚本自动算两个差值并约成最简比，最后一行写出“甲 : 乙 = 20 : 10 = 2 : 1”。混合值必须严格介于两者之间，否则报错。
- 平均分混合、增长率混合同样适用，`unit` 改成“分”或留空。

## grid 二维表格

```json
{"template":"grid","title":"两颗骰子点数和为 7","row_title":"第1颗","col_title":"第2颗",
 "rows":["1","2","3","4","5","6"],"cols":["1","2","3","4","5","6"],"count_role":"answer",
 "cells":[["","","","","",{"text":"7","role":"answer"}],
          ["","","","",{"text":"7","role":"answer"},""],
          ["","","",{"text":"7","role":"answer"},"",""],
          ["","",{"text":"7","role":"answer"},"","",""],
          ["",{"text":"7","role":"answer"},"","","",""],
          [{"text":"7","role":"answer"},"","","","",""]],
 "notes":["P = 6 / 36 = 1/6"]}
```

- 行、列表头各 1–12 个；`cells` 必须是“行数 × 列数”的二维数组，空格写 `""`。
- `count_role`：自动统计该颜色的格子数，写出“所求 6 格 / 共 36 格”。
- 匹配推理打勾表：行写人，列写职业，格子写 `✓`（role 用 `answer`）或 `✗`（role 用 `dim`）。日历题：列写星期，格子写日期。

## gantt 时间条（工程、统筹）

```json
{"template":"gantt","title":"工程交替：甲先干 3 天，乙再加入","subtitle":"总量 60，甲效率 4，乙效率 6",
 "length":9,"unit":"天",
 "rows":[{"label":"甲","segments":[{"from":0,"to":3,"label":"独做 12","role":"given"},
                                    {"from":3,"to":7.8,"label":"合作","role":"base"}]},
         {"label":"乙","segments":[{"from":3,"to":7.8,"label":"合作 48 ÷ 10","role":"key"}]}],
 "marks":[{"at":3,"label":"乙加入"},{"at":7.8,"label":"完工"}],
 "notes":["60 − 4×3 = 48，48 ÷ (4+6) = 4.8 天"]}
```

- 每行一个人或一台机器，最多 8 行；`segments` 必须满足 0 ≤ from < to ≤ length。
- `marks` 画竖线，标出加入、离开、完工等关键时刻。
- 统筹题（如烧水泡茶）每个工序占一行，能同时进行的工序时间段会上下重叠，一眼就能看出可以并行的部分。

## geometry 几何图形

用坐标描述图形，脚本负责缩放、上色、标点名。**坐标按题目的真实尺寸取**，例如长 8 宽 5 的长方形就是 (0,0)、(8,0)、(8,5)、(0,5)，这样验算才有意义。

平面示例（阴影三角形）：

```json
{"template":"geometry","title":"同底等高：阴影三角形是长方形的一半","subtitle":"长方形 ABCD 长 8、宽 5，E 在 CD 上",
 "points":{"A":[0,0],"B":[8,0],"C":[8,5],"D":[0,5],"E":[3,5]},
 "polygons":[{"points":["A","B","C","D"],"role":"base"},
             {"points":["A","B","E"],"role":"answer","label":"S = 20","check_area":20}],
 "segments":[{"from":"A","to":"B","label":"8","check":8},{"from":"B","to":"C","label":"5","check":5}],
 "notes":["S△ABE = 1/2 × 8 × 5 = 20，E 在哪都一样"]}
```

扇形与弓形（先铺扇形，再用 `dim` 三角形盖住，剩下的就是弓形）：

```json
{"template":"geometry","title":"扇形阴影：四分之一圆减三角形","subtitle":"正方形边长 4，以 A 为圆心画弧",
 "points":{"A":[0,0],"B":[4,0],"C":[4,4],"D":[0,4]},
 "sectors":[{"center":"A","r":4,"start":0,"end":90,"role":"answer"}],
 "polygons":[{"points":["A","B","D"],"role":"dim","label":"三角形 8"}],
 "segments":[{"from":"A","to":"B","label":"4","check":4},{"from":"B","to":"C"},{"from":"C","to":"D"},{"from":"D","to":"A"}],
 "texts":[{"at":[2.55,2.55],"text":"弓形"}],
 "notes":["弓形 = π×4²/4 − 4×4/2 = 4π − 8"]}
```

直角与角度：

```json
{"template":"geometry","title":"勾股定理：3-4-5","points":{"A":[0,0],"B":[4,0],"C":[0,3]},
 "polygons":[{"points":["A","B","C"],"role":"given"}],
 "segments":[{"from":"A","to":"B","label":"4","check":4},{"from":"A","to":"C","label":"3","check":3},
             {"from":"B","to":"C","label":"5","check":5,"role":"key"}],
 "angles":[{"at":"A","from":"B","to":"C","right":true},{"at":"B","from":"A","to":"C","label":"37°","check":36.87}]}
```

立体示例（坐标写 `[x, y, z]`：x 向右是长，y 向上是高，z 向后是宽；脚本按斜二测画法投影）：

```json
{"template":"geometry","title":"长方体切一刀：表面积增加两个截面","subtitle":"长 6、宽 4、高 3",
 "points":{"A":[0,0,0],"B":[6,0,0],"C":[6,0,4],"D":[0,0,4],"E":[0,3,0],"F":[6,3,0],"G":[6,3,4],"H":[0,3,4],
           "P":[3,0,0],"Q":[3,3,0],"R":[3,3,4],"S":[3,0,4]},
 "polygons":[{"points":["P","Q","R","S"],"role":"answer","label":"截面 12"}],
 "segments":[{"from":"A","to":"B","label":"6","check":6},{"from":"B","to":"F"},{"from":"F","to":"E"},
             {"from":"E","to":"A","label":"3","check":3},{"from":"B","to":"C","label":"4","check":4},
             {"from":"C","to":"G"},{"from":"G","to":"F"},{"from":"G","to":"H"},{"from":"H","to":"E"},
             {"from":"A","to":"D","dashed":true},{"from":"D","to":"C","dashed":true},{"from":"D","to":"H","dashed":true}],
 "hide_labels":["P","Q","R","S"],
 "notes":["多出 2 个截面：2 × (3 × 4) = 24"]}
```

圆柱（底面用椭圆，`back_dashed` 把后半圈画成虚线）：

```json
{"template":"geometry","title":"圆柱：侧面展开是长方形","subtitle":"底面半径 2，高 5",
 "points":{"O":[0,0],"O1":[0,5],"L":[-2,0],"R":[2,0],"L1":[-2,5],"R1":[2,5]},
 "ellipses":[{"center":"O","rx":2,"ry":0.6,"back_dashed":true},{"center":"O1","rx":2,"ry":0.6}],
 "segments":[{"from":"L","to":"L1"},{"from":"R","to":"R1","label":"h = 5","check":5},
             {"from":"O","to":"R","label":"r = 2","dashed":true}],
 "hide_labels":["L","R","L1","R1"],
 "notes":["侧面积 = 2πr × h = 2π × 2 × 5 = 20π"]}
```

字段：
- `points`：点名 → 坐标。平面写 `[x, y]`（y 向上），立体写 `[x, y, z]`。所有点都会画小圆点，并自动把点名放在图形外侧；辅助点的名字用 `hide_labels` 隐藏。
- `polygons`：多边形，按顺序连点并填色。`label` 写在中心，`check_area` 验算面积（立体同样按真实三维面积算）。
- `segments`：线段。`label` 写边长，`check` 验算长度，`dashed: true` 画虚线（被遮住的棱、辅助线），`role: "key"` 加粗强调。
- `angles`：`at` 是顶点，`from` / `to` 是两边上的点。`right: true` 画直角符号并验算是否 90°；`check` 验算度数，误差允许 1°。
- `sectors`：扇形，`start` / `end` 是角度，从 x 轴正方向起逆时针计；`circles`：整圆，`dashed` 画虚线；`ellipses`：立体里的圆面。
- `texts`：图上的自由标注，`at` 是坐标位置。
- **数字都写上 `check`**：坐标一旦算错（比如直角其实不是 90°、边长对不上），脚本会拒绝出图并指出哪里错。

画不了：需要精确作出的复杂尺规作图、曲面体切割后的截面形状。这类题用文字讲，或者只画大致结构、不标数字。

## 写进网页知识点页（仅当用户明确要求保存）

网页知识点页同样显示 Markdown 图片。先在聊天里给用户看过图，用户确认后：

1. 只知道名称时用名称查标签，不要查数据库：`node /home/ubuntu/ExamSystem/scripts/knowledge-content.mjs find '容斥'`。
   常用：容斥 → `数量关系-数学运算-容斥原理问题`，子页 `@two-sets`、`@three-sets-formula`、`@three-sets-venn`、`@multi-sets-extremum`。
2. `get '完整三级标签' 节点ID` 读该子页正文与 revision。
3. 把画图返回的 `markdown` 那一行插到正文对应段落（例如“核心公式与模型”标题下方），其余正文原样保留。
4. 按 `references/knowledge-content/README.md` 的补丁格式 `apply`，再 `get` 读回确认图片行和公式都在。

## 自检

- 图里的数字必须和正文讲解一致，和题目条件一致。
- 不要编造题目里没有的数；需要设未知数时，区域里写字母。
- 图片 Markdown 前后各空一行。
