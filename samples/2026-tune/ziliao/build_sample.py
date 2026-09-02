#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Author + verify one 广东-style 资料分析 sample paper (4 materials x 5 questions).

Review sample for the module-by-module 广东 AI 练题 tuning pass (module 1/N = 资料).
Forms match real 广东省考/粉笔模考: M1 纯文字, M2 文字+表, M3 文字+柱图,
M4 混合(材料表 + 一道选项为柱图的识图题). Figures are rendered with the repo's
scripts/render_ziliao_figure.py (needs CJK font: fonts-noto-cjk).

Numbers are invented but statistical-bulletin "dirty" (decimals / non-round
endings) and self-consistent (分项加总=合计; 现期/(1+r)=基期). Every computed
value + distractor is produced here so the arithmetic is auditable.

Run:  python3 samples/2026-tune/ziliao/build_sample.py
Emits: materials.json, questions.json, images/*.png (next to this script).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
IMG = OUT / "images"
IMG.mkdir(parents=True, exist_ok=True)
REPO = OUT.parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from render_ziliao_figure import render_table, render_bars  # noqa: E402

BATCH = "gd-ziliao-sample-2026tune"
GD_JUDGE = "根据资料，以下说法可以判断属实的是（    ）。"

# canonical 资料分析 primary tags (hermes-skills solver-canon/07-ziliao.md)
QI = "资料分析-基础知识-统计术语与常考概念"
BASE = "资料分析-ABRX类-基期量计算与比较"
DELTA = "资料分析-ABRX类-增长量计算与现期推算"
SHARE = "资料分析-比重类-现期、基期与隔级比重"
SHARE_DIFF = "资料分析-比重类-比重趋势、比重差与比值差"
CMP = "资料分析-比较类-双线法与增量比较"
AVG = "资料分析-平均类-一般平均值与年均增速/增量"

# ─────────────────────────── raw data (dirty, self-consistent) ───────────────────────────

# M1 · G省 邮政快递业 2024（纯文字）
m1 = dict(kd_total=328.61, kd_g=18.94, kd_rev=1423.85, kd_rev_g=14.27,
          zsj=276.52, zsj_g=17.83, ydxb=52.09, ydxb_g=25.34,
          yidi=291.47, tongcheng=21.41, intl=15.73, intl_g=31.62)
assert round(m1["zsj"] + m1["ydxb"], 2) == m1["kd_total"]
assert round(m1["yidi"] + m1["tongcheng"] + m1["intl"], 2) == m1["kd_total"]

# M2 · G省 规模以上文化及相关产业 2024（文字+表）
m2 = dict(total=21867.4, total_g=9.63, manu=9834.2, manu_g=6.71,
          trade=3120.5, trade_g=8.44, serv=8912.7, serv_g=13.28,
          newbiz=7345.9, newbiz_g=18.52, profit=1789.66, profit_g=7.05)
assert round(m2["manu"] + m2["trade"] + m2["serv"], 1) == m2["total"]

# M3 · 全国 货物贸易进出口 2024（文字+柱图）
m3 = dict(total=438957.0, total_g=5.12, exp=253297.0, exp_g=7.06,
          imp=185660.0, imp_g=2.58, priv=244768.0, priv_g=8.83,
          jidian=149371.0, jidian_g=8.71)
assert round(m3["exp"] + m3["imp"], 0) == m3["total"]

# M4 · G省 居民收入与消费 2024（混合：材料表 + 选项为柱图的识图题）
m4 = dict(per=51789.0, per_g=4.73, urban=63847.0, urban_g=4.12,
          rural=26418.0, rural_g=6.35, consume=34926.0, consume_g=5.28, engel=33.7)

# ─────────────────────────── figures ───────────────────────────

render_table(
    "2024年G省规模以上文化及相关产业分领域营业收入",
    ["领域", "营业收入", "同比增长"],
    [["文化制造业", "9834.2", "6.71%"],
     ["文化批发和零售业", "3120.5", "8.44%"],
     ["文化服务业", "8912.7", "13.28%"],
     ["合计", "21867.4", "9.63%"]],
    IMG / "m2_table.png", unit="单位：亿元",
)
render_bars(
    "2024年全国货物贸易主要指标绝对规模",
    "亿元", ["出口", "进口", "民营进出口", "机电出口"],
    [("金额", [253297.0, 185660.0, 244768.0, 149371.0])],
    IMG / "m3_bars.png",
)
render_table(
    "2024年G省居民人均可支配收入与消费支出",
    ["指标", "数值", "名义增长"],
    [["全体居民人均可支配收入", "51789", "4.73%"],
     ["城镇居民人均可支配收入", "63847", "4.12%"],
     ["农村居民人均可支配收入", "26418", "6.35%"],
     ["全体居民人均消费支出", "34926", "5.28%"]],
    IMG / "m4_table.png", unit="单位：元",
)
# Q16 选项柱图：城镇可支配 / 农村可支配 / 人均消费（识图，只有一组数值正确）
_q16_cats = ["城镇可支配", "农村可支配", "人均消费"]
_q16_variants = {
    "correct": [63847.0, 26418.0, 34926.0],
    "swap": [26418.0, 63847.0, 34926.0],          # 城乡对调
    "consume_per": [63847.0, 26418.0, 51789.0],   # 消费错取全体可支配
    "urban_per": [51789.0, 26418.0, 34926.0],     # 城镇错取全体可支配
}
for name, vals in _q16_variants.items():
    render_bars("", "元", _q16_cats, [("金额", vals)], IMG / f"q16_{name}.png")

# ─────────────────────────── materials ───────────────────────────

MATERIALS = [
    dict(
        external_id=f"{BATCH}-M01",
        content=(
            "2024年，G省邮政快递业保持较快增长。全年全省快递业务量完成328.61亿件，"
            "同比增长18.94%；实现快递业务收入1423.85亿元，同比增长14.27%。\n"
            "从业务结构看，异地快递业务量291.47亿件，同城快递业务量21.41亿件，"
            "国际及港澳台快递业务量15.73亿件，其中国际及港澳台业务量同比增长31.62%。\n"
            "分区域看，珠三角九市完成快递业务量276.52亿件，同比增长17.83%；"
            "粤东西北地区完成快递业务量52.09亿件，同比增长25.34%，增速快于全省平均水平。"
        ),
        images=[],
    ),
    dict(
        external_id=f"{BATCH}-M02",
        content=(
            "2024年，G省规模以上文化及相关产业实现营业收入21867.4亿元，同比增长9.63%；"
            "实现利润总额1789.66亿元，同比增长7.05%。分三大领域看的营业收入及增速情况见下表。\n"
            "文化新业态特征较为明显的16个行业小类实现营业收入7345.9亿元，同比增长18.52%，"
            "新业态引领作用进一步增强。"
        ),
        images=["images/m2_table.png"],
    ),
    dict(
        external_id=f"{BATCH}-M03",
        content=(
            "2024年，全国货物贸易进出口总额438957亿元，比上年增长5.12%。\n"
            "其中，出口增长7.06%，进口增长2.58%；民营企业进出口增长8.83%，"
            "机电产品出口增长8.71%。主要指标的绝对规模见下图。"
        ),
        images=["images/m3_bars.png"],
    ),
    dict(
        external_id=f"{BATCH}-M04",
        content=(
            "2024年，G省居民收支保持稳定增长，全省居民人均可支配收入与人均消费支出"
            "情况见下表。\n"
            "全年全省居民恩格尔系数为33.7%，城乡居民人均可支配收入之比较上年继续缩小。"
        ),
        images=["images/m4_table.png"],
    ),
]

QUESTIONS = []


def pct(x):
    return f"{x:.2f}%"


def pp(x):
    return f"{x:.2f}个百分点"


def yi_jian(x):
    return f"{x:.2f}亿件"


def yi_yuan(x):
    return f"{x:.1f}亿元"


def wan_yi(x):
    return f"{x:.0f}亿元"


def yuan(x):
    return f"{x:.0f}元"


def add_calc(qid, material, tag, stem, value, distractors, fmt, explanation):
    # options sorted ascending (广东真题惯例)；正确项字母由数值排名自然落定
    values = [(value, True)] + [(d[0], False) for d in distractors]
    assert len({round(v, 4) for v, _ in values}) == 4, f"{qid} duplicate value: {values}"
    values.sort(key=lambda pair: pair[0])
    options = [{"key": k, "text": fmt(v)} for k, (v, _) in zip("ABCD", values)]
    derived = next(k for k, (_, is_c) in zip("ABCD", values) if is_c)
    assert len({o["text"] for o in options}) == 4, f"{qid} dup text"
    QUESTIONS.append(dict(external_id=qid, category="资料分析", question_type="single",
                          material_id=material, stem=stem, options=options, answer=derived,
                          explanation=explanation, difficulty=2, tags=[tag]))


def add_image_choice(qid, material, tag, stem, letter_to_img, answer, explanation):
    options = [{"key": k, "text": "", "images": [img]} for k, img in letter_to_img.items()]
    QUESTIONS.append(dict(external_id=qid, category="资料分析", question_type="single",
                          material_id=material, stem=stem, options=options, answer=answer,
                          explanation=explanation, difficulty=2, tags=[tag]))


def add_judge(qid, material, tag, options_text, letter, explanation):
    options = [{"key": k, "text": t} for k, t in zip("ABCD", options_text)]
    QUESTIONS.append(dict(external_id=qid, category="资料分析", question_type="single",
                          material_id=material, stem=GD_JUDGE, options=options, answer=letter,
                          explanation=explanation, difficulty=3, tags=[tag]))


# ── M1 · 纯文字 ──
add_calc(f"{BATCH}-Q01", f"{BATCH}-M01", QI,
    "2024年，G省珠三角九市与粤东西北地区快递业务量相差约（  ）亿件。",
    round(m1["zsj"] - m1["ydxb"], 2),
    [(round(m1["zsj"] + m1["ydxb"], 2), "误求和(=全省)"),
     (round(m1["zsj"], 2), "只取珠三角"),
     (round(m1["yidi"] - m1["tongcheng"], 2), "取错行(异地−同城)")],
    yi_jian,
    "【定型找数】读数比较。珠三角九市276.52亿件、粤东西北52.09亿件（第三段）。\n"
    "【列式】276.52−52.09=224.43（亿件）。\n干扰项：误相加、只取珠三角、错取异地与同城之差。")
add_calc(f"{BATCH}-Q02", f"{BATCH}-M01", BASE,
    "2023年，G省快递业务量约为（  ）亿件。",
    round(m1["kd_total"] / (1 + m1["kd_g"] / 100), 2),
    [(round(m1["kd_total"] * (1 - m1["kd_g"] / 100), 2), "误用现期×(1−r)"),
     (round(m1["kd_total"] / (1 + m1["kd_rev_g"] / 100), 2), "错用收入增速"),
     (round(m1["kd_total"] * (1 + m1["kd_g"] / 100), 2), "方向反:现期×(1+r)")],
    yi_jian,
    "【定型找数】求基期量。现期328.61亿件、同比增长18.94%（第一段）。\n"
    "【列式】基期=现期/(1+r)=328.61/1.1894≈276.28（亿件）。\n干扰项：现期×(1−r)、错套收入增速、方向反。")
add_calc(f"{BATCH}-Q03", f"{BATCH}-M01", SHARE,
    "2024年，G省珠三角九市快递业务量占全省快递业务量的比重约为（  ）。",
    round(m1["zsj"] / m1["kd_total"] * 100, 2),
    [(round(m1["ydxb"] / m1["kd_total"] * 100, 2), "取错分子(粤东西北)"),
     (round(m1["zsj"] / m1["yidi"] * 100, 2), "取错分母(异地量)"),
     (round(m1["zsj"] / (m1["kd_total"] - m1["intl"]) * 100, 2), "分母错减国际件")],
    pct,
    "【定型找数】现期比重=部分/整体。珠三角九市276.52亿件、全省328.61亿件。\n"
    "【列式】276.52/328.61≈84.15%。\n干扰项：取错分子、以异地量作分母、分母漏计国际件。")
add_calc(f"{BATCH}-Q04", f"{BATCH}-M01", CMP,
    "2024年，G省快递业务量同比增速比快递业务收入同比增速约高（  ）。",
    round(m1["kd_g"] - m1["kd_rev_g"], 2),
    [(round(m1["kd_g"] + m1["kd_rev_g"], 2), "误求和"),
     (round((m1["kd_g"] - m1["kd_rev_g"]) / m1["kd_rev_g"] * 100, 2), "误算相对差"),
     (round(m1["ydxb_g"] - m1["kd_rev_g"], 2), "错取区域增速")],
    pp,
    "【定型找数】两增速作差得百分点。业务量增速18.94%、业务收入增速14.27%。\n"
    "【列式】18.94−14.27=4.67（个百分点）。\n干扰项：误相加、误算相对差、错取粤东西北增速。")
add_judge(f"{BATCH}-Q05", f"{BATCH}-M01", SHARE_DIFF,
    ["2024年，G省快递业务收入的同比增速高于快递业务量的同比增速",
     "2024年，G省国际及港澳台快递业务量占全省快递业务量的比重超过一成",
     "2023年，G省粤东西北地区快递业务量高于珠三角九市",
     "2024年，珠三角九市快递业务量的同比增速低于全省快递业务量的整体增速"], "D",
    "【逐项】A：收入增速14.27%<业务量增速18.94%，错。\n"
    "B：15.73/328.61≈4.79%<10%，错。\n"
    "C：52.09<276.52且均为正增长，基期同样更低，错。\n"
    "D：珠三角增速17.83%<全省18.94%，跨段可判，属实。故选D。")

# ── M2 · 文字+表 ──
add_calc(f"{BATCH}-Q06", f"{BATCH}-M02", QI,
    "2024年，G省文化制造业营业收入比文化服务业营业收入约多（  ）亿元。",
    round(m2["manu"] - m2["serv"], 1),
    [(round(m2["manu"] + m2["serv"], 1), "误求和"),
     (round(m2["manu"] - m2["trade"], 1), "取错减数(批零)"),
     (round(m2["serv"] - m2["trade"], 1), "取错行")],
    yi_yuan,
    "【定型找数】读表比较。文化制造业9834.2亿元、文化服务业8912.7亿元（见表）。\n"
    "【列式】9834.2−8912.7=921.5（亿元）。\n干扰项：误相加、错取批零业、错取行。")
add_calc(f"{BATCH}-Q07", f"{BATCH}-M02", DELTA,
    "2024年，G省文化服务业营业收入比上年约增加（  ）亿元。",
    round(m2["serv"] * (m2["serv_g"] / 100) / (1 + m2["serv_g"] / 100), 1),
    [(round(m2["serv"] * m2["serv_g"] / 100, 1), "误用现期×r"),
     (round(m2["serv"] - m2["serv"] / (1 + m2["total_g"] / 100), 1), "错用整体增速"),
     (round(m2["manu"] * (m2["manu_g"] / 100) / (1 + m2["manu_g"] / 100), 1), "取错行(制造业)")],
    yi_yuan,
    "【定型找数】求增长量。文化服务业现期8912.7亿元、增速13.28%（见表）。\n"
    "【列式】增长量=现期×r/(1+r)=8912.7×0.1328/1.1328≈1044.8（亿元）。\n干扰项：现期×r、错套整体增速、错取制造业。")
add_calc(f"{BATCH}-Q08", f"{BATCH}-M02", SHARE,
    "2024年，G省文化服务业营业收入占规模以上文化及相关产业营业收入的比重约为（  ）。",
    round(m2["serv"] / m2["total"] * 100, 2),
    [(round(m2["manu"] / m2["total"] * 100, 2), "取错分子(制造业)"),
     (round(m2["serv"] / (m2["manu"] + m2["serv"]) * 100, 2), "分母漏批零"),
     (round(m2["trade"] / m2["total"] * 100, 2), "取错分子(批零)")],
    pct,
    "【定型找数】现期比重=部分/整体。文化服务业8912.7亿元、合计21867.4亿元（见表）。\n"
    "【列式】8912.7/21867.4≈40.76%。\n干扰项：取错分子、分母漏计批零业。")
add_calc(f"{BATCH}-Q09", f"{BATCH}-M02", CMP,
    "2024年，G省文化制造业、文化批发和零售业、文化服务业三个领域中，营业收入同比增速最高的领域，其增速约为（  ）。",
    round(m2["serv_g"], 2),
    [(round(m2["trade_g"], 2), "取次高(批零)"),
     (round(m2["manu_g"], 2), "取最低(制造业)"),
     (round(m2["total_g"], 2), "错取整体增速")],
    pct,
    "【定型找数】三领域增速比较（见表增速列）。制造业6.71%、批零8.44%、服务业13.28%。\n"
    "【结论】最高为文化服务业13.28%。\n干扰项：取次高、取最低、错取整体增速。")
add_judge(f"{BATCH}-Q10", f"{BATCH}-M02", SHARE_DIFF,
    ["2024年，G省文化新业态16个行业小类营业收入增速低于规上文化企业整体增速",
     "2024年，G省文化制造业营业收入占规上文化企业营业收入的比重超过五成",
     "2024年，G省规上文化企业利润总额增速高于其营业收入增速",
     "2024年，G省文化服务业营业收入占规上文化企业营业收入的比重较上年有所提高"], "D",
    "【逐项】A：新业态增速18.52%>整体9.63%，错。\n"
    "B：9834.2/21867.4≈44.97%<50%，错。\n"
    "C：利润增速7.05%<营收增速9.63%，错。\n"
    "D：服务业增速13.28%>整体9.63%，部分快于整体则比重上升，跨段可判，属实。故选D。")

# ── M3 · 文字+柱图 ──
add_calc(f"{BATCH}-Q11", f"{BATCH}-M03", QI,
    "2024年，全国货物贸易顺差约为（  ）亿元。",
    round(m3["exp"] - m3["imp"], 0),
    [(round(m3["exp"] + m3["imp"], 0), "误求和(=总额)"),
     (round(m3["imp"], 0), "错取进口额"),
     (round(m3["exp"], 0), "错取出口额")],
    wan_yi,
    "【定型找数】顺差=出口−进口（读柱图）。出口253297亿元、进口185660亿元。\n"
    "【列式】253297−185660=67637（亿元）。\n干扰项：误相加、错取进口/出口额。")
add_calc(f"{BATCH}-Q12", f"{BATCH}-M03", BASE,
    "2023年，全国货物贸易进出口总额约为（  ）亿元。",
    round(m3["total"] / (1 + m3["total_g"] / 100), 0),
    [(round(m3["total"] * (1 - m3["total_g"] / 100), 0), "误用现期×(1−r)"),
     (round(m3["total"] / (1 + m3["exp_g"] / 100), 0), "错用出口增速"),
     (round(m3["total"] * (1 + m3["total_g"] / 100), 0), "方向反:现期×(1+r)")],
    wan_yi,
    "【定型找数】求基期。现期总额438957亿元（正文）、增长5.12%。\n"
    "【列式】基期=438957/1.0512≈417575（亿元）。\n干扰项：现期×(1−r)、错套出口增速、方向反。")
add_calc(f"{BATCH}-Q13", f"{BATCH}-M03", SHARE,
    "2024年，全国机电产品出口额占出口总额的比重约为（  ）。",
    round(m3["jidian"] / m3["exp"] * 100, 2),
    [(round(m3["jidian"] / m3["total"] * 100, 2), "分母错用进出口总额"),
     (round(m3["jidian"] / m3["imp"] * 100, 2), "分母错用进口额"),
     (round(m3["priv"] / m3["exp"] * 100, 2), "取错分子(民营)")],
    pct,
    "【定型找数】现期比重=部分/整体（读柱图）。机电出口149371亿元、出口总额253297亿元。\n"
    "【列式】149371/253297≈58.97%。\n干扰项：分母错用进出口总额/进口额、分子取民营额。")
add_calc(f"{BATCH}-Q14", f"{BATCH}-M03", CMP,
    "2024年，全国出口额同比增速比进口额同比增速约高（  ）。",
    round(m3["exp_g"] - m3["imp_g"], 2),
    [(round(m3["exp_g"] + m3["imp_g"], 2), "误求和"),
     (round(m3["exp_g"] - m3["total_g"], 2), "错取出口与总额增速差"),
     (round(m3["total_g"] - m3["imp_g"], 2), "错取总额与进口增速差")],
    pp,
    "【定型找数】两增速作差得百分点（正文）。出口增速7.06%、进口增速2.58%。\n"
    "【列式】7.06−2.58=4.48（个百分点）。\n干扰项：误相加、错取出口/进口与总额的增速差。")
add_judge(f"{BATCH}-Q15", f"{BATCH}-M03", SHARE_DIFF,
    ["2024年，全国进口额同比增速快于出口额同比增速",
     "2024年，全国机电产品出口额占出口总额的比重不足五成",
     "2023年，全国货物贸易表现为逆差",
     "2024年，全国民营企业进出口额占货物贸易进出口总额的比重较上年有所上升"], "D",
    "【逐项】A：进口增速2.58%<出口增速7.06%，错。\n"
    "B：149371/253297≈58.97%>50%，错。\n"
    "C：两年出口均大于进口（基期出口≈236595>进口≈180991），为顺差，错。\n"
    "D：民营进出口增速8.83%>总额增速5.12%，占比较上年上升，跨段可判，属实。故选D。")

# ── M4 · 混合（材料表 + 选项柱图的识图题）──
add_image_choice(f"{BATCH}-Q16", f"{BATCH}-M04", QI,
    "下列柱状图能正确反映2024年G省城镇居民人均可支配收入、农村居民人均可支配收入和"
    "全体居民人均消费支出的是（  ）。",
    {"A": "images/q16_correct.png", "B": "images/q16_swap.png",
     "C": "images/q16_consume_per.png", "D": "images/q16_urban_per.png"}, "A",
    "【定型找数】识图核对三项数值（见材料表）：城镇63847元、农村26418元、人均消费34926元。\n"
    "A 柱图三项与表一致，正确。\nB 城乡数值对调；C 人均消费错标为全体可支配收入51789元；"
    "D 城镇错标为全体可支配收入51789元。故选A。")
add_calc(f"{BATCH}-Q17", f"{BATCH}-M04", BASE,
    "2023年，G省农村居民人均可支配收入约为（  ）元。",
    round(m4["rural"] / (1 + m4["rural_g"] / 100), 0),
    [(round(m4["rural"] * (1 - m4["rural_g"] / 100), 0), "误用现期×(1−r)"),
     (round(m4["rural"] / (1 + m4["urban_g"] / 100), 0), "错用城镇增速"),
     (round(m4["rural"] * (1 + m4["rural_g"] / 100), 0), "方向反:现期×(1+r)")],
    yuan,
    "【定型找数】求基期。农村现期26418元、名义增长6.35%（见表）。\n"
    "【列式】基期=26418/1.0635≈24840（元）。\n干扰项：现期×(1−r)、错套城镇增速、方向反。")
add_calc(f"{BATCH}-Q18", f"{BATCH}-M04", SHARE,
    "2024年，G省全体居民人均消费支出占人均可支配收入的比重约为（  ）。",
    round(m4["consume"] / m4["per"] * 100, 2),
    [(round(m4["per"] / m4["consume"] * 100, 2), "分子分母颠倒"),
     (round(m4["consume"] / m4["urban"] * 100, 2), "分母错用城镇收入"),
     (round(m4["consume"] / m4["rural"] * 100, 2), "分母错用农村收入")],
    pct,
    "【定型找数】消费率=人均消费支出/人均可支配收入（见表）。消费34926元、收入51789元。\n"
    "【列式】34926/51789≈67.44%。\n干扰项：分子分母颠倒、分母错用城镇/农村收入。")
add_calc(f"{BATCH}-Q19", f"{BATCH}-M04", CMP,
    "2024年，G省农村居民人均可支配收入名义增速比城镇居民约高（  ）。",
    round(m4["rural_g"] - m4["urban_g"], 2),
    [(round(m4["rural_g"] + m4["urban_g"], 2), "误求和"),
     (round(m4["rural_g"] - m4["per_g"], 2), "错取全体增速"),
     (round(m4["consume_g"] - m4["urban_g"], 2), "错取消费增速")],
    pp,
    "【定型找数】两增速作差得百分点（见表增长列）。农村6.35%、城镇4.12%。\n"
    "【列式】6.35−4.12=2.23（个百分点）。\n干扰项：误相加、错取全体/消费增速。")
add_judge(f"{BATCH}-Q20", f"{BATCH}-M04", AVG,
    ["2024年，G省城镇居民与农村居民人均可支配收入之比较上年有所缩小",
     "2024年，G省农村居民人均可支配收入名义增速低于城镇居民",
     "2024年，G省全体居民人均可支配收入名义增速高于人均消费支出名义增速",
     "2024年，G省全体居民人均消费支出占人均可支配收入的比重超过七成"], "A",
    "【逐项】A：农村增速6.35%>城镇增速4.12%，城乡收入比(城/农)较上年缩小，跨段可判，属实。\n"
    "B：农村6.35%>城镇4.12%，错。\n"
    "C：收入增速4.73%<消费增速5.28%，错。\n"
    "D：34926/51789≈67.44%<70%，错。故选A。")


# ─────────────────────────── self-check ───────────────────────────

def all_stats() -> list[float]:
    vals = []
    for m in (m1, m2, m3, m4):
        vals.extend(float(v) for v in m.values())
    return vals


def is_dirty(x: float) -> bool:
    if abs(x - round(x)) > 1e-9:
        return True  # has a fractional part
    i = int(round(x))
    return len(str(abs(i))) >= 3 and i % 100 != 0


def main() -> int:
    (OUT / "materials.json").write_text(
        json.dumps(MATERIALS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "questions.json").write_text(
        json.dumps(QUESTIONS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    from collections import Counter
    print("=== 资料样卷自检 ===")
    print(f"materials: {len(MATERIALS)}  questions: {len(QUESTIONS)}  images: {len(list(IMG.glob('*.png')))}")
    print("材料形态：M1 纯文字 / M2 文字+表 / M3 文字+柱图 / M4 混合(材料表+选项柱图识图题)")

    for mi, mat in enumerate(MATERIALS, 1):
        letters = [q["answer"] for q in QUESTIONS if q["material_id"] == mat["external_id"]]
        c = Counter(letters)
        cover = set(c) == set("ABCD") and sorted(c.values()) == [1, 1, 1, 2]
        print(f"  M0{mi} answers={''.join(letters)}  {'ABCD各一+1' if cover else '打散'}  images={mat['images']}")

    stats = all_stats()
    dirty = sum(1 for x in stats if is_dirty(x))
    print(f"脏数字比例（材料+图表全部统计量）：{dirty}/{len(stats)} = {dirty / len(stats):.0%}（要求≥40%）")

    banned = {"10", "20", "25", "33.3", "40", "50"}
    rates = [v for m in (m1, m2, m3, m4) for k, v in m.items() if k.endswith("_g") or k == "engel"]
    hit = [x for x in rates if f"{x:g}" in banned]
    print(f"增长率{len(rates)}个，命中禁堆值{sorted(banned)}：{hit or '无'}")
    print("含“某省”：", [m["external_id"] for m in MATERIALS if "某省" in m["content"]] or "无")
    print("题面课纲词(本题考察/秒杀)：",
          [q["external_id"] for q in QUESTIONS if any(w in q["stem"] for w in ("本题考察", "秒杀"))] or "无")
    print("整数2.0倍/两倍送分选项：",
          [q["external_id"] for q in QUESTIONS
           if any("2.0倍" in o.get("text", "") or "两倍" in o.get("text", "") for o in q["options"])] or "无")
    fig_opts = [q["external_id"] for q in QUESTIONS if any(o.get("images") for o in q["options"])]
    print("选项为图的题：", fig_opts or "无")
    print("全卷字母分布：", dict(sorted(Counter(q["answer"] for q in QUESTIONS).items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
