# 项目行为边界

必须遵守本仓库 `AGENTS.md`。Hermes 优先加载本文件时，也必须读取并遵守该文件的权限、快照、工具失败和出题纪律；本文件不授予额外系统代码修改权限。

# 掌握度

任何对话里，只要出现能明确落到对或错的作答证据，立刻记录，不要等 Russell 提醒：

```bash
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' 1 60000 hermes
python3 /home/ubuntu/ExamSystem/scripts/kaodian_profile.py --record '模块-一级-二级' '模块' '一级' 0 90000 exam --exam-id 场次id --item 题号
```

- 做对填 `1`，做错填 `0`；有真实用时就填毫秒数，没有就填 `0`。
- `record()` 会按 Beta(2,2) 先验、21 天半衰期、证据来源权重和有效样本自动重算掌握度与置信度。
- 只有明确作答、复盘能确认对错时才记录；“聊到过”“听懂了”“感觉会了”不算证据。
- **AI 练题复盘只读**：交卷接口已经写入，禁止再 `record()`。
- **录屏/真题复盘必须记**：视频分析本身不落库。带上报告讲解时，对每道有对错的题用 `exam --exam-id <场次id> --item <题号>` 写一次；重复带同一场同一题会 `already recorded`，不要换标签再记。
- 确认是独立新考点时，先用 `--register '模块-一级-二级-子题型' <模块> <一级> [备注]` 把叶子挂在粉笔 L3 下，再用 `--record` 记录本题。
- `--mastery` 仅供 Russell 明确要求人工覆盖分数时使用；Hermes 禁止凭感觉填写 0–100。
- Mastery/profile bookkeeping must run silently in the background. Never show commands, tool output, database-write details, mastery scores, confidence, sample counts, or bookkeeping summaries unless Russell explicitly asks for statistics.

# 出题唯一流程

出题技能以仓库内 `hermes-skills/quiz-pipeline/SKILL.md` 为准，教练规约以 `hermes-skills/gd-gongkao-coach/SKILL.md` 为准。本机 Hermes 的 skill 与仓库同步；可直接读取这些路径或使用对应 skill_view。不要依据旧会话重建另一套流水线。

- 只讨论概念、知识点拆分或学习策略时，不生成题目。用户明确指定模块、知识点、题量、题型和难度时优先服从；推荐纪律只约束 Hermes 自行选择。
- 需要学员状态时，只使用 `python3 /home/ubuntu/ExamSystem/scripts/learner_snapshot.py --compact`。若本轮已附 `[LEARNER_SNAPSHOT]` 快照则直接使用，不重复查询；不直接查库、CSV 或自行拼学情。
- 动态知识点目录：`node /home/ubuntu/ExamSystem/scripts/knowledge-content.mjs catalog '<模块、完整二级或三级标签>'`。按范围查询后编排；指定子点时使用 catalog 返回的精确显示名或稳定 `tag`（三级标签-@节点ID；outline 中为 `linkTag`），不手拼历史超长标签。
- 用户点“最值问题”“工程问题”等父级时，把完整三级标签交给 `quiz_lite.py --tag`，脚本按当前启用的末级子点分配题量。后续新增、拆分、改名、停用立即影响新批次，不硬编码子点清单。指定一个子点时，只练该点；子点之下仍有细分时按其当前末级分配。
- 用户要求更新知识内容时，沿用 `knowledge-content.mjs outline/get/apply`；读取子页用 `get '<完整三级标签>' '<节点ID>'`，不能把节点ID单独当标签传入；apply 的首参数也必须是完整三级标签。生成前脚本会登记所选稳定叶子定义并冻结本批口径。Hermes 不为网页子页临时造另一套画像标签，也不把讨论当作作答或已掌握。
- 正式生成入口为 `python3 /home/ubuntu/ExamSystem/scripts/quiz_lite.py --module '<模块>' --tag '<父级或精确子点>' --count <题量> --difficulty <easy|mid|hard> --batch-id '<日期_hermes_考点_唯一序号>'`。需要核对实际子点分配时先加 `--plan-only`，只返回计划、不生成或入库。
- 点名知识点但未指定题量默认 5 题；数量未指定难度时省略命令和槽位的 difficulty，专用数量流程自由命题并按实际评档（auto），不得擅自补成全 mid。言语未指定难度也为 auto，以练到指定知识点为主，easy/mid/hard 仅作命题倾向，不因难度边界退题，不强求复杂干扰；单题按两位审核较低评级记录，卷名保留请求档位，未指定为综合。政治、常识同样 auto 并按实际较低评级保存，难度仅作倾向；文字逻辑判断同样默认 auto，难度只作倾向，独立核查答案唯一性和推理，不强制算式、固定步骤或复杂干扰；资料仍默认 mid；仅点政治模块默认 10 题、常识默认 5 题。数量口径不变：easy与mid严格区分，hard槽接受mid或hard、不接受easy。用户明确要求配额时保留请求槽位与题量，实际评级不虚标。显式配额或难度组合使用 `--blueprint` 的 slots（tag/count/difficulty，可加 brief），不同时传 --tag/--count；总题量 1–15，同一批只包含一个模块。题量小于子点数时不得声称全部覆盖。
- 数量日常练习默认 auto。“广东省考难度”“贴近真题”“稍难一点”“多点基础题”都是命题倾向，不等于指定 mid/hard；保留 auto，用 blueprint 槽位的 brief 传达原话并注明“命题倾向，非硬性难度门槛”，不得仅因实际评为 easy 退题。只有用户明确指定档位或难度配额（如“全部中等”“三道困难题”）才设置 easy/mid/hard；不改用户题量，不把十题擅自降为五题。
- 正式生成必须 terminal 后台运行，`background=true`、`notify_on_complete=true`。脚本负责出题、独立盲解、考官审核、补题、签收据和入库；不要自己写 questions.json、手跑 generation_gate/import-batch，失败不得绕过。等待后台 JSON 的 status=success 后才能报告 batch_id 和实际 imported 数量，“已开始”不代表完成。
- 批次号必须唯一，不能覆盖已有题。显示名称由脚本按当前目录生成：父级用 `广东省考行测-{模块}-{父知识点}-{难度}-{YYYYMMDD}`，指定子考法则在父级后、难度前追加该子点当前全名。难度用“简单／中等／困难／综合”之一；easy/mid/hard 分别对应前三档，多档混合或 auto 用“综合”（不承诺各档配额）。不简写知识点、不把“综合”粘到知识点名、不显示“自主难度”；父级配额卷不冒充首个子点，加入当天计划也不覆盖名称。
- 政治理论、常识判断先按 `quiz-pipeline/references/politics-common-workflow.md` 核验权威原文，运行 `policy_sources.py status`；缺源先补源，不能靠模型记忆或搜索摘要编造事实。政治支持判断/单选/多选，常识为单选。
- 图形推理、空间推理、科学推理使用粉笔/已有外采真题，不启动图题生成器或实验模式。
- 资料分析整套必须走 agent-paper 高质量通道，禁止用 parallel runner 出整套：凡是 20 题、4 篇、“一套/整套”、广东省考/默认难度的资料分析请求（语音或文字、网页或 TUI）一律后台运行 `scripts/ziliao_agent_paper.py --workers 2 --import`（完整命令见 `quiz-pipeline/SKILL.md`「默认粤考整套」），成功须 passed=true 且 imported=20。`ziliao_parallel_runner.py` 只做单篇 5 题或指定资料考点专项（至多 2 篇 10 题），脚本会拒绝整套请求，并同样强制资料清单硬检查。不自动恢复日练。
- 对话默认不打印新题题干、选项或答案；成功直接按回执简报批次和题量，不再查库确认；如报难度，用actual_difficulty_counts说明实际分布，不能把请求hard说成实际全hard。失败原样说明脚本错误。工具连续失败两次停止；上游错误或回答截断必须告知，等用户要求继续，不静默重试。

# 复盘与质量反馈

复盘来源、逐题模板、客观作答去重、过程评估和封存按 `gd-gongkao-coach` 执行。用户已给出的原题、答案和草稿是证据，不得凭聊天印象编成绩或掌握度。AI 练题已自动记录的证据禁止重复 record；补充过程评估与复盘封存不等于新增作答样本。

用户指出出题跑偏或质量问题时，查实际生成参数、冻结考点定义与审核证据，修复通用流程并用新的正常请求生成新批次验证；不能把修补过的一份题当作整条流水线恢复稳定的证明。

# 复盘重做打包

这是独立任务，放在新会话里做。先读取用户选中的 AI 练题复盘报告；没有报告路径或场次 id 时，请用户在 Hermes 里选中那场复盘，不凭旧聊天印象猜题号，也不查数据库。只选报告中确实作答过、需要重新认真做的历史原题：错题/空题、连续未掌握或解题步骤需要重建的题。一次粗心且已掌握、连续两次答对的不入选；合格题 1–15 道即可，不凑数、不生成或改写题目。

通过 `node /home/ubuntu/ExamSystem/scripts/create-redo-pack.mjs` 的标准输入提交 JSON，包含 `title`、`source_session_id`、`reason_summary`、`items`；每个 item 包含报告里的 `question_id`、具体 `reason`、`priority` 和现有 `knowledge_tags`。命令校验题目属于来源场次，成功回执才算创建；不要用需要网页 token 的 API 请求。打包不新增作答证据、不触发复盘封存。完成后告诉用户在「AI 练题 → 复盘重做」查看。
