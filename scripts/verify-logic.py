#!/usr/bin/env python3
"""命题逻辑题的机械判定器：判断选项能否被前提必然推出，并检查正确项是否恰好一个。

为什么要有它：让模型「自己再验一遍」是不可靠的（实测承诺过也照样出错）。
翻译推理 / 逻辑判断这类题的正确性完全可以形式化，一旦形式化，判定就是
穷举真值表，结果是决定性的，跟模型能力无关。

所以分工是：模型只负责把中文翻译成公式（它擅长），判定交给这个脚本（它不会错）。

用法：
    echo '{...}' | python3 scripts/verify-logic.py
    python3 scripts/verify-logic.py question.json

输入 JSON：
    {
      "id": "Q001",
      "premises": ["面试 -> 笔试", "面试 -> 录用"],
      "options": {
        "A": "!录用 -> !笔试",
        "B": "笔试 -> 录用",
        "C": "!面试 -> !笔试",
        "D": "录用 -> 面试"
      },
      "claimed_answer": "D"
    }

变元不用声明，从公式里自动收集，中文变量名直接可用。公式语法：
    !  非
    &  与
    |  或
    -> 蕴含（右结合）
    <->等价
    () 分组
    常见的 Unicode 逻辑符号会先被规范成上面这套 ASCII 写法。

退出码：0 = 唯一答案且与 claimed_answer 一致；1 = 题目有问题；2 = 输入有问题。
"""

import io
import json
import sys
from itertools import product

# ---------------------------------------------------------------------------
# 词法：先把 Unicode 逻辑符号规范成 ASCII，再切 token
# ---------------------------------------------------------------------------

NORMALIZE = {
    '\u00ac': '!', '~': '!', '\uff01': '!',
    '\u2227': '&', '\uff06': '&',
    '\u2228': '|',
    '\u2192': '->', '\u21d2': '->', '\u27f9': '->',
    '\u2194': '<->', '\u21d4': '<->',
    '\uff08': '(', '\uff09': ')',
}

OPS = ('<->', '->', '&', '|', '!', '(', ')')

# 变元名里出现这些词，说明这句话根本没被形式化，整句被当成了一个变元名。
# 只收双字词：单字的「就」会把「就业」「成就」这类正常变元误报掉。
CONNECTIVE_WORDS = ('如果', '那么', '否则', '除非', '只有', '并且', '或者',
                    '因为', '所以', '必须', '前提', '当且仅当')


def tokenize(text):
    for k, v in NORMALIZE.items():
        text = text.replace(k, v)
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        matched = None
        for op in OPS:
            if text.startswith(op, i):
                matched = op
                break
        if matched:
            tokens.append(matched)
            i += len(matched)
            continue
        # 变元：一直吃到下一个运算符或空白，所以中文变量名天然支持
        j = i
        while j < n and not text[j].isspace():
            if any(text.startswith(op, j) for op in OPS):
                break
            j += 1
        if j == i:
            raise ValueError('无法解析的字符 %r（位置 %d）' % (text[i], i))
        tokens.append(text[i:j])
        i = j
    return tokens


# ---------------------------------------------------------------------------
# 语法：递归下降。优先级 ! > & > | > -> > <->
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens, source):
        self.t = tokens
        self.i = 0
        self.src = source

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, tok):
        if self.peek() != tok:
            raise ValueError('%r 里缺少 %r' % (self.src, tok))
        self.i += 1

    def parse(self):
        node = self.iff()
        if self.i != len(self.t):
            raise ValueError('%r 尾部有多余内容：%s' % (self.src, ' '.join(self.t[self.i:])))
        return node

    def iff(self):
        left = self.implies()
        while self.peek() == '<->':
            self.eat('<->')
            left = ('<->', left, self.implies())
        return left

    def implies(self):
        left = self.orr()
        if self.peek() == '->':
            self.eat('->')
            return ('->', left, self.implies())
        return left

    def orr(self):
        left = self.andd()
        while self.peek() == '|':
            self.eat('|')
            left = ('|', left, self.andd())
        return left

    def andd(self):
        left = self.unary()
        while self.peek() == '&':
            self.eat('&')
            left = ('&', left, self.unary())
        return left

    def unary(self):
        if self.peek() == '!':
            self.eat('!')
            return ('!', self.unary())
        if self.peek() == '(':
            self.eat('(')
            node = self.iff()
            self.eat(')')
            return node
        tok = self.peek()
        if tok is None or tok in OPS:
            raise ValueError('%r 里缺少变元' % self.src)
        self.i += 1
        return ('var', tok)


def parse(text):
    return Parser(tokenize(text), text).parse()


def collect_vars(node, out):
    if node[0] == 'var':
        out.add(node[1])
    elif node[0] == '!':
        collect_vars(node[1], out)
    else:
        collect_vars(node[1], out)
        collect_vars(node[2], out)


def count_vars(node, counter):
    """统计每个变元出现的次数。笔误检测要靠它区分「打错一次」和「两个正经命题」。"""
    if node[0] == 'var':
        counter[node[1]] = counter.get(node[1], 0) + 1
    elif node[0] == '!':
        count_vars(node[1], counter)
    else:
        count_vars(node[1], counter)
        count_vars(node[2], counter)


def evaluate(node, env):
    kind = node[0]
    if kind == 'var':
        return env[node[1]]
    if kind == '!':
        return not evaluate(node[1], env)
    a = evaluate(node[1], env)
    b = evaluate(node[2], env)
    if kind == '&':
        return a and b
    if kind == '|':
        return a or b
    if kind == '->':
        return (not a) or b
    if kind == '<->':
        return a == b
    raise ValueError('未知节点 %r' % kind)


# ---------------------------------------------------------------------------
# 形式化 lint：判定本身不会错，但「喂进来的公式不是题目的意思」它看不出来。
# 这里拦两种静默失败——两种都会让错题拿到 ok 的通过章。
# ---------------------------------------------------------------------------

def _char_kind(ch):
    if '一' <= ch <= '鿿':
        return 'cjk'
    return 'ascii' if ch.isascii() else 'other'


def lint_variables(names, occurrences, premise_count):
    """返回一串警告。空列表 = 变元表看上去是正常形式化的产物。

    occurrences: 变元名 -> 在全部公式里出现的总次数。
    """
    warnings = []

    # 1) 整句没被形式化：连接词残留在变元名里。
    #    典型是「除非甲否则乙」不加空格，被当成单个变元，然后误报 no_answer。
    for name in names:
        hit = [w for w in CONNECTIVE_WORDS if w in name]
        if hit:
            warnings.append(
                '变元 %r 里含有连接词 %s，这句话没有被形式化。'
                '中文变元之间要留空格，连接词要写成运算符（-> ! & |）'
                % (name, '、'.join(hit)))

    # 2) 变元名笔误：「录用」写成「綠用」会被当成两个互不相干的命题，
    #    判定照样返回 ok。
    #
    #    但「笔试 / 面试」「初审 / 复审」这类只差一字的词在公考题里是正当的
    #    不同命题，光看「差一个字」会把它们全误报掉，反而逼着人去改对的题。
    #    真正的笔误信号是：其中一个变元只出现了一次（打错的那次），
    #    另一个反复出现。所以这里只报「差一字且其中一方是孤立变元」的组合。
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if len(a) != len(b) or len(a) < 2:
                continue
            diff = [k for k in range(len(a)) if a[k] != b[k]]
            if len(diff) != 1:
                continue
            k = diff[0]
            # 只在中文之间比：A/B、P1/P2 这种正规命名不算
            if _char_kind(a[k]) != 'cjk' or _char_kind(b[k]) != 'cjk':
                continue
            # 两边都被用了多次，说明是两个正经命题（笔试/面试），不是笔误
            lonely = [x for x in (a, b) if occurrences.get(x, 0) <= 1]
            if not lonely:
                continue
            warnings.append(
                '变元 %r 和 %r 只差一个字，而 %s 全篇只出现了一次，疑似笔误。'
                '判定器会把它们当成两个无关的命题，结论不可信'
                % (a, b, '、'.join(repr(x) for x in lonely)))

    # 3) 单变元且只有一条前提，通常是形式化写漏了。
    #    「P 且 !P」这种真前提矛盾的题也只有一个变元，但它前提在两条以上，
    #    该由 contradictory_premises 去报，不该被 lint 抢先拦掉。
    if len(names) == 1 and premise_count < 2:
        warnings.append('只收集到 1 个变元 %r，形式化很可能写漏了' % names[0])

    return warnings


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------

def verify(payload):
    premise_src = payload.get('premises') or []
    option_src = payload.get('options') or {}
    if not premise_src:
        raise ValueError('premises 不能为空')
    if not option_src:
        raise ValueError('options 不能为空')

    premises = [parse(p) for p in premise_src]
    options = dict((k, parse(v)) for k, v in option_src.items())

    names = set()
    for node in premises:
        collect_vars(node, names)
    for node in options.values():
        collect_vars(node, names)
    names = sorted(names)

    occurrences = {}
    for node in premises:
        count_vars(node, occurrences)
    for node in options.values():
        count_vars(node, occurrences)

    # 形式化有问题时，后面的判定再对也没有意义——公式压根不是这道题。
    # 放在真值表穷举之前短路，既省掉 2^n 次求值，也避免给出
    # verdict: ok 这种会被当成通过章的结论。
    lint = lint_variables(names, occurrences, len(premises))
    if lint:
        return {
            'id': payload.get('id'),
            'variables': names,
            'lint': lint,
            'verdict': 'bad_formalization',
            'reason': '形式化有问题，判定结果不可信，先修公式再跑：' + '；'.join(lint),
        }, 1

    # 前提合取的全部可满足赋值，也就是题干允许存在的那些世界
    models = []
    for combo in product([False, True], repeat=len(names)):
        env = dict(zip(names, combo))
        if all(evaluate(p, env) for p in premises):
            models.append(env)

    result = {
        'id': payload.get('id'),
        'variables': names,
        'premise_models': len(models),
        'options': {},
    }

    if not models:
        result['verdict'] = 'contradictory_premises'
        result['reason'] = '题干前提自相矛盾，没有任何赋值能同时满足，题目本身不成立'
        return result, 1

    for key in sorted(options):
        counter = None
        for env in models:
            if not evaluate(options[key], env):
                counter = env
                break
        item = {'entailed': counter is None, 'formula': option_src[key]}
        if counter is not None:
            item['counterexample'] = dict((k, bool(v)) for k, v in counter.items())
        result['options'][key] = item

    correct = [k for k in sorted(result['options'])
               if result['options'][k]['entailed']]
    result['entailed_options'] = correct

    claimed = payload.get('claimed_answer')
    if claimed is not None:
        result['claimed_answer'] = claimed

    if len(correct) == 1:
        if claimed is not None and claimed != correct[0]:
            result['verdict'] = 'wrong_answer_key'
            result['reason'] = ('唯一能推出的是 %s，但题目标注的答案是 %s'
                               % (correct[0], claimed))
            return result, 1
        result['verdict'] = 'ok'
        result['reason'] = '恰好一个选项能被前提必然推出：%s' % correct[0]
        return result, 0

    if not correct:
        result['verdict'] = 'no_answer'
        result['reason'] = ('没有任何选项能被前提必然推出，题干条件不足；'
                           '每个选项的 counterexample 就是它推不出的反例赋值')
        return result, 1

    result['verdict'] = 'multiple_answers'
    result['reason'] = ('有 %d 个选项都能被必然推出：%s，答案不唯一'
                        % (len(correct), '、'.join(correct)))
    return result, 1


def main():
    try:
        if len(sys.argv) > 1:
            with io.open(sys.argv[1], encoding='utf-8') as f:
                raw = f.read()
        else:
            raw = sys.stdin.read()
        payload = json.loads(raw)
    except Exception as exc:
        print(json.dumps({'verdict': 'bad_input', 'reason': str(exc)},
                         ensure_ascii=False, indent=2))
        return 2

    items = payload if isinstance(payload, list) else [payload]
    results = []
    worst = 0
    for item in items:
        try:
            res, code = verify(item)
        except Exception as exc:
            res, code = ({'id': item.get('id'), 'verdict': 'bad_input',
                          'reason': str(exc)}, 2)
        results.append(res)
        worst = max(worst, code)

    print(json.dumps(results if isinstance(payload, list) else results[0],
                     ensure_ascii=False, indent=2))
    return worst


if __name__ == '__main__':
    sys.exit(main())
