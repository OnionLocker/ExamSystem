#!/usr/bin/env python3
"""把 zhenti-promote 题的粗标签对齐到系统里已有的三级知识点。

只使用 336 风格库标签、知识卡片数量规范名、资料分析词表里的固定落点。
对不上就不改。归纳成功的题把规范标签放到 tags[0]。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from kaodian_taxonomy import (
    KNOWN_QUANTITY_TAGS,
    KNOWN_ZILIAO_TAGS,
    ZILIAO_AVG,
    ZILIAO_BASE,
    ZILIAO_CMP,
    ZILIAO_DELTA,
    ZILIAO_MIX,
    ZILIAO_QI,
    ZILIAO_RATE,
    ZILIAO_SHARE,
    ZILIAO_SHARE_DIFF,
    ZILIAO_SPEC,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "exam.db"

ZILIAO_ALLOW = set(KNOWN_ZILIAO_TAGS)

# (needles, tag) 先写更细的。blob 命中任一 needle 即采用。
RULES: list[tuple[tuple[str, ...], str]] = [
    # 数量 · 数推
    (("作和作积",), "数量关系-数字推理-作和作积数列"),
    (("作商数列", "作商"), "数量关系-数字推理-作商数列"),
    (("分数数列", "分数"), "数量关系-数字推理-分数数列"),
    (("图形数阵", "数阵"), "数量关系-数字推理-图形数阵"),
    (("多重数列", "多重"), "数量关系-数字推理-多重数列"),
    (("多级数列", "多级", "二级等差"), "数量关系-数字推理-多级数列"),
    (("幂次",), "数量关系-数字推理-幂次数列"),
    (("机械划分", "机械拆分"), "数量关系-数字推理-机械划分"),
    (("递推数列", "递推"), "数量关系-数字推理-递推数列"),
    (("数字推理",), "数量关系-数字推理-数字推理-其他"),
    # 数量 · 运算
    (("两溶液", "溶液混合"), "数量关系-数学运算-溶液问题"),
    (("立体",), "数量关系-数学运算-几何问题"),
    (("相似",), "数量关系-数学运算-几何问题"),
    (("平面图形", "几何", "勾股", "周长", "面积"), "数量关系-数学运算-几何问题"),
    (("年龄",), "数量关系-数学运算-年龄问题"),
    (("不定方程",), "数量关系-数学运算-不定方程问题"),
    (("相遇追及", "追及", "相遇"), "数量关系-数学运算-行程问题"),
    (("行程", "流水", "行船"), "数量关系-数学运算-行程问题"),
    (("给情况求概率",), "数量关系-数学运算-概率问题"),
    (("给概率求概率",), "数量关系-数学运算-概率问题"),
    (("正难则反", "反面容斥", "反面法", "反面剥离"), "数量关系-数学运算-排列组合问题"),
    (("隔板", "插空", "特殊位置", "分组分配", "优限"), "数量关系-数学运算-排列组合问题"),
    (("基础排列组合", "排列组合", "组合数", "古典概型", "概率"), "数量关系-数学运算-排列组合问题"),
    (("星期", "日期", "闰年", "大月", "小月"), "数量关系-数学运算-星期日期问题"),
    (("周期", "排班", "公倍数"), "数量关系-数学运算-周期问题"),
    (("统筹", "非典型最值", "最值", "极值"), "数量关系-数学运算-最值问题"),
    (("利润", "折扣", "分段计费", "经济利润"), "数量关系-数学运算-经济利润问题"),
    (("工程",), "数量关系-数学运算-工程问题"),
    (("容斥",), "数量关系-数学运算-容斥原理问题"),
    (("和差倍比", "方程", "比例", "特值"), "数量关系-数学运算-和差倍比问题"),
    # 判断 · 逻辑
    (("支持与前提假设", "加强论证", "支持论证", "补充论据", "搭桥", "前提假设", "加强", "补充前提"), "判断推理-逻辑判断-加强题型"),
    (("一般质疑", "削弱论点", "削弱论据", "削弱论证", "拆桥", "反例削弱", "削弱"), "判断推理-逻辑判断-削弱题型"),
    (("翻译推理与逻辑基础", "常规翻译", "翻译推理", "逆否", "假言", "选言", "联言", "翻译"), "判断推理-逻辑判断-翻译推理"),
    (("秒杀模型与速解技巧", "结构相似", "论证结构", "推理形式", "平行结构"), "判断推理-逻辑判断-论证结构"),
    (("比例类论证与解释说明", "原因解释", "解释矛盾", "解释现象", "解释"), "判断推理-逻辑判断-原因解释"),
    (("归因论证", "因果倒置", "另有他因", "因果分析"), "判断推理-逻辑判断-原因解释"),
    (("代入法", "代入"), "判断推理-逻辑判断-组合排列-单题"),
    (("最大信息",), "判断推理-逻辑判断-组合排列-单题"),
    # 判断 · 科推
    (("受力平衡", "受力分析", "平衡"), "判断推理-科学推理-科学推理-物理"),
    (("杠杆滑轮", "滑轮", "杠杆"), "判断推理-科学推理-科学推理-物理"),
    (("液体压强", "连通器", "液压"), "判断推理-科学推理-科学推理-物理"),
    (("阿基米德原理", "浮力"), "判断推理-科学推理-科学推理-物理"),
    (("反射折射", "光现象", "光学", "折射", "反射"), "判断推理-科学推理-科学推理-物理"),
    (("透镜成像", "凸透镜", "凹透镜"), "判断推理-科学推理-科学推理-物理"),
    (("串并联", "欧姆定律", "电路分析"), "判断推理-科学推理-科学推理-物理"),
    (("电路故障", "故障"), "判断推理-科学推理-科学推理-物理"),
    (("酸碱与 pH", "酸碱", "pH", "指示剂"), "判断推理-科学推理-科学推理-化学"),
    (("人体调节", "体温调节", "神经调节", "体液调节", "胰岛素"), "判断推理-科学推理-科学推理-生物"),
    (("电路",), "判断推理-科学推理-科学推理-物理"),
    (("浮力",), "判断推理-科学推理-科学推理-物理"),
    (("压强",), "判断推理-科学推理-科学推理-物理"),
    (("摩擦",), "判断推理-科学推理-科学推理-物理"),
    (("弹力",), "判断推理-科学推理-科学推理-物理"),
    (("化学",), "判断推理-科学推理-科学推理-化学"),
    (("溶液",), "判断推理-科学推理-科学推理-化学"),
    (("电荷",), "判断推理-科学推理-科学推理-物理"),
    (("曲线运动",), "判断推理-科学推理-科学推理-物理"),
    (("生态",), "判断推理-科学推理-科学推理-生物"),
    (("生物",), "判断推理-科学推理-科学推理-生物"),
    (("物质的性质",), "判断推理-科学推理-科学推理-化学"),
    (("基本概念",), "判断推理-科学推理-科学推理-物理"),
    # 判断 · 图形（无切图，但文字标注仍可归）
    (("位置规律",), "判断推理-图形推理-位置规律"),
    (("属性规律",), "判断推理-图形推理-属性规律"),
    (("数量规律",), "判断推理-图形推理-数量规律"),
    (("样式规律",), "判断推理-图形推理-样式规律"),
    (("特殊规律",), "判断推理-图形推理-特殊规律"),
    (("空间类", "空间"), "判断推理-图形推理-空间类"),
    # 言语
    (("词语辨析", "实词辨析", "实词填空", "搭配对象", "感情色彩", "程度轻重"), "言语理解与表达-逻辑填空-词的辨析"),
    (("逻辑对应", "成语辨析", "成语填空", "解释说明", "对应关系"), "言语理解与表达-逻辑填空-语境分析"),
    (("宏观把握", "语境呼应", "混搭填空", "关联关系"), "言语理解与表达-逻辑填空-混搭填空"),
    (("语句排序", "确定首句", "确定顺序", "确定捆绑", "确定尾句", "重新排列"), "言语理解与表达-语句表达-语句排序题"),
    (("语句填入", "语句填空", "语句衔接", "横线在中间", "横线在开头", "横线在结尾", "总领下文"), "言语理解与表达-语句表达-语句填空题"),
    (("五种常见结构分析", "主旨概括", "中心理解", "主旨", "五种常见结构"), "言语理解与表达-片段阅读-中心理解题"),
    (("标题拟定", "标题填入题", "标题选择", "标题填入", "适合做这段文字标题"), "言语理解与表达-片段阅读-标题填入题"),
    (("意图判断", "意图", "意在说明", "意在强调", "想表达"), "言语理解与表达-片段阅读-中心理解题"),
    (("下文推断", "接语选择题", "承接叙述", "接语", "接下来最可能"), "言语理解与表达-语句表达-接语选择题"),
    (("细节判断", "细节判断题", "细节查找", "细节理解"), "言语理解与表达-片段阅读-细节判断题"),
    (("标题",), "言语理解与表达-片段阅读-标题填入题"),
    (("主题词",), "言语理解与表达-片段阅读-中心理解题"),
    (("接语", "承接叙述", "下文推断"), "言语理解与表达-语句表达-接语选择题"),
    (("横线在中间",), "言语理解与表达-语句表达-语句填空题"),
    (("横线在开头",), "言语理解与表达-语句表达-语句填空题"),
    (("横线在结尾",), "言语理解与表达-语句表达-语句填空题"),
    (("确定尾句", "尾句"), "言语理解与表达-语句表达-语句排序题"),
    (("确定捆绑", "捆绑"), "言语理解与表达-语句表达-语句排序题"),
    (("确定顺序",), "言语理解与表达-语句表达-语句排序题"),
    (("混搭填空", "混搭"), "言语理解与表达-逻辑填空-混搭填空"),
    (("成语填空", "成语"), "言语理解与表达-逻辑填空-成语填空"),
    (("实词填空", "实词"), "言语理解与表达-逻辑填空-实词填空"),
    (("虚词填空", "虚词"), "言语理解与表达-逻辑填空-虚词填空"),
    (("搭配对象", "搭配"), "言语理解与表达-逻辑填空-词的辨析"),
    (("感情色彩",), "言语理解与表达-逻辑填空-词的辨析"),
    (("程度轻重",), "言语理解与表达-逻辑填空-词的辨析"),
    (("逻辑填空&并列", "关联关系-并列"), "言语理解与表达-逻辑填空-语境分析"),
    (("逻辑填空&转折", "关联关系-转折"), "言语理解与表达-逻辑填空-语境分析"),
    (("解释说明",), "言语理解与表达-逻辑填空-语境分析"),
    # 常识
    (("宪法",), "常识判断-法律常识-宪法"),
    (("民法典", "民法"), "常识判断-法律常识-民法典"),
    (("行政法",), "常识判断-法律常识-行政法"),
    (("诉讼法",), "常识判断-法律常识-诉讼法"),
    (("劳动法", "经济法"), "常识判断-法律常识-劳动法和经济法"),
    (("法理学",), "常识判断-法律常识-法理学"),
    (("生物常识", "生物", "医学"), "常识判断-科技常识-生物常识"),
    (("生活常识", "生活"), "常识判断-科技常识-生活常识"),
    (("科技理论", "科技成就", "航天"), "常识判断-科技常识-科技理论与成就"),
    (("文学常识", "文学"), "常识判断-人文常识-文学常识"),
    (("中国历史", "历史"), "常识判断-人文常识-中国历史"),
    (("文化常识", "文化"), "常识判断-人文常识-文化常识"),
    (("自然地理",), "常识判断-地理国情-自然地理"),
    (("中国地理",), "常识判断-地理国情-中国地理"),
    (("国际经济",), "常识判断-经济常识-国际经济及组织"),
    (("宏观经济", "调控"), "常识判断-经济常识-宏观经济与调控政策"),
    (("微观经济", "微观"), "常识判断-经济常识-微观经济"),
    (("市场经济",), "常识判断-经济常识-市场经济"),
    # 政治
    (("唯物辩证法", "辩证法", "矛盾"), "政治理论-马克思主义-马克思主义哲学"),
    (("唯物史观",), "政治理论-马克思主义-马克思主义哲学"),
    (("认识论",), "政治理论-马克思主义-马克思主义哲学"),
    (("唯物论",), "政治理论-马克思主义-马克思主义哲学"),
    (("党的历史", "党史"), "政治理论-毛中特-党的基本知识"),
    (("党章", "党纪"), "政治理论-毛中特-党的基本知识"),
    (("毛泽东",), "政治理论-毛中特-毛泽东思想"),
    (("新思想&会议", "新思想&讲话"), "政治理论-时事政治-重要会议讲话"),
    (("新思想&文件",), "政治理论-时事政治-重要文件"),
    (("时政&会议", "时事政治&会议", "时政&讲话"), "政治理论-时事政治-重要会议讲话"),
    (("时政&文件", "时事政治&文件"), "政治理论-时事政治-重要文件"),
    # 资料（落到知识库 07-ziliao.md 主标签；综合判断按正确项考点打，不单列）
    (("两期比重", "比重差", "比重趋势", "比值差"), ZILIAO_SHARE_DIFF),
    (("混合增长", "十字交叉", "盐水"), ZILIAO_MIX),
    (("拉动", "贡献率"), ZILIAO_SPEC),
    (("年均", "平均数", "平均值"), ZILIAO_AVG),
    (("基期量",), ZILIAO_BASE),
    (("增长量", "环比增量"), ZILIAO_DELTA),
    (("增长率", "同比增速", "同比增长率"), ZILIAO_RATE),
    (("双线", "增量比较"), ZILIAO_CMP),
    (("比重", "占比", "资产负债率"), ZILIAO_SHARE),
    (("直接读数", "简单查找", "简单计算", "数据检索", "倍数"), ZILIAO_QI),
]


def parse_tags(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(x) for x in value if str(x).strip()] if isinstance(value, list) else []


def load_allowlist(conn: sqlite3.Connection) -> set[str]:
    allow = set(KNOWN_QUANTITY_TAGS) | set(ZILIAO_ALLOW) | {tag for _, tag in RULES}
    allow.add("判断推理-逻辑判断-翻译推理")
    for (raw,) in conn.execute("SELECT tags FROM reference_questions WHERE imported_by = 'New Bot'"):
        allow.update(tag for tag in parse_tags(raw) if tag.count("-") >= 2)
    return allow


def needle_hits(blob: str, needle: str) -> bool:
    parts = [part for part in needle.split("&") if part]
    return all(part in blob for part in parts)


def compatible(category: str, tag: str) -> bool:
    head = tag.split("-", 1)[0]
    if head == category:
        return True
    if category == "言语理解与表达" and head == "言语理解":
        return True
    if category == "判断推理" and head in {"判断推理", "科学推理", "逻辑判断", "图形推理"}:
        return True
    if category == "科学推理" and head == "判断推理":
        return True
    if category == "常识判断" and head == "政治理论":
        return True
    return False


def classify(category: str, sub_category: str, tags: list[str], allow: set[str]) -> str | None:
    blob = " ".join([category, sub_category, *tags])
    if any(word in blob for word in ("定义判断", "类比推理")):
        return None
    for needles, tag in RULES:
        if tag not in allow or not compatible(category, tag):
            continue
        if any(needle_hits(blob, needle) for needle in needles):
            return tag
    return None


def run(db_path: Path, apply: bool) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    allow = load_allowlist(conn)
    rows = conn.execute(
        """
        SELECT external_id, category, sub_category, tags
          FROM reference_questions
         WHERE imported_by = 'zhenti-promote'
        """
    ).fetchall()
    mapped: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    updates: list[tuple[str, str]] = []
    for row in rows:
        old = parse_tags(row["tags"])
        tag = classify(row["category"], row["sub_category"] or "", old, allow)
        if tag:
            mapped[row["category"]] += 1
            new_tags = [tag, *[item for item in old if item != tag]]
            updates.append((json.dumps(new_tags, ensure_ascii=False), row["external_id"]))
        else:
            key = f"{row['category']}｜{row['sub_category'] or '未细分'}"
            unmapped[key] += 1
    if apply and updates:
        conn.executemany(
            "UPDATE reference_questions SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE external_id = ?",
            updates,
        )
        conn.commit()
    conn.close()
    return {
        "total": len(rows),
        "mapped": sum(mapped.values()),
        "unmapped": sum(unmapped.values()),
        "mapped_by_category": dict(mapped),
        "unmapped_by_type": unmapped.most_common(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stats = run(args.db, args.apply)
    print(
        f"{'已写入' if args.apply else '试运行'} "
        f"总 {stats['total']}｜已归纳 {stats['mapped']}｜未归纳 {stats['unmapped']}"
    )
    print("已归纳分模块：", stats["mapped_by_category"])
    print("未归纳（按题型，前 20）：")
    for key, count in stats["unmapped_by_type"][:20]:
        print(f"  {count:4d}  {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
