"""言语专用命题与语境复核；目录、补题、证据和入库仍由 quiz_lite 负责。

规则按题族切片：逻辑填空、语句表达、片段阅读。每次命题和审核只带本组需要的规则。
选项之间没有大小或增减关系，审核前把正确项字母摊开，避免整卷堆在同一个选项。
"""
import json
import random
import re
from collections import Counter
from pathlib import Path


FAMILY_ORDER = ("fill", "sentence", "reading")
GROUP_SIZE = {"fill": 3, "sentence": 2, "reading": 2}
CORPUS_PER_GROUP = 2


def family_of(tag: str) -> str:
    text = str(tag or "")
    if "逻辑填空" in text:
        return "fill"
    if "语句表达" in text:
        return "sentence"
    return "reading"


_PLAIN_NUMBER = re.compile(r"^\s*[+-]?\d+(?:\.\d+)?%?\s*$")


def letters_movable(question: dict) -> bool:
    """四个选项没有数值顺序时，正确项可以换字母。纯数字选项保持原顺序。"""
    if str(question.get("category") or "") != "言语理解与表达":
        return False
    if str(question.get("question_type") or "single") != "single":
        return False
    options = [item for item in (question.get("options") or []) if isinstance(item, dict)]
    by_key = {str(item.get("key") or ""): item for item in options}
    if set(by_key) != set("ABCD"):
        return False
    if str(question.get("answer") or "") not in set("ABCD"):
        return False
    texts = [str(by_key[key].get("text") or "") for key in "ABCD"]
    return not all(_PLAIN_NUMBER.match(text) for text in texts)


def balance_verbal_letters(questions: list[dict], *, locked: set[str], seed: str) -> int:
    """把未审过的言语题正确项摊到 A–D。已审过的字母不动。解析里的选项称呼随字母对调。"""
    from normalize_ai_batch import letter_counts, swap_option_pair

    fixed: list[str] = []
    movable: list[dict] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        answer = str(question.get("answer") or "")
        qid = str(question.get("external_id") or "")
        if qid in locked or not letters_movable(question):
            if answer in set("ABCD"):
                fixed.append(answer)
            continue
        movable.append(question)
    if len(fixed) + len(movable) < 2 or not movable:
        return 0
    ideal = dict(zip("ABCD", letter_counts(len(fixed) + len(movable))))
    counts: Counter[str] = Counter(fixed)
    rng = random.Random(seed)
    changed = 0
    for question in movable:
        deficit = {letter: ideal[letter] - counts[letter] for letter in "ABCD"}
        best = max(deficit.values())
        letter = rng.choice([item for item in "ABCD" if deficit[item] == best])
        counts[letter] += 1
        src = str(question.get("answer") or "")
        if src != letter and swap_option_pair(question, src, letter):
            changed += 1
    return changed


def verbal_groups(asks: list[dict]) -> list[list[dict]]:
    """先按题族分开，再按族的组大小切开。填空一组建 3 题，片段和语句一组建 2 题。"""
    grouped = sorted(asks, key=lambda ask: (FAMILY_ORDER.index(family_of(ask.get("tag"))), int(ask.get("index") or 0)))
    groups = []
    for family in FAMILY_ORDER:
        rows = [ask for ask in grouped if family_of(ask.get("tag")) == family]
        size = GROUP_SIZE[family]
        groups.extend(rows[start:start + size] for start in range(0, len(rows), size))
    return groups


def verbal_corpus_refs(offset: int = 0) -> str:
    """从 data/manual-verbal-corpus/ 读取最近权威语料摘要。按组轮换，避免同批挤到同一题材。"""
    try:
        base = Path(__file__).resolve().parents[1] / "data" / "manual-verbal-corpus"
        days = sorted(base.iterdir(), reverse=True) if base.is_dir() else []
        for day in days:
            corpus = day / "corpus.json"
            if not corpus.is_file():
                continue
            data = json.loads(corpus.read_text(encoding="utf-8"))
            refs = []
            for _cat, items in (data.get("results") or {}).items():
                for item in items:
                    if int(item.get("authority") or 0) < 3:
                        continue
                    summary = str(item.get("summary") or "")
                    title = str(item.get("title") or "")
                    if not title or len(summary) < 20:
                        continue
                    refs.append(f"- [{item.get('site')}] {title}：{summary[:300]}")
            if refs:
                start = offset * CORPUS_PER_GROUP % len(refs)
                picked = (refs[start:] + refs[:start])[:CORPUS_PER_GROUP]
                return "真实权威语料参考（仅作题材来源，可基于其主题改写题干，不得照抄原文段落）：\n" + "\n".join(picked)
    except Exception:
        return ""
    return ""


USAGE_EXAMPLES = """以下是校准辨析方式的反例，不是指定题材、选词或禁用表：
教育部《成语典》“饮鸩止渴”的比喻义是只顾解决眼前困难、不顾后患，不要求性命攸关；“因地制宜”按不同环境的实际情况采取适当办法，不限自然地理。
因此，排除一个选项可说“本文未呈现其所强调的眼前困境”，不能说“没有生命危险就不能用”；可比较“量力而行”的能力限度与“因地制宜”的具体条件，不能声称后者只能用于地域。
“恶意辩驳”可以成立：若整组不及“攻讦”，须指出题文从论点转向个人攻击的具体对象变化，不能说辩驳是中性词所以不能和恶意搭配。
“挤压空间”常见，不等于“剥夺空间”非法。正项常用只是正项依据，不能代替错项的真实缺陷；若完整代入后无法辨出唯一最佳，应改题或明确拒绝。
以上来源仅支持对应词义，不得声称查过其他词典或捏造引文。"""

USAGE = """你审核现代汉语教学断言，不做选择题，不知道标答。下面仅摘取解析中涉及用法限制的句子，核对其中是否有会误导学习的实质错误。
对于搭配禁令先反证：被声称不合法的词组能否在自然汉语中构成含义明确的用法？尝试造一个自然例句。
常用频率低不等于搭配错误，较不精确不等于不能使用。不能从常与A搭配推出不可与B搭配。
普遍禁令存在自然反例时返回REJECT；“在本题不贴切/搭配不当”须按原句对象和上下文核对，不要求证明在任何语境都不能用。
不因讲解简洁、没有穷尽词义或采用不同老师的正确解法而拒绝。不编造题干没有的前提，不把中性词一律排除于负面语境。
context为原题语境，用于判断“在本句不合适”和“任何场合均不合法”的区别；只有声称普遍禁用才用其他语境反证。一般的择优说明不因存在其他可用语境而判错。
reason说明具体含义冲突或自然反例，不能仅复述“习惯搭配”。
每句可能含多条理由，任何一条错误都应REJECT，不能因为总体择优结果成立而忽略错误释义或虚构限制。
仅调用一次submit_review提交全部结果。每个c编号对应同名输入断言，值为字符串，以PASS或REJECT开头，后接该句具体依据或自然反例。所有编号都必须返回。
""" + USAGE_EXAMPLES

DIFFICULTY = """本次目标是练到指定知识点，不强求难度。未指定难度为auto；easy/mid/hard是命题倾向，不是退题门槛。
能用一个关键线索排除也有训练价值，不要求固定数量的强干扰项，不为凑难度加术语、生僻词、空格或复杂句。
actual_difficulty按作答必需的辨析动作逐条对照，取所需最高一档：
easy：一步可得，关键词、关联词或语境线索直接指向答案，错项与正确项差别明显；
mid：需一次额外动作，如结合上下文语境比较、辨析一对近义词或搭配、识别一层转折/递进/让步，或排除一个与正确项接近的干扰；
hard：需两个及以上相互依赖的动作，如线索隐含须先概括再比较、多空或多处信息相互制约、需同时辨析程度轻重与适用对象，或至少两个干扰项须细致比较才能排除。
边界不必争论。
difficulty_reason简述实际作答依据，difficulty_ok在有效评档后为true，不因与请求档位不一致而REJECT；入库单题记录实际评级，不虚标。"""

COMMON_RULES = """答案依据来自给定文段及通常汉语用法，不需要外部专业知识或猜命题人意图。
每题必须有唯一正确或唯一最佳选项；若另有同样好或更好的选项，或必须补隐含前提才能定答案，应拒绝。
不把“全部/唯一”自动判错或“可能/往往”自动判对。讲解卡限定考点范围，其口诀不能替代原文证据。
只核对考查任务与目标是否一致，不因问法、句式、主题、正确解法与参考卡不同而拒绝。
重复应指实际论证/辨析骨架和错项设计相同，不能仅因两题都用“不仅…更…”等连接词就判重复。
"""

FILL_RULES = """逻辑填空：把各组选项全部代入，核对搭配对象、语义轻重、感情色彩和上下句关系。
常规择优比较即可；不能仅因另一个词孤立看也能使用就判双解，也不能凭“更顺口”排除同样合适的选项。
词语搭配和适用对象须符合通常用法，不能把常见搭配说成唯一合法搭配；不能仅凭“显露”等隐喻就硬分听觉、视觉并排除词语。
成语实词综合可以是成语、实词或二者同题；子点细分限定辨析动作，不改变父级题型。
指定了词库目标词时，正确项必须用上该词，题干空格处不能写出该词；易混词可以做干扰，排除理由必须来自本题语境。
"""

SENTENCE_RULES = """语句表达：排序要按指代、时序、话题推进和衔接比较所有备选次序，不能以固定首句口诀代替判断。
语句填空按横线所在位置衔接前后话题，不能改成主旨概括。
接语须依据末尾话题和未完成的信息预测紧接内容，不能把尾句换个说法再当下一句。
"""

READING_RULES = """片段阅读：主旨和标题须覆盖文段核心与重点，不能要求错项在任何语境下都错误；部分符合、片面或范围不当可构成不最佳。
细节判断须区分原文支持、原文反驳、无法确定，并核对选正或选非；未提及不等于事实为假。
词句理解须在原语境解释指定词句，不能脱离文段另给词典义。
"""

FAMILY_RULES = {"fill": FILL_RULES, "sentence": SENTENCE_RULES, "reading": READING_RULES}

READING_LEVEL = """片段阅读接近省考真题火候：主旨句不得直接出现在“因此/然而/可见/关键在于/唯有/必须”等标志词后，
须藏在论证中段或需要考生归纳；干扰项做成语义纠缠型（半对半错、程度偏差、主体偷换、无中生有），禁止一眼跑偏的选项。
文段语体多样化，可用科普、文化、经济评论等，不全用政策腔。
"""

SENTENCE_LEVEL = """语句表达接近省考真题火候：排序至少有两处需要指代或话题捆绑才能确定，不能靠“首句总起”口诀排完；
语句填空的正确句要同时接住前后话题；接语要顺着末尾未完成的信息往下走，不能复述尾句。
"""

FILL_LEVEL = """逻辑填空接近省考真题火候：正确项和至少一个干扰项要在词义上接近，必须靠语境、搭配或程度才能分开；
禁止三项都是明显不通的词。多空题要让空与空互相制约，不能每一空都单独一眼可填。
"""

BLIND_HEAD = "你是言语理解独立作答者，看不到答案、解析或请求难度。\n"
BLIND_TAIL = """steps先给最短充分作答路径，再核对其他选项是否同样成立，不强迫把每空每词都展开；difficulty_reason据最短路径评档。also_valid只列除answer之外同样或更适合的选项。
条件不足或存在等优答案时unsolvable=true并说明；所有字段必须填写。
只输出JSON：{"questions":[{"id":"...","answer":"A","steps":"逐项比较及语境依据",
"actual_difficulty":"mid","difficulty_reason":"实际必要辨析及竞争项",
"also_valid":[],"unsolvable":false,"reason":""}]}
"""

EXAMINER_HEAD = "你是言语命题审核者。自己核对文段与各选项，再核对解析，不以标答或盲解结论作证据。\n"
EXAMINER_TAIL = """kaodian_ok核对declared_kaofa与topic定义，不能把细节、词句、接语、标题都改成主旨；但不强制特定设问词。
style_ok只检查题面清楚、自然、信息完整；不强制真题文风、专业题材、文段长短或干扰项数量。基础题和一步排除法可通过。
analysis_ok核对核心依据、选项关键差异和结论，analysis_check简述核查依据。允许老师式的简洁讲解，不要求逐空解释每个词或穷尽所有推理路径。
逐句核查解析的排他理由：把“更贴切/更常见”说成另一个词“不能搭配/只能用于某对象/语法错误”，须找出真实的语义或语法冲突；
若只是频率或侧重差别，不能证明另项用法错误，应analysis_ok=false。尤其不能根据讲解卡的简化口诀制造用法禁令。
即使正确答案仍是唯一最佳，错误的排除理由也必须退回修订；核查所有选项，不把标答成立当作解析成立。
necessity_claims是程序摘取的高风险用法断言；整体解析仍按上述要求核对，不要求为每个普通说明句另建记录。每个输入claim_index必须返回一项necessity_checks。
核对这些句子的词义、原文依据与排除理由；会误导学习的错误判valid=false，不因合理择优说明不够绝对或不够详尽而拒绝。
对搭配禁令，先用被排除词组尝试构造自然且含义明确的句子；若可以成立，原解析不能再声称该搭配不合法。
每条返回claim_index/valid/reason，reason说明构造的反例或真正的语义语法冲突；没有断言则为空数组。brief_ok按用户额外要求审核。
variant_match：declared_brief注明“本题考法变式：xxx”时，核对本题实际设问结构与解题动作是否属于该变式，返回{"ok":true,"reason":"依据"}；
退回该考点最常见默认考法、或只换场景不换解题动作则ok=false并写明差在哪。没有注明考法变式就给{"ok":true,"reason":"无细分考法"}。
只输出JSON：{"questions":[{"id":"...","actual_difficulty":"mid","difficulty_reason":"实际辨析依据",
"analysis_check":"文段依据及逐项核查","necessity_checks":[{"claim_index":0,"valid":true,"reason":"语境依据"}],
"verdict":"PASS","difficulty_ok":true,"kaodian_ok":true,"style_ok":true,"analysis_ok":true,"brief_ok":true,
"variant_match":{"ok":true,"reason":"依据"},"issues":[]}]}
任一实质问题返回REJECT和原因。不因参考卡写了固定步骤就排斥另一种正确解法。
"""


def rules_for(families) -> str:
    chosen = [family for family in FAMILY_ORDER if family in set(families or ())] or list(FAMILY_ORDER)
    return COMMON_RULES + "".join(FAMILY_RULES[family] for family in chosen)


def blind_system(families=None) -> str:
    return BLIND_HEAD + DIFFICULTY + rules_for(families) + BLIND_TAIL


def examiner_system(families=None) -> str:
    return EXAMINER_HEAD + DIFFICULTY + rules_for(families) + EXAMINER_TAIL


def is_blind_system(system: str) -> bool:
    return str(system).startswith(BLIND_HEAD)


def is_examiner_system(system: str) -> bool:
    return str(system).startswith(EXAMINER_HEAD)


BLIND = blind_system()
EXAMINER = examiner_system()

WRITER_SCHEMA = {
    "type": "object", "required": ["questions"], "additionalProperties": False,
    "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "required": ["index", "stem", "options", "answer", "analysis", "kaodian_signal"],
        "additionalProperties": False,
        "properties": {
            "index": {"type": "integer"},
            **{key: {"type": "string"} for key in ("stem", "analysis", "kaodian_signal")},
            "answer": {"type": "string", "enum": ["A", "B", "C", "D"]},
            "unsuitable": {"type": "boolean"},
            "options": {"type": "array", "items": {
                "type": "object", "required": ["key", "text"], "additionalProperties": False,
                "properties": {"key": {"type": "string", "enum": ["A", "B", "C", "D"]},
                               "text": {"type": "string"}},
            }},
        },
    }}},
}


def writer_prompt(run, asks, kept, cards):
    families = {family_of(ask.get("tag")) for ask in asks}
    diffs = {str(ask.get("difficulty") or "auto") for ask in asks}
    extra = []
    if diffs - {"easy"}:
        if "reading" in families:
            extra.append(READING_LEVEL)
        if "sentence" in families:
            extra.append(SENTENCE_LEVEL)
        if "fill" in families:
            extra.append(FILL_LEVEL)
        if "hard" in diffs and "reading" in families:
            extra.append("hard档片段：文段信息密度更高、论证层次更隐蔽；至少一个干扰项与正确项高度相似，正确答案必须是唯一最佳。")
    corpus = ""
    if families & {"reading", "sentence"}:
        offset = min(int(ask.get("index") or 1) for ask in asks) // 2
        corpus = verbal_corpus_refs(offset)
    vocab_note = ""
    if any(ask.get("vocab_brief") for ask in asks):
        vocab_note = (
            "带 vocab_brief 的填空题：正确选项必须包含该指定词，题干用空格，不能把指定词写进题干。"
            "按释义和易混关系自拟语境，不得照抄词库例句或挖空句。易混词可做干扰项，排除理由必须来自本题语境，不能写成“词库说它不对”。"
        )
    lines = [
        "你负责广东省考言语理解文字题。items每项一道，保留全局index。",
        json.dumps({"items": asks, "topic_definitions": cards, "already_kept": kept}, ensure_ascii=False),
        "目标是让学生练到指定知识点。目录定义限定考查范围，讲解卡的口诀只是参考，不要求复制其步骤或表达。",
        "easy/mid/hard只是命题倾向，auto自由安排。基础题也有训练价值，不为难度堆术语、空格或复杂干扰。",
        DIFFICULTY,
        rules_for(families),
        *extra,
        *([vocab_note] if vocab_note else []),
        *([corpus] if corpus else []),
        "文段、选词、文体、设问和正确解法自由设计；语境自然、信息完整，四项A/B/C/D中有唯一正确或唯一最佳项。",
        "按指定题型命题：填空须有空格，成语实词综合可以是成语、实词或混合，排序有句子和次序选项。不得把指定子点换成相邻考点。",
        "先完整代入选项，确认题文能支持择优。允许部分词都可用，只需整组选项能区分。不要为了证明标答而添设原文没有的前提。",
        "基础训练的干扰项可直接对应常见误读，含义差异清楚即可，不必四组都放近义表达。若两组只是“都通顺但一个更常见”，没有可见线索区分，就换一个干扰项；不要用搭配习惯或程度轻重的空泛断言强行定答案。",
        "analysis只保留足以决定选项的关键线索、答案依据和其他整组选项的主要差异，通常100至200字即可（不是字数硬限制）。某一空已能区分，就代入核对其他空，不再逐词排除。删除不影响作答的附带词义断言，不写词源、词素拆字或抽象/具体对象分类。",
        "按含义和上下文解释何者更贴切，不从中性词推出负面语境不可用，不把常见搭配当唯一合法搭配，不用机械拆字编造词义。",
        "无明确反驳的选项可说文段未支持，不把未提及写成事实错误。若题文不足以区分同等最佳项，应改题，而非在解析里强行排除。",
        "参考卡的易错提醒不是本题必须展示的词义规则：即使训练搭配或色彩，也只解释本题实际语义关系，不强行把其他自然表达说成搭配非法、色彩冲突或程度不够。",
        "同批题材和辨析关系有变化，不照搬参考卡例题、不靠换词换场景重复同题；优先自然常见语境，不全用抽象技术议论文。",
        "附有退回原因时解决具体问题；repair=analysis_only时保留原题干、选项与答案，只修解析并接受重审。若题目本身双解或标答无依据，返回unsuitable:true。",
        "kaodian_signal说明实际考查动作。解析直接给学生，不输出试错、改题草稿。遵守每个item的brief。",
        "近期题面与主题避让：recent_topics 里的主题指纹不要再写；"
        "family_counts 达到 3 次及以上的主题族必须换主题；"
        "do_not_reuse_molds 里的句式套路本组不要再用；"
        "recent_openings 只作开头参考："
        + json.dumps(run.get("yanyu_avoid") or {}, ensure_ascii=False),
        "只输出JSON：{\"questions\":[{\"index\":1,\"stem\":\"...\",\"kaodian_signal\":\"...\","
        "\"options\":[{\"key\":\"A\",\"text\":\"...\"},{\"key\":\"B\",\"text\":\"...\"},{\"key\":\"C\",\"text\":\"...\"},{\"key\":\"D\",\"text\":\"...\"}],"
        "\"answer\":\"A\",\"analysis\":\"...\"}]}。使用中文引号，确实不能满足范围时可返回unsuitable:true。",
    ]
    return "\n".join(lines)
