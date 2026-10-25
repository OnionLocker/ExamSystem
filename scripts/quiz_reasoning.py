"""文字判断专用命题与审核；复用 quiz_lite 的目录、补题、回执和入库。

规则按题型族切片：演绎（翻译、真假、组合排列）、论证（加强、削弱、解释、缺陷）、结构、日常结论，
每次命题与审核只带本组题型需要的规则。演绎题另附 formal，由 logic_model 穷举判定答案唯一。
"""
import json
import re
from datetime import date
from pathlib import Path

from logic_model import ASKS, family_of


CORPUS_PER_GROUP = 2


_THEME_PICKS: list[str] = []


def commit_theme_picks() -> None:
    """把本轮 writer_prompt 选中并实际出题使用的题材登记为今天已用。

    只读性的 logic_corpus_refs 不会写文件；只有真实出题入库流程（quiz_lite 主流程）
    在生成成功后才调用本函数落盘，避免测试或其他预览路径污染生产题材登记表。
    """
    global _THEME_PICKS
    if not _THEME_PICKS:
        return
    registry_path = Path(__file__).resolve().parents[1] / 'data' / 'manual-logic-theme-registry.json'
    try:
        if registry_path.is_file():
            reg = json.loads(registry_path.read_text(encoding='utf-8'))
            today = date.today().strftime('%Y-%m-%d')
            titles = set(_THEME_PICKS)
            changed = False
            for t in reg.get('themes') or []:
                if (t.get('title') or '').strip() in titles and t.get('last_used_at') != today:
                    t['last_used_at'] = today
                    changed = True
            if changed:
                reg['updated_at'] = today
                registry_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    finally:
        _THEME_PICKS = []


def logic_corpus_refs(offset: int = 0) -> str:
    """从 data/manual-logic-theme-registry.json 按轮换取 2 条题材参考，返回可注入段落。

    优先读题材登记表：按 last_used_at（null 最优先）+ 学科均衡选 2 条，只读不落盘，
    选中的题材记录到 _THEME_PICKS，由 quiz_lite 真实出题成功后调用 commit_theme_picks 登记。
    保证逻辑判断全模块共用一份题材池、不短期重复；多学科均衡轮换。
    登记表不可用或题材不足时，回退到旧逻辑：从 data/manual-logic-corpus/ 最新 corpus.json
    按 offset 轮换取 2 条。无素材或读取失败时返回空字符串（调用方静默跳过）。
    """
    registry_path = Path(__file__).resolve().parents[1] / 'data' / 'manual-logic-theme-registry.json'
    try:
        if registry_path.is_file():
            reg = json.loads(registry_path.read_text(encoding='utf-8'))
            themes = [t for t in (reg.get('themes') or []) if (t.get('title') or '').strip()]
            if len(themes) >= 2:
                # 未用过的（null）最优先；再按学科尽量分散
                def sort_key(t):
                    used = t.get('last_used_at') or ''
                    return (0 if not used else 1, used)
                themes.sort(key=sort_key)
                picked, used_disc = [], set()
                # 优先不同学科各取一条
                for t in themes:
                    if len(picked) >= 2:
                        break
                    disc = t.get('discipline') or ''
                    if disc and disc in used_disc:
                        continue
                    picked.append(t)
                    if disc:
                        used_disc.add(disc)
                # 不同学科不足 2 条时，再补同学科
                if len(picked) < 2:
                    for t in themes:
                        if len(picked) >= 2:
                            break
                        if t not in picked:
                            picked.append(t)
                if len(picked) >= 2:
                    global _THEME_PICKS
                    _THEME_PICKS = [t['title'].strip() for t in picked]
                    lines = [f"- [{t.get('discipline') or ''}] {t['title'].strip()}：{(t.get('summary') or '').strip()[:200]}" for t in picked]
                    return ('真实科研/调查语料题材参考（仅作情境与题材来源，可基于其场景构造题干，不得照抄原文或编造具体数据结论；'
                            '本组每题题材互不相同，也不要与 already_kept 同题材）：\n' + '\n'.join(lines))
    except Exception:
        pass
    # 回退：旧 offset 轮换
    try:
        base = Path(__file__).resolve().parents[1] / 'data' / 'manual-logic-corpus'
        days = sorted(base.iterdir(), reverse=True) if base.is_dir() else []
        for day in days:
            corpus = day / 'corpus.json'
            if not corpus.is_file():
                continue
            data = json.loads(corpus.read_text(encoding='utf-8'))
            refs, titles = [], []
            for cat, items in (data.get('results') or {}).items():
                for item in items:
                    if int(item.get('authority') or 0) < 3:
                        continue
                    summary = str(item.get('summary') or '')
                    title = str(item.get('title') or '')
                    if not title or len(summary) < 20:
                        continue
                    grams = {title[i:i + 2] for i in range(len(title) - 1)}
                    if any(len(grams & seen) / max(1, len(grams | seen)) >= 0.4 for seen in titles):
                        continue  # 多家网站转载同一报道，只留一条
                    titles.append(grams)
                    refs.append(f"- [{item.get('site')}] {title}：{summary[:300]}")
            if refs:
                start = offset * CORPUS_PER_GROUP % len(refs)
                picked = (refs[start:] + refs[:start])[:CORPUS_PER_GROUP]
                return ('真实科研/调查语料参考（仅作情境与题材来源，可基于其场景构造论证题干，不得照抄原文或编造具体数据结论；'
                        '本组每题题材互不相同，也不要与 already_kept 同题材）：\n' + '\n'.join(picked))
    except Exception:
        return ''
    return ''

WRITER_SCHEMA = {
    'type': 'object', 'required': ['questions'], 'additionalProperties': False,
    'properties': {'questions': {'type': 'array', 'items': {
        'type': 'object', 'required': ['index', 'stem', 'options', 'answer', 'analysis', 'kaodian_signal'],
        'additionalProperties': False,
        'properties': {
            'index': {'type': 'integer'},
            **{k: {'type': 'string'} for k in ('stem', 'answer', 'analysis', 'kaodian_signal')},
            'unsuitable': {'type': 'boolean'},
            'options': {'type': 'array', 'items': {
                'type': 'object', 'required': ['key', 'text'], 'additionalProperties': False,
                'properties': {'key': {'type': 'string'}, 'text': {'type': 'string'}},
            }},
            'formal': {'type': 'object', 'required': ['vars', 'constraints', 'options', 'ask'], 'properties': {
                'vars': {'type': 'array', 'items': {'type': 'object', 'required': ['name', 'values'], 'properties': {
                    'name': {'type': 'string'}, 'values': {'type': 'array', 'items': {'type': 'string'}}}}},
                'background': {'type': 'array', 'items': {'type': 'string'}},
                'constraints': {'type': 'array', 'items': {'type': 'string'}},
                'options': {'type': 'object', 'required': list('ABCD'),
                            'properties': {k: {'type': 'string'} for k in 'ABCD'}},
                'ask': {'type': 'string', 'enum': list(ASKS)},
                'conclusion': {'type': 'string'},
                'target': {'type': 'string'},
            }},
            'formal_skip': {'type': 'string'},
        },
    }}},
}

DIFFICULTY = """以练到指定知识点为主。auto自由安排；easy/mid/hard仅为意图，不是退题门槛。
actual_difficulty按解题必需的思考动作逐条对照，取所需最高一档：
easy：一步可得，矛盾、标志词或论证缺口原样给出，直接辨析；
mid：需一次额外动作，如一次等价转换（只有…才、除非…否则等改写）、反对关系、一次假设代入，或排除一个与正确项接近的干扰；
hard：需两个及以上相互依赖的动作，如多步转换、圈外复合命题判假后取反、假言连锁、分情况讨论，或至少两个干扰项须比较力度才能排除。
不强求边界、条件数或竞争错项数。
difficulty_reason说明实际思考动作，有效评档后difficulty_ok=true。简单但正确的题可通过，不虚标难度。
"""

COMMON_RULES = """只考当前目录中的文字逻辑判断；不出图形、空间、科学推理、定义判断或类比推理。
题面自足，答案来自题干与通常语义，不要求外部专业知识；模拟情境不冒充真实政策、科研结论或时事。
当前节点定义限定考点，讲解卡只作教学参考，不强制固定步骤、措辞、符号格式或唯一解法。
先区分设问：必然推出、可能成立、不能推出、加强、削弱、解释、缺陷、结构；不得混用判断标准。
题干必须明确给出作答任务（如找缺陷、找同构、必然或可能等），不能只陈述一段论证而省略设问，让学生从考点标签或选项猜任务。
逐项核对其他选项是否同等或更优；若无法以明确条件或论证差异区分，应拒绝，不猜命题意图。
解析结论与理由都须正确；不把一种可行情况写成唯一，不添加题干没有的排他条件。
解析只保留核定后的推理，不混入试写、自我更正或同一假设下互相矛盾的判断。
"""

DEDUCTION_RULES = """演绎题：区分充分必要、逆否与逆命题，“只有P才Q”为Q→P；否前不能否后、肯后不能肯前。
“或”默认相容，除非题面明确二选一；全称不自动保证对象存在。“有的”不等于“大多数”。
必然成立须排除反例；可能成立给一个满足全部条件的例子即可；不能推出包含未知与被反驳，不能一律当假。
真假推理须把每人整句话作为一条判断，“且/或/如果”按完整语义算真假，不暗加每人只说一个简单命题。
组合排列写清对象、名额、顺序与一一对应条件，检查所有可行情形；唯一答案不要求完整安排唯一。
涉及数值边界写清是否包含端点，不能混用“超过90”和“达到90”的否定；排队/日期间隔用“中间恰有2人/2天”或“序号相差2”，避免“相隔2天”的两种读法。
"""

DAILY_RULES = """日常结论不扩大对象、比例、时间或条件，不凭常识补材料，不把“可能”自动当正确。
必然成立须排除反例；“有的”不等于“大多数”，“多数”不等于“全部”。
"""

ARGUMENT_RULES = """加强/削弱按对论点的支持力度比较，不要求加强项单独证明结论、削弱项彻底推翻；多个有作用时须有唯一最强项。
必要前提的选项若包含某一种具体机制，必须证明该机制不可替代；不能把“可通过其他机制成立”误说成“否定此机制便完全无效”。
写必要前提选项时只补所需关联，不擅加题干未限定的具体实现途径；补充可行机制适合加强设问，不能自动当必要前提。
错项比较不能捏造群体占比、事件时间、效应大小；“多数”不得改读“少数”。若题干没有区分两项力度的依据，先修题面，不能编事实排除。
先识别论据、论点与缺口；区分样本偏差、另因、倒因、桥梁和必要前提。前提题否定检验不能当作所有加强题的硬要求。
原因解释须同时容纳并解释题干两方面现象，不能直接否定现象或只重复其中一面。
论证缺陷识别真实跳步，不靠主题词相似度；不从相关性推出确定因果。
排除一个竞争原因不能“直接证明”因果；多数情况有效不等于仅此一种机制，“通常只”不能改写为“绝对不能”。加强削弱的解析用支持/质疑表述实际效果，不夸成必然保证/根本不可能。
"""

STRUCTURE_RULES = """论证结构比较推理关系、方向和量词，不靠主题词相似度。
论证结构先将题干与四项统一翻译成同一种蕴含方向再比较。“只有P才Q，非P故非Q”是Q→P的逆否，与“如果A则B，非B故非A”同构，不能仅因一个用只有、另一个用如果而排除；若两项归一后同构须重写错项。
"""

FAMILY_RULES = {'deduction': DEDUCTION_RULES, 'daily': DAILY_RULES, 'argument': ARGUMENT_RULES, 'structure': STRUCTURE_RULES}
FAMILY_ORDER = ('deduction', 'daily', 'argument', 'structure')


def rules_for(families) -> str:
    """通用规则加本组题型族的专属规则；族未知时给全部，宁多勿漏。"""
    chosen = [f for f in FAMILY_ORDER if f in set(families or ())] or list(FAMILY_ORDER)
    return COMMON_RULES + ''.join(FAMILY_RULES[f] for f in chosen)


LOGIC = rules_for(FAMILY_ORDER)

FORMAL_WRITER = f"""演绎题（翻译推理、真假推理、组合排列）每题另附 formal，程序会穷举全部情形判定答案是否唯一：
- vars：每个未知量一项 {{"name","values"}}。name 用不含空格和符号的中文或字母；真假量 values 写 ["bool"]；数值量写成数字字符串如 ["1","2","35"]，程序自动当整数参与四则运算和比较；类别写 ["红","蓝"]，表达式里字符串加英文双引号。全部取值组合不超过40万种。
- constraints：题干每个条件一条表达式（Python 写法）：and/or/not、== != < <= > >=、in、+ - * %，以及 implies(p,q)、iff(p,q)、count(...)、exactly/atleast/atmost(k,...)、distinct(...)、adjacent(a,b)、abs/int/min/max。数值推算类组合排列同样可以形式化。设问里“如果……”的附加条件也写进来。
- 真假推理：每人一句话设一个布尔量（如 甲真），用 iff(甲真, 该句完整内容) 绑定，再写真话人数，如 exactly(1, 甲真, 乙真, 丙真)。
- 全称句（所有、凡是、每个）须对每个对象分别建模，不能只写其中一人；“或”按相容写 or，题面明确二选一才写 !=。
- options：A–D 各一条表达式，意思与选项文字逐一对应，不得改写成更容易判定的说法。
- ask：{'；'.join(f'{name}={label}' for name, label in ASKS.items())}。sufficient_premise 另写 conclusion；max/min 另写 target，选项写整数。
- background：题目结构设定（每人负责一个、只选派一人、名次无并列等）单独放这里，不写进 constraints。
- 程序判定须恰好一个选项满足设问且等于 answer；还会逐条删去 constraints 重判，去掉后答案仍唯一的凑数条件超过 1 条、或真正用到的条件少于 2 条，整题退回。
- 确实无法有限穷举的题（如跨对象的直言三段论）不写 formal，改写 formal_skip 说明原因，改由逐句审核。
"""

REAL_LEVEL = """默认按广东省考真题水平命题（auto 同样适用）：不出一眼看穿、一步可得的题；四个选项都紧扣题干，至少两个干扰项需要辨析才能排除，明显无关的凑数项最多一个。
"""

DEDUCTION_DEPTH = """演绎题参照广东真题的推理量：
- 翻译推理：题干给 3–4 条相互关联的条件，混用“如果…那么”“只有…才”“除非…否则”“只要…就”“至少…之一/至少两个”“不能都”中至少两种句式；或给两条可串联的假言，让选项考连锁、逆否与肯后、否前陷阱。不出“一条规则加一个事实、一步推出”的题。载体与情景自由多样（日常生活、商业、科研、社会管理等均可，不一律“某单位/某部门+规章制度”套话），句式多样性须保留，答案唯一性由判题器兜底。
- 题干不得替考生翻译或解释逻辑关系：禁止“即……”“也就是说”“换言之”“等价于”及括号注释式改写。
- 分析推理（组合排列）：3–5 条条件且每条都参与推理，多用相邻/隔一个/左右、高低比较、条件句、名额限制；设问优先用“如果……则必然正确的是”“补充哪项可以确定……”“以下判断错误/不可能的是”“可能为真”。不要四个选项都给完整对应、逐条扫一遍就排除完；排除法变式也要每个条件至少排除一项，且需组合两个条件才能锁定答案。载体与情景自由多样（社区、竞赛、科研、日常生活均可，不一律“某单位/某县+甲乙丙丁+干部专家”套话），答案唯一性由判题器兜底。
- 真假推理：至少 3 人表态且含复合命题（且/或/如果），需借助矛盾、反对关系或假设代入；不能有人直接说出答案。
"""

ARGUMENT_DEPTH = """论证题参照广东真题：题干是有具体机制或数据的科研、调查、政策论证，论据与结论之间有可识别但不直白的缺口（概念偷换、样本外推、指标替代、措施与目的错位、类比不当等）。正确项精准对准缺口；至少一个干扰项与正确项同话题、只在方向、对象或力度上差一点（半对项）。设问在“最能支持/削弱”之外，也要用“需要补充的前提”“暗含前提”“最不能支持”“最能反驳”。结构相似题四个选项结构各异，至少一项只差量词或推理方向。
解析描述加强/削弱力度时禁用“切断因果/证明/保证/必然/彻底/根本”等绝对断言，改说“有力削弱/强化了归因概率/使推论更可信”等留有余地的表述；解析不得把“有助于削弱”夸大成“彻底否定”，也不得把“多数有效”夸大成“唯一机制”。
"""

DAILY_DEPTH = """日常结论题参照广东真题：题干是带背景与机制的科研、调查或随访陈述（随访年限、样本构成、检出率差异、机制检测等），通过长句和术语制造真实阅读负荷，但不考专业背景，只考“能推出/不能推出”。
设问按考法变式：正向归纳（@daily-infer）用“由此可以推出的是”，选非找茬（@daily-flaw）用“由此不能推出的是”，不得混用。
正向归纳时，正确项用“可能/部分/一定程度上/往往”等从弱词收拢机制，干扰项设“绝对化因果断言、无端比较、调查主体跨界、把伴随当因果”等坑；
选非找茬时，干扰项（即正解）设“强加因果、局部偷换整体、属性概念偷换、可能偷换必然、无依据添加比较”中的一种，其余三项须为可推出的从弱事实。
"""

HIDE_TRAPS = """正确项禁止照抄题干原句，须同义转述、逆向概括或机制收拢；极端绝对化词（必然/唯一/所有/绝对/决定了等）干扰项每道最多 1 个，其余干扰项须做成“看似符合生活常识、实则因果跃迁、主体偷换、范围跨界或概念偷换”的隐蔽坑，禁止靠绝对词一眼暴露。
"""

FORMAL_EXAMINER = """item 带 formal 时，程序已按 formal 穷举判定（formal_result）。你只需核对 formal 是否忠实于题面：
每个题干条件都有对应约束、没有题干之外的额外条件、选项表达式与选项文字意思一致（全称/特称、或的相容、端点、主体不偷换）、ask 与设问一致。
返回 formal_ok（true/false）与 formal_reason（逐条对照的依据，或指出哪条约束/选项译错）；formal 不忠实则 verdict=REJECT。没有 formal 的题给 formal_ok=true、formal_reason="无形式化"。
"""

BLIND_HEAD = "你是文字判断独立作答者，看不到标答、解析和请求难度。\n"
BLIND_TAIL = """steps给出最短充分推理及各选项关键差异；演绎题检查反例，论证题比较作用力度。
also_valid列除answer外同样或更符合设问的选项；矛盾、条件不足或无正确项时unsolvable=true。
输出JSON：{"questions":[{"id":"...","answer":"A","steps":"推理和逐项核对",
"actual_difficulty":"mid","difficulty_reason":"实际推理动作","also_valid":[],"unsolvable":false,"reason":""}]}。
"""

EXAMINER_HEAD = "你是文字判断审核者。独立核对题干与所有选项，然后核对解析；不能用标答作为正确证据。\n"
EXAMINER_CORE = """kaodian_ok检查当前定义与实际考查动作，不因解法不同判错；style_ok只看清楚自然、信息完整，不强求真题篇幅与复杂干扰。
analysis_ok逐句核对原解析的推理方向、隐含前提、完整条件及逐项排除依据；analysis_check写出原句核查，不能只重做一遍题替代检查原文。
特别检查同一假设下的真假、数值与角色是否前后冲突。即使后文自行改正、最终答案正确，前文残留错误也须analysis_ok=false，要求删去错误草稿后重审；不能替作者自动更正后判PASS。
necessity_claims在本模块列出解析全部原句；每个claim_index返回necessity_checks的valid/reason。逐句判断该句在本设问下是否有依据，不是要求所有支持/削弱关系都为必然蕴含。对必然性或唯一性断言先尝试反例。
"""
EXAMINER_ARGUMENT = """论证题的“支持/削弱”不等于必然蕴含。解析若夸成“证明/保证/必然”，须验证这个更强结论，不能默默改读为“有帮助”。
“彻底颠覆、切断因果、表明主要由另一原因所致”同样是强断言。另因或倒因通常只削弱，不能据此断言原因完全无效；“有的群体较小”须有题干依据，不能靠想象。
"""
EXAMINER_TAIL = """brief_ok核对用户要求，跨题要求按batch_slots和batch_questions检查。任一实质问题REJECT；难度偏差或简洁讲解不是实质问题。
items只是本轮待审子集，分组审核或补题时少于整批是正常的，绝不能据items数量判缺题。总题量、标签与配额由程序校验；跨题语义要求只看batch_questions。只为items中的题返回记录，不因其他待补题牵连本题。
variant_match：declared_brief注明“本题考法变式：xxx”时，核对本题实际设问结构与解题动作是否属于该变式，返回{"ok":true,"reason":"依据"}；
退回该考点最常见默认考法、或只换场景不换解题动作则ok=false并写明差在哪。没有注明考法变式就给{"ok":true,"reason":"无细分考法"}。
输出JSON：{"questions":[{"id":"...","actual_difficulty":"mid","difficulty_reason":"实际推理动作",
"analysis_check":"设问、关键推理与选项核对","necessity_checks":[{"claim_index":0,"valid":true,"reason":"推导或反例"}],
"verdict":"PASS","difficulty_ok":true,"kaodian_ok":true,"style_ok":true,"analysis_ok":true,"brief_ok":true,
"variant_match":{"ok":true,"reason":"依据"},"formal_ok":true,"formal_reason":"依据","issues":[]}]}。
"""


SPOON_FED = re.compile(r"[（(]\s*即|即并非|也就是说|换言之|换句话说|等价于")


def stem_issues(question: dict) -> list[str]:
    """不花模型调用的题面检查：演绎题不得替考生翻译逻辑关系。"""
    if family_of((question.get('tags') or [''])[0]) != 'deduction':
        return []
    hit = SPOON_FED.search(str(question.get('stem') or ''))
    return [f'题干替考生翻译了逻辑关系（“{hit.group()}…”），删去解释性改写，让考生自己翻译'] if hit else []


def blind_system(families=None) -> str:
    return BLIND_HEAD + DIFFICULTY + rules_for(families) + BLIND_TAIL


def examiner_system(families=None) -> str:
    families = set(families or FAMILY_ORDER)
    argument = families & {'argument', 'daily', 'structure'}
    formal = 'deduction' in families
    return (EXAMINER_HEAD + DIFFICULTY + rules_for(families) + EXAMINER_CORE
            + (EXAMINER_ARGUMENT if argument else '') + (FORMAL_EXAMINER if formal else '') + EXAMINER_TAIL)


def is_blind_system(system: str) -> bool:
    return str(system).startswith(BLIND_HEAD)


def is_examiner_system(system: str) -> bool:
    return str(system).startswith(EXAMINER_HEAD)


BLIND = blind_system()
EXAMINER = examiner_system()

CLAIMS = """你只检查逻辑教学断言是否有依据，不做选择题，也不知道标答。context为题干，options为选项，claim为待核验原句。
若输入task为question_check，先核查明确设问，再独立比较全部选项，输出PASS与唯一选项理由，或REJECT与缺失设问/双解/无解理由。论证结构必须先将题干与每项统一写成P→Q、Q→P等形式，再比较；必要条件的逆否和充分条件的逆否是同一种结构，不能以汉语句式不同排除同构项。不得以“更贴近原句”从两项同构中硬选一项。
逐句查前提、推理方向、量词、排除理由和强弱程度。只用题干与对应选项，不把原解析自加的事实视为已知。
先检查每句中“直接证明、确系、根本无法、切断、彻底、唯一、必须、只能”等最强主张，reason引用该主张并给反例或依据。没有此类主张则检查该句核心关系。不能笼统写各项分析正确。
先尝试满足题干及选项的反例，再判原句。reason须指出具体依据或反例，不用“符合逻辑/解释合理”代替验证。
句中每条理由都要正确。最终择优没错，不代表中间理由可以错；一句含一个实质错误便REJECT。
不因解析简洁或不够复杂拒绝，不强求支持/削弱项本身能证明/推翻。一般力度比较有依据即可。
但原句若说“彻底颠覆/切断因果/表明主因”，就按这句强断言核查，不能自动改读为“有助于削弱”。
校准反例（不是禁用题材）：
1. 患病在先、改习惯在后，可以削弱“习惯引起患病”的证据，但仍可能加重已有病情；不能说彻底排除其因果作用。
2. 对照城市同样下降，只支持可能存在共同原因，不证明两个城市的实际主因相同，更不能直接断言一定是气候导致。
3. “大多数渔民离城”不等于“部分渔民在全市占比较小”，缺少人口或就诊构成不能补比例来排除另因。
4. 必要前提选项中的具体机制须整体否定：A通过机制M减少B，其否定可以是A通过另一机制N减少B；不能把否定“通过M有效”偷换为“A完全无效”。
遇到“必要前提、不可或缺、反面代入”，reason必须逐字对照options中被讨论选项的完整内容，写出包含限定词的准确否定与反例。禁止将选项简化后再否定。
例如结论“运动通过提高X来降低疾病Y”，选项“X通过减轻组织M炎症降低Y”：所需的是X有保护作用，不一定通过M。原句把该选项否定成“X对Y毫无作用”就是偷换，必须REJECT；不能用模型记忆的医学机理补齐题干。
5. 同一假设下先写某人说假话、后又说真话，即使最终改对仍有错误草稿，须REJECT并修正。
所有编号都必须返回。仅调用一次submit_review，各c编号对应同名输入，值以PASS或REJECT开头，后接具体依据或反例。
"""


def writer_prompt(run, asks, kept, cards):
    diffs = {str(a.get('difficulty') or 'auto') for a in asks}
    families = {family_of(a.get('tag')) for a in asks}
    extra = []
    if diffs - {'easy'}:
        extra.append(REAL_LEVEL)
        extra.append(HIDE_TRAPS)
        if 'deduction' in families:
            extra.append(DEDUCTION_DEPTH)
        if families & {'argument', 'structure'}:
            extra.append(ARGUMENT_DEPTH)
        if 'daily' in families:
            extra.append(DAILY_DEPTH)
    if diffs & {'auto', 'mid', 'hard'}:
        extra.append(
            '要求接近省考真题火候：论证结构更隐蔽，不能靠标志词直接秒杀；'
            '干扰项做成语义纠缠型（半对半错、程度偏差、偷换主体、以偏概全），禁止一眼跑偏；'
            '情境优先采用科研实验、调查研究、机制分析等真实可感场景，避免空泛政策腔。'
        )
    if 'hard' in diffs:
        extra.append(
            'hard档进一步要求：至少两个干扰项与正确项高度相似，需仔细权衡论证力度或逻辑方向才能排除；'
            '结论与论据之间的缺口更隐蔽，必要前提或削弱点不直接显式给出。'
        )
    return '\n'.join([
        '你负责广东省考文字判断专项。items每项一道，保留全局index。',
        json.dumps({'items': asks, 'topic_definitions': cards, 'already_kept': kept}, ensure_ascii=False),
        DIFFICULTY, rules_for(families),
        *([FORMAL_WRITER] if 'deduction' in families else []),
        *extra,
        *([corpus] if (corpus := logic_corpus_refs(min(int(a.get('index') or 0) for a in asks) // 3)) else []),
        '在考点内自由设计情境、设问和解法，四项A/B/C/D有唯一正确或唯一最佳项。不要写教材术语选择题代替实际推理。',
        '干扰项对应真实常见误推；同批变化论证关系或约束结构，不能只换人名、数字或行业。',
        'analysis直接给学生关键推理与其他选项的主要差异，简洁但充分；不要求固定标题、算式或穷尽所有解法。通常用100至200字说明关键依据即可（不是硬限），删除多余的强断言，不因选择题有最佳答案就宣称已证明因果。',
        'kaodian_signal说明实际考查动作。退回后处理具体错误；repair=analysis_only时保留题面、选项、答案只修解析，仍接受重审。',
        '题目本身双解、无解或跨考点须重写；确实不能满足范围返回unsuitable:true，不输出改题草稿。',
        '每个stem写完整明确的设问。只输出合法JSON，questions数组内只有题目对象，不追加难度评价或总结文字：{"questions":[{"index":1,"stem":"...","kaodian_signal":"...",'
        '"options":[{"key":"A","text":"..."},{"key":"B","text":"..."},{"key":"C","text":"..."},{"key":"D","text":"..."}],'
        '"answer":"A","analysis":"..."}]}。',
    ])
