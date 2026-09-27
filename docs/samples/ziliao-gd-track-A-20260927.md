# 轨 A「粤考日练」样本说明（2026-09-27）

| field | value |
|---|---|
| track | `gd`（粤考日练） |
| source | `粤考日练-资料分析-mid-20260927` |
| model | `gemini-3.8-flash-high`（`ZILIAO_GEMINI_MODEL` / `DAILY_GEMINI_MODEL` / 默认） |
| layout | 4 材料 × 5 题；formats=`text,table,chart,chart` |
| companion | `docs/samples/ziliao-gd-track-A-20260927.json` |

## 本环境实跑状态

本云端 VM **没有** `CLIPROXY_API_KEY`，也没有本机 CLIPROXY（`127.0.0.1:8889` 不可达），因此 **未能用 Gemini 实跑出 20 道题全文**。

本文件交付的是 **轨 A 配额蓝图**（`--plan-only` 真实输出）+ 离线闸门自检。题目正文需在有密钥的正式机/环境按下面命令生成后，才能给学员当验收卷。

## 配额（已写入 runner，离线断言通过）

| 家族 | 本套槽位数 | 目标 |
|---|---:|---|
| 细节定位/排除 `detail` | 4 | 3–4 |
| 综合正误 `judge`（每篇 Q5） | 4 | 4 |
| 现期比重/简单加减 `share_add` | 4 | 3–4 |
| 增长率/增长量 `growth` | 3 | 3 |
| 基期或两期比重 `base_share` | 2 | 2 |
| 平均/比较 `avg_cmp` | 2 | 2 |
| 混合或拉动 `mix_pull` | 1 | 至多 1–2 |

M01 长文字槽位：细节 ×2 + 轻量计算 ×2 + 综合正误 ×1。

四道综合正误题干已按篇锁死，避免再被闸门「至少 2 种问法」拦下：

| 篇 | 形式 | 题干开头 |
|---|---|---|
| M01 | 属实 | 根据资料，以下说法可以判断属实的是 |
| M02 | 无法推出 | 不能从上述资料中推出的是 |
| M03 | 计数 | 根据资料，下列说法正确的有 |
| M04 | 能推出 | 能够从上述资料中推出的是 |

难度分：细节=1、一步比重/加减=2、增长/基期/比较=3、混合与综合=4，禁止全员 3。

## 在有密钥的正式机复现

密钥只放环境变量或 `~/.hermes/.env`，不要写入仓库。

```bash
# 1) 先看配额，不调用模型
python3 scripts/ziliao_parallel_runner.py --plan-only --track gd --difficulty mid

# 2) Gemini 实跑一套（不入库，便于验收）
export CLIPROXY_BASE_URL="${CLIPROXY_BASE_URL:-http://127.0.0.1:8889/v1}"
# CLIPROXY_API_KEY 已在环境或 ~/.hermes/.env
python3 scripts/ziliao_parallel_runner.py \
  --track gd --count 20 --materials 4 --difficulty mid \
  --no-import --batch-id 20260927_ziliao_gd_track_a_live

# 3) 轨 B 仅当用户要经典计算加练时使用（不得标成广东省考综合训练）
python3 scripts/ziliao_parallel_runner.py --plan-only --track classic
```

成功后把 `data/parallel-ziliao/<date>/<batch>/` 下的 `questions.json` / `materials.json` 拷到 `docs/samples/` 再给人看。

## 图表匹配

本轮 **未强制、未假实现**。挂点：`scripts/ziliao_tracks.py` 的 `CHART_MATCH_HOOK` 与 `render_option_figures()`。若未来题目自带 `options[].figure`，程序可渲选项图；配额不因缺图而编造四幅匹配题。
