#!/usr/bin/env python3
"""Workflowy helper for Ivan's SDLC skills.

Reads WORKFLOWY_API_KEY from the environment or the nearest .env file.
All write commands are dry-run unless --apply is passed.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://workflowy.com/api/v1"
DEFAULT_MAX_NAME_WORDS = 15


def load_dotenv() -> None:
    for folder in [Path.cwd(), *Path.cwd().parents]:
        env_path = folder / ".env"
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        return


def api_key() -> str:
    load_dotenv()
    key = os.environ.get("WORKFLOWY_API_KEY", "").strip()
    if not key:
        raise SystemExit("WORKFLOWY_API_KEY is missing from the environment or repo .env")
    return key


def request_json(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None
    headers = {"Authorization": f"Bearer {api_key()}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Workflowy API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Workflowy API connection error: {exc.reason}") from exc
    return json.loads(body) if body else {}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    return re.sub(r"<[^>]+>", "", value).strip()


def node_short_id(node_id: str) -> str:
    return node_id.replace("-", "")[-12:]


def normalize_ref(value: str) -> str:
    value = value.strip()
    match = re.search(r"workflowy\.com/(?:#?/)?#?/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    match = re.search(r"#/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    return value


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def export_nodes() -> list[dict[str, Any]]:
    return request_json("GET", "/nodes-export").get("nodes", [])


def path_for(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    current: dict[str, Any] | None = node
    seen: set[str] = set()
    while current:
        node_id = current.get("id", "")
        if node_id in seen:
            break
        seen.add(node_id)
        parts.append(clean_text(current.get("name")) or node_id)
        parent_id = current.get("parent_id")
        current = by_id.get(parent_id) if parent_id else None
    return " > ".join(reversed(parts))


def cmd_targets(_: argparse.Namespace) -> None:
    print_json(request_json("GET", "/targets"))


def cmd_search(args: argparse.Namespace) -> None:
    query = args.query.lower()
    nodes = export_nodes()
    by_id = {node["id"]: node for node in nodes if "id" in node}
    matches = []
    for node in nodes:
        name = clean_text(node.get("name"))
        note = clean_text(node.get("note"))
        if query not in f"{name}\n{note}".lower():
            continue
        item: dict[str, Any] = {
            "id": node.get("id"),
            "short_id": node_short_id(node.get("id", "")),
            "name": name,
            "path": path_for(node, by_id),
            "completed": bool(node.get("completed") or node.get("completedAt")),
        }
        if args.include_notes and note:
            item["note_excerpt"] = note[:240]
        matches.append(item)
    print_json({"query": args.query, "match_count": len(matches), "matches": matches})


def get_children(parent_id: str) -> list[dict[str, Any]]:
    data = request_json("GET", "/nodes", params={"parent_id": parent_id})
    return sorted(data.get("nodes", []), key=lambda node: node.get("priority", 0))


def get_node(node_ref: str) -> dict[str, Any]:
    node_ref = normalize_ref(node_ref)
    quoted = urllib.parse.quote(node_ref, safe="")
    data = request_json("GET", f"/nodes/{quoted}")
    return data.get("node", data)


def cmd_children(args: argparse.Namespace) -> None:
    """Direct children with ids — the mapping source for docs folders and GitHub sync."""
    children = get_children(normalize_ref(args.node))
    print_json(
        {
            "parent": normalize_ref(args.node),
            "children": [
                {
                    "id": child.get("id"),
                    "short_id": node_short_id(child.get("id", "")),
                    "name": clean_text(child.get("name")),
                    "note": clean_text(child.get("note")),
                    "completed": bool(child.get("completed") or child.get("completedAt")),
                }
                for child in children
            ],
        }
    )


def render_outline(parent_ref: str, *, max_depth: int, include_root: bool) -> list[str]:
    lines: list[str] = []

    def walk(node_ref: str, depth: int) -> None:
        if depth > max_depth:
            return
        for child in get_children(node_ref):
            name = clean_text(child.get("name")) or child.get("id", "")
            lines.append(f"{'  ' * depth}- {name}")
            note = clean_text(child.get("note"))
            if note:
                lines.append(f"{'  ' * (depth + 1)}note: {note}")
            walk(child["id"], depth + 1)

    if include_root:
        root = get_node(parent_ref)
        root_name = clean_text(root.get("name")) or normalize_ref(parent_ref)
        lines.append(f"- {root_name}")
        note = clean_text(root.get("note"))
        if note:
            lines.append(f"  note: {note}")
        walk(root.get("id", normalize_ref(parent_ref)), 1)
    else:
        walk(normalize_ref(parent_ref), 0)
    return lines


def cmd_outline(args: argparse.Namespace) -> None:
    lines = render_outline(
        args.node,
        max_depth=args.max_depth,
        include_root=not args.children_only,
    )
    print("\n".join(lines))


def parse_outline(text: str) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        expanded = raw_line.replace("\t", "  ")
        indent = len(expanded) - len(expanded.lstrip(" "))
        level = indent // 2
        name = re.sub(r"^[-*]\s+", "", expanded.strip())

        if name.lower().startswith("note:"):
            note = name.split(":", 1)[1].strip()
            if not stack:
                raise ValueError("note line must follow an item")
            target = stack[-1][1]
            existing_note = target.get("note", "")
            target["note"] = f"{existing_note}\n{note}".strip() if existing_note else note
            continue

        node: dict[str, Any] = {"name": name, "note": "", "children": []}
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            roots.append(node)
        stack.append((level, node))
    return roots


def name_word_count(name: str) -> int:
    return len(re.findall(r"\b\S+\b", name))


def find_long_names(
    nodes: list[dict[str, Any]],
    *,
    max_words: int,
    path: str = "",
) -> list[dict[str, Any]]:
    violations = []
    for node in nodes:
        name = node["name"]
        node_path = f"{path} > {name}" if path else name
        words = name_word_count(name)
        if words > max_words:
            violations.append({"path": node_path, "words": words, "max_words": max_words})
        violations.extend(
            find_long_names(node["children"], max_words=max_words, path=node_path)
        )
    return violations


def create_tree(
    parent_id: str,
    nodes: list[dict[str, Any]],
    *,
    position: str,
) -> list[dict[str, str | None]]:
    created: list[dict[str, str | None]] = []
    for node in nodes:
        result = request_json(
            "POST",
            "/nodes",
            payload={
                "parent_id": parent_id,
                "name": node["name"],
                "position": position,
            },
        )
        child_id = result.get("item_id")
        created.append({"id": child_id, "name": node["name"]})
        if child_id and node.get("note"):
            request_json(
                "POST",
                f"/nodes/{urllib.parse.quote(child_id, safe='')}",
                payload={"note": node["note"]},
            )
        if child_id and node["children"]:
            created.extend(create_tree(child_id, node["children"], position=position))
    return created


def cmd_append_outline(args: argparse.Namespace) -> None:
    outline_path = Path(args.file)
    try:
        tree = parse_outline(outline_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    long_names = find_long_names(tree, max_words=args.max_name_words)
    if long_names and not args.allow_long_names:
        print_json({"dry_run": True, "error": "item names exceed word limit", "violations": long_names})
        raise SystemExit(2)

    if not args.apply:
        print_json(
            {
                "dry_run": True,
                "parent": args.parent,
                "max_name_words": args.max_name_words,
                "tree": tree,
            }
        )
        return
    created = create_tree(normalize_ref(args.parent), tree, position=args.position)
    print_json({"dry_run": False, "created": created})


def cmd_update_node(args: argparse.Namespace) -> None:
    payload: dict[str, str] = {}
    if args.name:
        words = name_word_count(args.name)
        if words > args.max_name_words and not args.allow_long_names:
            print_json(
                {
                    "dry_run": True,
                    "error": "item name exceeds word limit",
                    "violation": {
                        "name": args.name,
                        "words": words,
                        "max_words": args.max_name_words,
                    },
                }
            )
            raise SystemExit(2)
        payload["name"] = args.name
    if args.note_file:
        payload["note"] = Path(args.note_file).read_text(encoding="utf-8")
    elif args.note:
        payload["note"] = args.note
    if not payload:
        raise SystemExit("provide --name, --note, or --note-file")
    node_ref = normalize_ref(args.node)
    if not args.apply:
        print_json({"dry_run": True, "node": node_ref, "payload": payload})
        return
    result = request_json(
        "POST",
        f"/nodes/{urllib.parse.quote(node_ref, safe='')}",
        payload=payload,
    )
    print_json({"dry_run": False, "node": node_ref, "result": result})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workflowy API helper for Ivan")
    subparsers = parser.add_subparsers(dest="command", required=True)

    targets = subparsers.add_parser("targets", help="List Workflowy targets")
    targets.set_defaults(func=cmd_targets)

    search = subparsers.add_parser("search", help="Search exported nodes")
    search.add_argument("query")
    search.add_argument("--include-notes", action="store_true")
    search.set_defaults(func=cmd_search)

    children = subparsers.add_parser("children", help="List direct children with ids")
    children.add_argument("node")
    children.set_defaults(func=cmd_children)

    outline = subparsers.add_parser("outline", help="Render a node subtree")
    outline.add_argument("node")
    outline.add_argument("--children-only", action="store_true")
    outline.add_argument("--max-depth", type=int, default=8)
    outline.set_defaults(func=cmd_outline)

    append = subparsers.add_parser("append-outline", help="Append an outline")
    append.add_argument("parent")
    append.add_argument("--file", required=True)
    append.add_argument("--position", choices=["top", "bottom"], default="bottom")
    append.add_argument("--max-name-words", type=int, default=DEFAULT_MAX_NAME_WORDS)
    append.add_argument("--allow-long-names", action="store_true")
    append.add_argument("--apply", action="store_true", help="Write to Workflowy")
    append.set_defaults(func=cmd_append_outline)

    update = subparsers.add_parser("update-node", help="Update one node name or note")
    update.add_argument("node")
    update.add_argument("--name")
    update.add_argument("--note")
    update.add_argument("--note-file")
    update.add_argument("--max-name-words", type=int, default=DEFAULT_MAX_NAME_WORDS)
    update.add_argument("--allow-long-names", action="store_true")
    update.add_argument("--apply", action="store_true", help="Write to Workflowy")
    update.set_defaults(func=cmd_update_node)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
