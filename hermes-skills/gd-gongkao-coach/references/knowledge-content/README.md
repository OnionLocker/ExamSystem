# 网页知识点内容维护（Hermes 定点入口）

用户逐个讨论知识点。只有明确要求新增、扩展、修改、改名、移动、删除内容时才写入；概念交流直接回答。

学习状态和网页上的知识债是另一条记录：Hermes 只负责围绕用户当前指定的知识点交流或修改内容，不代替用户点击学习状态。用户确认“我已学过”后，之后的新错题才算知识债；旧记录保留作历史证据。

## 最短操作路径

在 `/home/ubuntu/ExamSystem` 运行：

```bash
# 用户已指定完整三级标签，不要先搜索全库
node scripts/knowledge-content.mjs outline '数量关系-数学运算-概率问题'
# 只读目标正文，返回 revision 与 node
node scripts/knowledge-content.mjs get '数量关系-数学运算-概率问题' equal-groups
# 将补丁写入 /tmp/knowledge-patch.json 后提交，保存即生效，无需 build
node scripts/knowledge-content.mjs apply '数量关系-数学运算-概率问题' /tmp/knowledge-patch.json
```

只知道名称时：`node scripts/knowledge-content.mjs find '概率'`。已有 `-@equal-groups` 形式的定位时，`@` 前是三级标签，后是稳定节点 ID；可以直接 get，无需 outline。

`outline` 只给目录；`get 标签 节点ID` 只给该页。首次确实需要重组整个知识点时才用 `get 标签`。不要读取其他知识点或学习数据库。

## 补丁格式

```json
{
  "revision": 0,
  "op": "update",
  "id": "equal-groups",
  "markdown": "## 识别信号\n\n各组容量相同。\n\n## 核心公式\n\n$$\nP=\\frac{k-1}{N-1}\n$$\n\n## 例题\n\n10 人均分两组，甲乙同组的概率为 $4/9$。\n\n## 易错提醒\n\n甲已占一个位置，分子分母都减 1。"
}
```

**例子中的 revision 必须替换成刚读取的值。** 标准 JSON 中反斜线写成 `\\`；可用 Python `json.dump` 生成补丁，避免 shell 吃掉 `$` 或反斜线。Markdown 文件本身正常写单个反斜线。

- `create`：提供新的稳定英文小写 `id`、现有 `parentId`、`title`，可附 `summary`、`markdown`、`order`。例如在 `grouping` 下新增 `conditional-grouping`，不挂在总览的同级。ID 不是学习标签，不需要登记画像。
- `update`：只提交本次更改的字段。可更新 `title`、`summary`、`markdown`、`parentId`、`order`。正文是该页完整 Markdown，先 get 后保留未改段落。
- `archive`：只传 revision/op/id，停用这个内容节点及其下级的展示；数据保留，可以 `restore`。先说明网页哪些子页会一起隐藏。**历史作答影响为 0，因为接口根本不访问 exam.db。**
- `restore`：恢复节点；祖先若停用，需先逐层恢复祖先。
- 内容合并：先读取两个目标，将需保留的正文更新到接收页，再 archive 被合并页，每一步使用最新 revision。保留稳定链接与历史版本，不合并画像标签。

输出包含 `changed.id`、`revision`、`changed.linkTag` 和 `evidenceChanged:false`。完成后只简短告诉用户改了哪页、放在哪个父页，并给出 `本题考察知识点：<changed.linkTag>` 供网页跳转。不要声称运行了构建。

409 表示版本冲突：不要覆盖，不重复提交旧补丁。重新读取指定节点，只合并本次意图后用新 revision 提交。同一工具连续失败两次即停下说明，遵守 AGENTS.md。

## 排版规则

- 总览只写模型选择、边界与子考法入口，不塞全部子页正文。
- 方法页讲识别与共性；具体变式挂在方法节点下。
- 每页优先采用：`## 识别信号` → `## 核心公式` → `## 例题` → `## 易错提醒`。
- 公式用 `$…$` 或单独一行的 `$$` 块；中文说明留在公式外。公式中的中文用 `\text{}`。
- 一段只解释一件事；例题把条件、代入、答案分开。不要把长篇中文整段套进数学环境。
- title 简短，不加序号；summary 一句话；先说明公式成立的条件。

## 权限和存储

这是**网页教学内容**接口，只写 `data/knowledge-content.db`，保留每次修改前的版本。不会修改题库、事件、掌握度、画像标签、系统代码或配置；SQL、文件路径和 shell 命令都不是可写字段。不要直接编辑这个数据库。`probability.json` 是初始样例，运行中的修改走 CLI，不能靠改样例覆盖运行数据。

所有已有三级知识点均可维护。新增真正独立的画像标签、合并或删除画像仍按 `knowledge-point-extension.md` 和 AGENTS.md 的证据数量、登记与别名规则办理。显示标题和层级调整不等于改名或合并画像。

系统代码、依赖、构建和部署不属于本接口权限，禁止为知识点内容操作修改 src/server/scripts 或运行 npm build。工具限制不代表整个 Hermes 进程已经处于操作系统沙箱。
