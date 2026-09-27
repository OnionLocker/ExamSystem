"""Resolve quiz scope from the same current content tree used by the webpage."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import subprocess

from fenbi_taxonomy import fenbi_modules, fenbi_l3_of, parse_fenbi_tag, LEGACY_TO_FENBI
from kaodian_taxonomy import (canonicalize, normalize_module, registered_knowledge_points,
                              database_aliases, resolve_database_alias)

ROOT = Path(__file__).resolve().parents[1]
FIGURES = re.compile(r"图形推理|科学推理|空间类|图形数阵")


def catalog(conn=None) -> dict[str, dict]:
    result = subprocess.run(["node", str(ROOT / "scripts/knowledge-content.mjs"), "catalog"],
                            cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
    documents = json.loads(result.stdout)["topics"]
    nodes = {}
    for module in fenbi_modules():
        name = module["name"]
        nodes[name] = {"tag": name, "title": name, "parentTag": None}
        for group in module["children"]:
            tag = name + "-" + group["name"]
            nodes[tag] = {"tag": tag, "title": group["name"], "parentTag": name}
    for doc in documents:
        for node in doc["nodes"]:
            nodes[node["tag"]] = {**node, "content_revision": doc["revision"], "content": True}

    aliases = database_aliases(conn)
    if conn is None:
        registered = registered_knowledge_points()
    else:
        rows = conn.execute("SELECT kaodian, COALESCE(definition, note, '') FROM kaodian_profile").fetchall()
        registered = {}
        for tag, definition in sorted(rows, key=lambda r: resolve_database_alias(r[0], aliases) != r[0]):
            registered.setdefault(resolve_database_alias(tag, aliases), {"definition": definition or ""})
    mapped_content = {}
    for node in nodes.values():
        for alias in node.get("aliases", []):
            mapped_content.setdefault(alias, []).append(node["tag"])
    for tag, point in registered.items():
        tag = resolve_database_alias(tag, aliases)
        tag = LEGACY_TO_FENBI.get(tag, tag)
        parent = fenbi_l3_of(tag)
        if not parent:
            continue
        if tag in nodes:
            # Stable content IDs store generation snapshots; current webpage content is authoritative.
            if "-@" not in tag and nodes[tag].get("content_revision") == 0 and point["definition"]:
                nodes[tag]["definition"] = point["definition"]
            continue
        mapped = mapped_content.get(tag, [])
        if len(mapped) == 1:
            node = nodes[mapped[0]]
            if node.get("content_revision") == 0 and point["definition"]:
                node["definition"] = point["definition"]
            continue
        # Content IDs that were removed cannot reappear via their profile row.
        if "-@" in tag:
            continue
        nodes[tag] = {"tag": tag, "title": parse_fenbi_tag(tag)[3], "parentTag": parent,
                      "definition": point["definition"], "registered": True}
    # Explicit profile merges retire the old content node from new allocations.
    for node in list(nodes.values()):
        for old in [node["tag"], *node.get("aliases", [])]:
            if old not in aliases or aliases[old] == old:
                continue
            target = resolve_database_alias(old, aliases)
            candidates = ([target] if target in nodes else mapped_content.get(target, []))
            if len(candidates) != 1 or candidates[0] == node["tag"]:
                continue
            destination = nodes[candidates[0]]
            if fenbi_l3_of(destination["tag"]) != fenbi_l3_of(node["tag"]):
                continue
            node["redirect"] = destination["tag"]
            node["archived"] = True
            destination.setdefault("aliases", []).extend([node["tag"], *node.get("aliases", [])])
            break
    return nodes


def _names(node):
    tag, title = node["tag"], node["title"]
    if node.get("referenceOnly"):
        return {tag}
    names = {tag, title, title.split(" · ")[0]}
    if title.endswith("问题") and len(title) > 3:
        names.add(title[:-2])
    if title in {"民法典", "刑法", "宪法"}:
        names.add(title.removesuffix("典"))
    names.update(node.get("aliases", []))
    parsed = parse_fenbi_tag(tag)
    if parsed:
        names.add(f"{parsed[2]}-{title}")
    for alias in node.get("aliases", []):
        parsed_alias = parse_fenbi_tag(alias)
        if parsed_alias and parsed_alias[3]:
            names.add(parsed_alias[3])
            names.add(f"{parsed_alias[2]}-{parsed_alias[3]}")
    return {n for n in names if n and not n.startswith("@")}


def _resolve(text, module, nodes, *, spoken=False):
    raw = str(text or "").strip()
    module = normalize_module(module) if module else ""
    eligible = {tag: node for tag, node in nodes.items()
                if not module or tag == module or tag.startswith(module + "-")}
    if spoken and "-" in raw:
        for name in sorted({m["name"] for m in fenbi_modules()}, key=len, reverse=True):
            found = re.search(re.escape(name) + r"-[\w\u4e00-\u9fff@（）·-]+", raw)
            if found:
                path = re.sub(r"(?:给我出|帮我出|出|来)(?:[一二两三四五六七八九十\d]+)(?:道题?|题)$", "", found.group())
                return _resolve(path, module, nodes)
    if raw in nodes:
        if raw not in eligible:
            raise ValueError(f"考点与模块不一致：{raw} / {module}")
        node = eligible[raw]
        return eligible.get(node.get("redirect"), node)
    if any(raw.startswith(m["name"] + "-") for m in fenbi_modules()):
        exact_aliases = [n for n in eligible.values() if raw in n.get("aliases", [])]
        exact_aliases = list({n.get("redirect", n["tag"]): eligible.get(n.get("redirect"), n)
                              for n in exact_aliases}.values())
        if len(exact_aliases) == 1:
            return exact_aliases[0]
        mapped = resolve_database_alias(raw)
        if mapped in eligible:
            return eligible[mapped]
        if not exact_aliases:
            raise ValueError(f"未知完整知识点路径，不能自动扩大到父级：{raw}")
    matches = []
    for node in eligible.values():
        for name in _names(node):
            if name == raw or (spoken and len(name) >= 2 and name in raw):
                explicit = {node["tag"], node["title"], *node.get("aliases", [])}
                for alias in node.get("aliases", []):
                    parsed_alias = parse_fenbi_tag(alias)
                    if parsed_alias and parsed_alias[3]:
                        explicit.add(parsed_alias[3])
                matches.append((len(name), name in explicit, node.get("redirect", node["tag"])))
    if not matches and not spoken:
        canonical = canonicalize(raw, module)
        if canonical != raw:
            return _resolve(canonical, module, nodes, spoken=True)
    if not matches:
        return None
    best = max((n, exact) for n, exact, _ in matches)
    tags = sorted({tag for n, exact, tag in matches if (n, exact) == best})
    # Mentioning both parent and its child is a precise child request.
    def ancestors(tag):
        result = set()
        parent = eligible[tag].get("parentTag")
        while parent in eligible and parent not in result:
            result.add(parent)
            parent = eligible[parent].get("parentTag")
        return result
    tags = [tag for tag in tags if not any(tag in ancestors(other) for other in tags if other != tag)]
    # A content alias and a registered label denote the same node only when explicit.
    if len(tags) != 1:
        raise ValueError(f"考点名称有歧义，请指定完整父级：{raw}；候选：{'、'.join(tags)}")
    node = eligible[tags[0]]
    return eligible.get(node.get("redirect"), node)


def resolve_scope_tag(text, module="") -> str:
    node = _resolve(text, module, catalog(), spoken=True)
    if node and node.get("archived"):
        raise ValueError(f"此知识点已停用：{node['title']}")
    return node["tag"] if node else ""


def scope_title(node, nodes) -> str:
    """Use the current catalog title, retaining the parent topic for a child."""
    parts = parse_fenbi_tag(node['tag'])
    if parts and parts[3]:
        parent = nodes.get(fenbi_l3_of(node['tag']), {})
        return f"{parent.get('title') or parts[2]}-{node['title']}"
    return node['title']


def source_topic(module: str, slots: list[dict]) -> str:
    """Name the requested scope, not whichever leaves received its quota."""
    scopes = list(dict.fromkeys(s.get('scope_title') for s in slots if s.get('scope_title')))
    if len(scopes) == 1 and all(s.get('scope_title') for s in slots):
        return scopes[0]
    unique = {str(s['tag']): s for s in slots}
    parsed = [parse_fenbi_tag(tag) for tag in unique]
    if len(unique) == 1 and len(scopes) <= 1:
        tag, slot = next(iter(unique.items()))
        parts = parsed[0]
        title = str(slot.get('display_title') or '').strip()
        if parts:
            parent_title = slot.get('topic_title') or parts[2]
            if parts[3]:
                if parts[3].startswith('@') and not title:
                    raise ValueError('动态考点缺少展示名称，不能用节点 ID 作为题组名')
                return f'{parent_title}-{title or parts[3]}'
            return title or parent_title
        return title or tag.split('-')[-1]
    if all(parsed):
        parents = list(dict.fromkeys(slot.get('topic_title') or parts[2]
                                    for slot, parts in zip(unique.values(), parsed)))
        if len(parents) == 1:
            return parents[0]
        families = list(dict.fromkeys(parts[1] for parts in parsed))
        if len(families) == 1:
            return families[0]
        return '、'.join(parents)
    return module


def source_name(module: str, slots: list[dict], date, difficulty=None) -> str:
    """Keep catalog names and label a single tier, mixed tiers, or unrestricted practice."""
    topic = source_topic(module, slots)
    topic = f'-{topic}' if topic != module else ''
    tiers = {slot.get('difficulty') or difficulty or 'mid' for slot in slots}
    level = {'easy': '简单', 'mid': '中等', 'hard': '困难'}.get(
        next(iter(tiers)) if len(tiers) == 1 else None, '综合')
    return f'广东省考行测-{module}{topic}-{level}-{date:%Y%m%d}'


def scope_slots(scope, count, module="", *, conn=None, nodes=None, all_leaves=False, allocation_offset=0) -> list[dict]:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 15:
        raise ValueError("专项配题数量须为 1–15")
    if isinstance(allocation_offset, bool) or not isinstance(allocation_offset, int) or allocation_offset < 0:
        raise ValueError("配额偏移须为非负整数")
    nodes = catalog(conn) if nodes is None else nodes
    root = _resolve(scope, module, nodes)
    if root is None:
        raise ValueError(f"没有匹配 '{scope}' 的知识点，请查看当前 catalog")
    if root.get("archived"):
        raise ValueError(f"此知识点已停用：{root['title']}")
    if FIGURES.search(root["tag"]):
        raise ValueError("图形、空间、科学推理请使用粉笔/已有外采真题")
    children = {}
    for node in nodes.values():
        children.setdefault(node.get("parentTag"), []).append(node)

    def leaves(node):
        if node.get("archived") or FIGURES.search(node["tag"]):
            return []
        subs = sorted(children.get(node["tag"], []), key=lambda n: (n.get("order", 0), n["tag"]))
        # A registered split supersedes an untouched generic card, not custom content.
        if any(n.get("registered") for n in subs):
            defaults = [n for n in subs if n.get("content")]
            if len(defaults) == 1 and defaults[0].get("content_revision") == 0:
                subs = [n for n in subs if n not in defaults]
        if subs:
            found = [leaf for sub in subs for leaf in leaves(sub)]
            if found:
                return found
            if not any(n.get("referenceOnly") and not n.get("archived")
                       and not children.get(n["tag"]) for n in subs):
                return []
        if node.get("referenceOnly"):
            return []
        # If all descendants were archived, don't silently fall back to the parent.
        if parse_fenbi_tag(node["tag"]):
            if fenbi_l3_of(node["tag"]) == node["tag"] and not node.get("definition"):
                return [{**node, "definition": f"本批只考{node['tag']}。按该考点的定义、设问动作与相邻考点边界出题，不因共用讲解参考卡而改考其他题型。"}]
            return [node]
        return []

    pool = leaves(root)
    if not pool and root.get("referenceOnly") and not children.get(root["tag"]):
        root = nodes[fenbi_l3_of(root["tag"])]
        pool = leaves(root)
    if not pool:
        raise ValueError(f"范围内没有可出题的有效子知识点：{root['title']}")
    if all_leaves:
        count = len(pool)
    else:
        offset = allocation_offset % len(pool)
        pool = pool[offset:] + pool[:offset]
        pool = pool[:count]
    base, extra = divmod(count, len(pool))
    slots = [{"tag": node["tag"], "count": base + (i < extra),
             "scope_tag": root["tag"], "scope_title": scope_title(root, nodes),
             "topic_title": nodes.get(fenbi_l3_of(node["tag"]), {}).get("title"),
             "display_title": node["title"],
             **({"definition": node["definition"]} if node.get("definition") else {}),
             **({"content_revision": node["content_revision"]} if node.get("content") else {})}
            for i, node in enumerate(pool)]
    for slot in slots:
        if not slot['tag'].startswith('数量关系-'):
            continue
        topic = fenbi_l3_of(slot['tag'])
        parents = {nodes[topic]['parentTag'], nodes[slot['tag']]['parentTag']}
        slot['sibling_topics'] = [
            {'tag': n['tag'], 'title': n['title']}
            for n in nodes.values()
            if n.get('parentTag') in parents and n['tag'] not in {topic, slot['tag']}
            and not n.get('archived') and not n.get('referenceOnly')
        ]
    return slots


def register_slots(slots, db):
    """Register selected stable content IDs before generation; never manufacture attempts."""
    from kaodian_profile import ensure_schema, register_knowledge_point
    points = {s["tag"]: s for s in slots if "-@" in s["tag"]}
    if not points:
        return
    with sqlite3.connect(db, timeout=30) as conn:
        ensure_schema(conn)
        for tag, slot in points.items():
            definition = slot.get("definition", "")
            if not definition:
                raise ValueError(f"子知识点缺少定义：{slot['display_title']}")
            # The full immutable definition stays in the batch, profile stores a bounded index.
            definition = definition[:4000]
            row = conn.execute("SELECT definition FROM kaodian_profile WHERE kaodian=?", (tag,)).fetchone()
            if not row or row[0] != definition:
                parsed = parse_fenbi_tag(tag)
                register_knowledge_point(conn, tag, parsed[0], parsed[1], definition)
