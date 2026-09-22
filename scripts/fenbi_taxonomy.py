#!/usr/bin/env python3
"""粉笔广东·省市类行测树：单一数据源（src/knowledge/fenbiTree.json）。

标签格式：`模块-一级-二级`，可选 L4：`模块-一级-二级-子题型`。
二级名本身可以带连字符（如 组合排列-单题、时事政治-其他），解析必须按最长匹配，
不能对整串做 naive split('-')。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


FENBI_TREE_PATH = Path(__file__).resolve().parents[1] / "src" / "knowledge" / "fenbiTree.json"
FENBI_MODULE_NAMES = (
    "政治理论",
    "常识判断",
    "言语理解与表达",
    "数量关系",
    "判断推理",
)

@lru_cache(maxsize=1)
def load_fenbi_tree() -> dict:
    return json.loads(FENBI_TREE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def legacy_to_fenbi() -> dict[str, str]:
    """旧长标签 / 真题粗标 → 最近的粉笔 L3。画像靠 alias 对齐，不抹历史行。"""
    raw = load_fenbi_tree().get("legacyAliases") or {}
    return {str(key): str(value) for key, value in raw.items()}


# 兼容现有 import：单一数据源仍是 fenbiTree.json。
LEGACY_TO_FENBI = legacy_to_fenbi()


def fenbi_modules() -> list[dict]:
    return list(load_fenbi_tree().get("modules") or [])


def compose_tag(module: str, l2: str, l3: str, l4: str = "") -> str:
    tag = f"{module}-{l2}-{l3}"
    if l4:
        tag = f"{tag}-{l4}"
    return tag


@lru_cache(maxsize=1)
def fenbi_l3_tags() -> frozenset[str]:
    tags: set[str] = set()
    for mod in fenbi_modules():
        module = mod["name"]
        for group in mod.get("children") or []:
            l2 = group["name"]
            for leaf in group.get("children") or []:
                tags.add(compose_tag(module, l2, leaf["name"]))
    return frozenset(tags)


@lru_cache(maxsize=1)
def fenbi_l3_by_module() -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {}
    for tag in fenbi_l3_tags():
        parsed = parse_fenbi_tag(tag)
        if parsed:
            out.setdefault(parsed[0], set()).add(tag)
    return {key: frozenset(value) for key, value in out.items()}


@lru_cache(maxsize=1)
def _module_index() -> list[tuple[str, list[tuple[str, list[str]]]]]:
    """[(module, [(l2, [l3, ...])]), ...] 一级/二级按名字长短降序，供解析。"""
    indexed = []
    for mod in fenbi_modules():
        groups = []
        for group in mod.get("children") or []:
            leaves = [leaf["name"] for leaf in (group.get("children") or [])]
            leaves.sort(key=len, reverse=True)
            groups.append((group["name"], leaves))
        groups.sort(key=lambda item: len(item[0]), reverse=True)
        indexed.append((mod["name"], groups))
    indexed.sort(key=lambda item: len(item[0]), reverse=True)
    return indexed


def parse_fenbi_tag(tag: str) -> tuple[str, str, str, str] | None:
    """拆成 (模块, 一级, 二级, 子题型)。对不上粉笔树则返回 None。"""
    raw = (tag or "").strip()
    if not raw:
        return None
    for module, groups in _module_index():
        if raw != module and not raw.startswith(f"{module}-"):
            continue
        rest = "" if raw == module else raw[len(module) + 1 :]
        for l2, leaves in groups:
            if rest != l2 and not rest.startswith(f"{l2}-"):
                continue
            tail = "" if rest == l2 else rest[len(l2) + 1 :]
            for l3 in leaves:
                if tail == l3:
                    return module, l2, l3, ""
                if tail.startswith(f"{l3}-"):
                    return module, l2, l3, tail[len(l3) + 1 :]
            return None
        return None
    return None


def fenbi_l3_of(tag: str) -> str:
    parsed = parse_fenbi_tag(tag)
    if not parsed:
        return ""
    module, l2, l3, _l4 = parsed
    return compose_tag(module, l2, l3)


def is_fenbi_l3(tag: str) -> bool:
    parsed = parse_fenbi_tag(tag)
    return bool(parsed and not parsed[3])


def is_fenbi_l4(tag: str) -> bool:
    parsed = parse_fenbi_tag(tag)
    return bool(parsed and parsed[3])


def is_fenbi_primary(tag: str) -> bool:
    """L3 或挂在 L3 下的 L4，都可以当新一代主标签。"""
    return is_fenbi_l3(tag) or is_fenbi_l4(tag)


@lru_cache(maxsize=1)
def fenbi_leaf_lookup() -> tuple[tuple[str, str], ...]:
    """(叶子短名, L3 标签) 按短名长短降序。跳过过短/歧义名。"""
    skip = {"其他", "道德"}
    rows: list[tuple[str, str]] = []
    seen: dict[str, int] = {}
    for tag in fenbi_l3_tags():
        parsed = parse_fenbi_tag(tag)
        if not parsed:
            continue
        leaf = parsed[2]
        seen[leaf] = seen.get(leaf, 0) + 1
        rows.append((leaf, tag))
    unique = [(leaf, tag) for leaf, tag in rows if seen[leaf] == 1 and leaf not in skip and len(leaf) >= 3]
    unique.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(unique)


L2_DEFAULTS = {
    "片段阅读": "言语理解与表达-片段阅读-中心理解题",
    "语句表达": "言语理解与表达-语句表达-语句填空题",
    "逻辑填空": "言语理解与表达-逻辑填空-混搭填空",
    "数字推理": "数量关系-数字推理-数字推理-其他",
    "数学运算": "数量关系-数学运算-计算问题",
    "逻辑判断": "判断推理-逻辑判断-翻译推理",
    "图形推理": "判断推理-图形推理-位置规律",
    "科学推理": "判断推理-科学推理-科学推理-物理",
}


def lookup_fenbi_short(text: str) -> str:
    """从口语/短标签里捞最长的粉笔叶子名，或一级默认叶子。"""
    blob = text or ""
    if not blob:
        return ""
    exact = LEGACY_TO_FENBI.get(blob)
    if exact:
        return exact
    if is_fenbi_primary(blob):
        return blob
    for leaf, tag in fenbi_leaf_lookup():
        if leaf in blob:
            return tag
    for l2, tag in sorted(L2_DEFAULTS.items(), key=lambda item: len(item[0]), reverse=True):
        if l2 in blob:
            return tag
    return ""


def static_alias(tag: str) -> str:
    raw = (tag or "").strip()
    if raw in LEGACY_TO_FENBI:
        return LEGACY_TO_FENBI[raw]
    if is_fenbi_primary(raw):
        return raw
    return ""


def tags_for_canon_lookup(tag: str) -> list[str]:
    """生成器去 solver-canon 切片时，新路径和旧主标签都要能对上。"""
    raw = (tag or "").strip()
    found: list[str] = []
    seen: set[str] = set()

    def add(item: str) -> None:
        if item and item not in seen:
            seen.add(item)
            found.append(item)

    add(raw)
    mapped = static_alias(raw) or raw
    add(mapped)
    parent = fenbi_l3_of(mapped) or fenbi_l3_of(raw)
    parsed = parse_fenbi_tag(mapped) or parse_fenbi_tag(raw)
    # 叶子改过名时（分堆分配与定序消序 → 分堆分配与消序），只有别名表反查能对上旧主标签。
    # 它必须排在按 L3 兜底的候选前面，否则会切到同一 L3 下的另一张卡。
    for old, new in LEGACY_TO_FENBI.items():
        if new == mapped:
            add(old)
    if parsed and parsed[3]:
        # 别名表的值已经细化到四级，按 L3 归拢后再比，旧的四级写法才不会落空。
        for old, new in LEGACY_TO_FENBI.items():
            same_family = new == parent or fenbi_l3_of(new) == parent
            if same_family and (parsed[3] in old or old.endswith(parsed[3])):
                add(old)
    add(parent)
    for old, new in LEGACY_TO_FENBI.items():
        if new == mapped or new == parent or old == raw:
            add(old)
    return found


def kaodian_family(kaodian: str) -> str:
    """画像同族：粉笔 L3 自身；L4 跟父 L3。旧标签先映射再取族。"""
    raw = (kaodian or "").strip()
    mapped = static_alias(raw) or raw
    parsed = parse_fenbi_tag(mapped)
    if parsed:
        return compose_tag(parsed[0], parsed[1], parsed[2])
    parts = [part for part in mapped.split("-") if part]
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return mapped
