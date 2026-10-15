"""九宫格黑白块运算：每行第三格 = 前两格逐块运算。

生成器挑一种考试常见运算；干扰项按 I-RAVEN 两两平衡：答案、换一种运算的结果、
二者各改同一块，四个选项两两距离相同，只看选项猜不出。

判题器只读 PNG 像素取每块颜色，在写明的规则族里穷举：行/列 16 种逐块布尔运算、
行列平移旋转翻转、黑块数加减与等差。和已知格子对得上的规则各推一个答案，
四个选项里只能有一个被推中且等于答案键。规则族外的规律判不了。
"""

from __future__ import annotations

import itertools
import random
import sys

from .core import LETTERS, SCALE, Svg, options_sheet, parse, png_image

NAME = "bw_grid"
TAG = "判断推理-图形推理-黑白块类"
CATEGORY, SUB_CATEGORY = "判断推理", "图形推理"
TITLE = "黑白块类"
VERSION = 1
PARTS = ("figure", "options")
DEFINITION = "黑白块运算：同位置小块按固定规则运算（如黑+黑=白、白+白=白、黑+白=黑），先从前两行归纳运算表再套用。"
STEM = "从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性："

N = 3
COMBOS = ((0, 0), (0, 1), (1, 0), (1, 1))
EXAM_OPS = {
    "去同存异": (0, 1, 1, 0),
    "去异存同（同色变黑）": (1, 0, 0, 1),
    "叠加（有黑就黑）": (0, 1, 1, 1),
    "求同（都黑才黑）": (0, 0, 0, 1),
    "黑黑得白、其余得黑": (1, 1, 1, 0),
    "第一格减去第二格的黑块": (0, 0, 1, 0),
}
EASY_OPS = ("去同存异", "叠加（有黑就黑）", "求同（都黑才黑）")
ALL_OPS = list(itertools.product((0, 1), repeat=4))


def apply_op(table, a, b):
    return tuple(table[COMBOS.index((x, y))] for x, y in zip(a, b))


def _grid(bits):
    return [bits[i * N:(i + 1) * N] for i in range(N)]


def _flat(rows):
    return tuple(v for row in rows for v in row)


def rot90(bits):
    g = _grid(bits)
    return _flat([[g[N - 1 - c][r] for c in range(N)] for r in range(N)])


def flip_h(bits):
    return _flat([row[::-1] for row in _grid(bits)])


def flip_v(bits):
    return _flat(_grid(bits)[::-1])


MOVES = {
    "顺时针转 90°": rot90,
    "转 180°": lambda b: rot90(rot90(b)),
    "逆时针转 90°": lambda b: rot90(rot90(rot90(b))),
    "左右翻": flip_h,
    "上下翻": flip_v,
    **{f"按阅读顺序平移 {k} 格": (lambda b, k=k: b[-k:] + b[:-k]) for k in range(1, N * N)},
}


def generate(rng, difficulty):
    tier = difficulty if difficulty in ("easy", "mid", "hard") else rng.choice(("easy", "mid", "hard"))
    names = EASY_OPS if tier == "easy" else tuple(EXAM_OPS)
    name = rng.choice(names)
    op = EXAM_OPS[name]
    p = rng.uniform(0.35, 0.6)
    rows = []
    for _ in range(3):
        a = tuple(int(rng.random() < p) for _ in range(N * N))
        b = tuple(int(rng.random() < p) for _ in range(N * N))
        rows.append([a, b, apply_op(op, a, b)])
    seen = {(x, y) for r in rows[:2] for x, y in zip(r[0], r[1])}
    panels = [cell for r in rows for cell in r]
    if len(seen) < 4 or len(set(panels)) < 9 or not all(2 <= sum(c) <= N * N - 2 for c in panels):
        return None
    answer = rows[2][2]
    a, b = rows[2][0], rows[2][1]
    others = [apply_op(EXAM_OPS[n], a, b) for n in EXAM_OPS if n != name]
    others = [o for o in others if o != answer and 1 <= sum(o) <= N * N - 1]
    if not others:
        return None
    wrong = rng.choice(others)
    same = [i for i in range(N * N) if answer[i] == wrong[i]]
    if not same:
        return None
    cell = rng.choice(same)
    flip = lambda bits: tuple(v ^ (i == cell) for i, v in enumerate(bits))
    options = [answer, wrong, flip(answer), flip(wrong)]
    if len(set(options)) < 4 or not all(1 <= sum(o) <= N * N - 1 for o in options):
        return None
    matrix = [[list(c) for c in r] for r in rows]
    matrix[2][2] = None
    return {"stem": STEM, "rule": name, "matrix": matrix, "options": [list(o) for o in options], "answer": 0,
            "difficulty": {"easy": 2, "mid": 3, "hard": 4}[tier]}


# ---------------------------------------------------------------- 渲染
CELL, GAP, PAD = 24, 34, 16
PANEL = N * CELL


def _panel(svg, x0, y0, bits, data):
    svg.rect(x0, y0, PANEL, PANEL, sw=2.2, data={**data, "panel": "frame"})
    for i, v in enumerate(bits or []):
        r, c = divmod(i, N)
        svg.rect(x0 + c * CELL, y0 + r * CELL, CELL, CELL, fill="#111111" if v else "#ffffff", sw=1.2,
                 data={**data, "cell": str(i)})


def render(draft, order, flip_cell=None):
    size = PAD * 2 + 3 * PANEL + 2 * GAP
    figure = Svg(size, size)
    for r, c in itertools.product(range(3), range(3)):
        x0, y0 = PAD + c * (PANEL + GAP), PAD + r * (PANEL + GAP)
        bits = draft["matrix"][r][c]
        if bits is None:
            figure.rect(x0, y0, PANEL, PANEL, sw=2.2, data={"slot": "?"})
            figure.text((x0 + PANEL / 2, y0 + PANEL / 2), "?", size=40)
        else:
            _panel(figure, x0, y0, bits, {"slot": f"{r},{c}"})
    cells = {}
    for i, j in enumerate(order):
        bits = list(draft["options"][j])
        if flip_cell is not None and j == draft["answer"]:  # 负例：渲染时把答案画错一块
            bits[flip_cell] ^= 1
        cells[LETTERS[i]] = lambda svg, b=bits: _panel(svg, 10, 10, b, {})
    sheet = options_sheet(cells, PANEL + 20, PANEL + 20, cols=4)
    return {"figure": str(figure), "options": str(sheet)}


# ---------------------------------------------------------------- 判题器：位置从 SVG 取，颜色只看 PNG 像素
def _read_bits(image, x0, y0):
    bits = []
    for i in range(N * N):
        r, c = divmod(i, N)
        x, y = (x0 + c * CELL + CELL / 2) * SCALE, (y0 + r * CELL + CELL / 2) * SCALE
        bits.append(int(image.getpixel((int(x), int(y))) < 128))
    return tuple(bits)


def _read(svgs, pngs):
    fig = png_image(pngs["figure"])
    matrix = [[None] * 3 for _ in range(3)]
    for prim in parse(svgs["figure"]):
        if prim.data.get("panel") == "frame" and "slot" in prim.data:
            r, c = map(int, prim.data["slot"].split(","))
            matrix[r][c] = _read_bits(fig, *prim.points[0])
    opt = png_image(pngs["options"])
    options = {}
    for prim in parse(svgs["options"]):
        if prim.data.get("panel") == "frame" and "option" in prim.data:
            options[prim.data["option"]] = _read_bits(opt, *prim.points[0])
    if sum(v is None for row in matrix for v in row) != 1 or matrix[2][2] is not None or sorted(options) != list(LETTERS):
        raise ValueError("九宫格或选项不全")
    return matrix, options


def predictions(m):
    out = []
    for t in ALL_OPS:
        if all(apply_op(t, m[r][0], m[r][1]) == m[r][2] for r in (0, 1)):
            out.append((f"行：逐块运算{t}", apply_op(t, m[2][0], m[2][1])))
        if all(apply_op(t, m[0][c], m[1][c]) == m[2][c] for c in (0, 1)):
            out.append((f"列：逐块运算{t}", apply_op(t, m[0][2], m[1][2])))
    for name, move in MOVES.items():
        if all(move(m[r][0]) == m[r][1] and move(m[r][1]) == m[r][2] for r in (0, 1)):
            out.append((f"行：{name}", move(m[2][1])))
        if all(move(m[0][c]) == m[1][c] and move(m[1][c]) == m[2][c] for c in (0, 1)):
            out.append((f"列：{name}", move(m[1][2])))
    for label, f in (("和", lambda x, y: x + y), ("差", lambda x, y: abs(x - y))):
        if all(f(sum(m[r][0]), sum(m[r][1])) == sum(m[r][2]) for r in (0, 1)):
            out.append((f"行：黑块数第三格=前两格之{label}", f(sum(m[2][0]), sum(m[2][1]))))
        if all(f(sum(m[0][c]), sum(m[1][c])) == sum(m[2][c]) for c in (0, 1)):
            out.append((f"列：黑块数第三格=前两格之{label}", f(sum(m[0][2]), sum(m[1][2]))))
    if all(sum(m[r][1]) - sum(m[r][0]) == sum(m[r][2]) - sum(m[r][1]) for r in (0, 1)):
        out.append(("行：黑块数等差", 2 * sum(m[2][1]) - sum(m[2][0])))
    if all(sum(m[r][0]) == sum(m[r][1]) == sum(m[r][2]) for r in (0, 1)):
        out.append(("行：黑块数相同", sum(m[2][0])))
    return out


def judge(svgs, pngs=None, stem=None, texts=None):
    matrix, options = _read(svgs, pngs)
    hit = {}
    for rule, pred in predictions(matrix):
        for letter, bits in options.items():
            if (isinstance(pred, int) and sum(bits) == pred) or pred == bits:
                hit.setdefault(letter, []).append(rule)
    issues = []
    if len(hit) > 1:
        issues.append("规律不唯一：" + "；".join(f"{k}←{v[0]}" for k, v in sorted(hit.items())))
    if len(set(options.values())) < 4:
        issues.append("有两个选项画得一样")
    if len(hit) == 1:
        key = next(iter(hit))
        dist = {k: sum(sum(x != y for x, y in zip(v, w)) for o, w in options.items() if o != k) for k, v in options.items()}
        if dist[key] < min(v for k, v in dist.items() if k != key):
            issues.append("只看选项就能猜：答案是四个选项的「中心」")
    tables = [t for t in ALL_OPS if all(apply_op(t, matrix[r][0], matrix[r][1]) == matrix[r][2] for r in (0, 1))]
    return {"correct": sorted(hit), "issues": issues, "table": list(tables[0]) if len(tables) == 1 else None,
            "rules": {k: v for k, v in hit.items()}}


def explain(verdict, key):
    table = verdict.get("table")
    if not table:
        return "每行前两格对应位置逐块运算得到第三格。"
    color = lambda v: "黑" if v else "白"
    rule = "，".join(f"{color(a)}+{color(b)}={color(table[COMBOS.index((a, b))])}" for a, b in COMBOS)
    return (f"每行第一、二个图形对应位置的小块逐块运算得到第三个图形：{rule}。"
            f"第三行前两个图形按此运算，得到 {key} 项。其余选项或换了一种运算，或有一块颜色不对，排除。")


def self_test():
    from .core import check, place_answer, rasterize

    me = sys.modules[__name__]

    def build(draft, order, **kw):
        svgs = render(draft, order, **kw)
        return svgs, {k: rasterize(v) for k, v in svgs.items()}

    out = []
    rng = random.Random(4242)
    draft = None
    while draft is None:
        draft = generate(rng, "mid")
    order = place_answer(0, 4, "C", rng)
    svgs, pngs = build(draft, order)
    issues, _ = check(me, svgs, pngs, "C")
    out.append(("正常题能过", not issues, "；".join(issues) or "通过"))
    issues, _ = check(me, svgs, pngs, "A")
    out.append(("答案键写错", bool(issues), "；".join(issues)))
    issues, _ = check(me, *build(draft, order, flip_cell=4), "C")
    out.append(("渲染时把答案画错一块", bool(issues), "；".join(issues)))
    dup = dict(draft)
    dup["options"] = [draft["options"][0], draft["options"][0], draft["options"][2], draft["options"][3]]
    issues, _ = check(me, *build(dup, order), "C")
    out.append(("重复选项", bool(issues), "；".join(issues)))

    # 前两行没有「黑+黑」：去同存异和叠加都说得通
    r = random.Random(3)
    while True:
        rows = []
        for i in range(3):
            a = tuple(int(r.random() < 0.45) for _ in range(N * N))
            b = tuple(0 if (i < 2 and a[j]) else int(r.random() < 0.45) for j in range(N * N))
            rows.append([a, b, apply_op(EXAM_OPS["去同存异"], a, b)])
        alt = apply_op(EXAM_OPS["叠加（有黑就黑）"], rows[2][0], rows[2][1])
        if alt != rows[2][2]:
            break
    under = {"matrix": [[list(c) for c in row] for row in rows], "answer": 0,
             "options": [list(rows[2][2]), list(alt), list(flip_h(alt)), list(rot90(alt))]}
    under["matrix"][2][2] = None
    issues, _ = check(me, *build(under, [0, 1, 2, 3]), "A")
    out.append(("前两行缺「黑+黑」：运算定不下来", bool(issues), "；".join(issues)))

    # 横看去同存异、竖看叠加，推出不同答案
    r = random.Random(7)
    while True:
        p00, p01, p10, p11 = (tuple(int(r.random() < 0.45) for _ in range(N * N)) for _ in range(4))
        xor, union = EXAM_OPS["去同存异"], EXAM_OPS["叠加（有黑就黑）"]
        p02, p12 = apply_op(xor, p00, p01), apply_op(xor, p10, p11)
        p20, p21 = apply_op(union, p00, p10), apply_op(union, p01, p11)
        by_row, by_col = apply_op(xor, p20, p21), apply_op(union, p02, p12)
        if by_row != by_col:
            break
    cross_ = {"matrix": [[list(p00), list(p01), list(p02)], [list(p10), list(p11), list(p12)], [list(p20), list(p21), None]],
              "answer": 0, "options": [list(by_row), list(by_col), list(flip_h(by_row)), list(flip_v(by_col))]}
    issues, _ = check(me, *build(cross_, [0, 1, 2, 3]), "A")
    out.append(("横看竖看两条规律推出不同选项", bool(issues), "；".join(issues)))
    return out
