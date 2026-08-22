#!/usr/bin/env python3
"""Azure DevOps helper for Ivan's SDLC skills.

Owns every call that carries text: work items, discussion comments, pull request
bodies, and the CI wait. All write commands are dry-run unless --apply is passed.
Nothing here ever deletes.

Auth, first hit wins:
  1. AZURE_DEVOPS_PAT      (env or repo .env)  -> Basic
  2. AZURE_DEVOPS_EXT_PAT  (the var `az devops` honours) -> Basic
  3. SYSTEM_ACCESSTOKEN    (inside an Azure Pipelines run) -> Bearer
  4. `az account get-access-token` for the Azure DevOps resource -> Bearer

Org / project, first hit wins:
  --org / --project  ->  AZURE_DEVOPS_ORG_URL / AZURE_DEVOPS_PROJECT (env or .env)
  ->  ~/.azure/azuredevops/config [defaults]
"""

from __future__ import annotations

import argparse
import base64
import configparser
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_VERSION = "7.1"
COMMENTS_API_VERSION = "7.1-preview.4"
# Azure DevOps' fixed AAD application id, used to mint a bearer token via `az`.
ADO_RESOURCE_ID = "499b84ac-1321-427f-aa17-267ca6975798"
MAX_IDS_PER_BATCH = 200
# `pr-wait` exit codes. The caller (/implement step 7) branches on these to decide
# what it can fix itself and what genuinely needs a human, so every outcome gets
# its own code instead of one undifferentiated failure.
PR_WAIT_MERGED = 0
PR_WAIT_ERROR = 1            # unexpected — treat as a real failure
PR_WAIT_POLICY_FAILED = 2    # a blocking machine policy (the build) rejected: fixable on the branch
PR_WAIT_CONFLICTS = 3        # the source branch no longer merges cleanly: rebase and re-push
PR_WAIT_NEEDS_HUMAN = 4      # only human-gated policies remain, or nothing will complete the PR
PR_WAIT_ABANDONED = 5        # someone abandoned the PR
PR_WAIT_TIMEOUT = 6          # still progressing at the deadline — not a failed cycle
# Policy types no amount of Ivan retrying can satisfy — they need a person.
HUMAN_GATED_POLICIES = {
    "Minimum number of reviewers",
    "Required reviewers",
    "Comment requirements",
}
POLICY_CHECK_HUMAN_GATED = 4   # `policy-check`: a blocking policy on the branch needs a person
BUILD_TRIAGE_QUALITY = 0       # the build failed on our code — fix it
BUILD_TRIAGE_INFRA = 7         # the build failed on the infrastructure — re-queue it
# Failure text that means the agent/network/feed let go, not that the code is wrong.
# Matched case-insensitively against a failed timeline record's issues.
INFRA_FAILURE_SIGNS = (
    "the agent request was aborted",
    "lost communication with the server",
    "the agent did not respond",
    "no hosted parallelism has been purchased",
    "we stopped hearing from agent",
    "unable to load the service index for source",
    "retrying 'findpackagesbyidasync",
    "the http request to the remote webproxy",
    "connection reset by peer",
    "econnreset",
    "etimedout",
    "socket timeout",
    "server error returned: 502",
    "server error returned: 503",
    "service unavailable",
    "bad gateway",
    "no space left on device",
    "there is not enough space on the disk",
    "the operation was canceled",
    "timeout waiting for the pipeline agent",
    "could not resolve host",
    "temporary failure in name resolution",
)
DESCRIPTION_FIELD = "System.Description"
SUMMARY_FIELDS = [
    "System.Id",
    "System.WorkItemType",
    "System.Title",
    "System.State",
    "System.Tags",
    "System.AreaPath",
    "System.Parent",
]


# ---------------------------------------------------------------- environment


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


def az_devops_defaults() -> dict[str, str]:
    config_path = Path.home() / ".azure" / "azuredevops" / "config"
    if not config_path.exists():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except configparser.Error:
        return {}
    if not parser.has_section("defaults"):
        return {}
    return {k: v.strip() for k, v in parser.items("defaults") if v.strip()}


def auth_header() -> str:
    load_dotenv()
    for var in ("AZURE_DEVOPS_PAT", "AZURE_DEVOPS_EXT_PAT"):
        pat = os.environ.get(var, "").strip()
        if pat:
            token = base64.b64encode(f":{pat}".encode()).decode()
            return f"Basic {token}"
    pipeline_token = os.environ.get("SYSTEM_ACCESSTOKEN", "").strip()
    if pipeline_token:
        return f"Bearer {pipeline_token}"
    try:
        token = subprocess.run(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                ADO_RESOURCE_ID,
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            shell=(os.name == "nt"),
        )
    except (OSError, subprocess.SubprocessError):
        token = None
    if token is not None and token.returncode == 0 and token.stdout.strip():
        return f"Bearer {token.stdout.strip()}"
    raise SystemExit(
        "No Azure DevOps credential. Put AZURE_DEVOPS_PAT=<pat> in the repo .env "
        "(gitignored), or run `az login`. Create a PAT at "
        "https://dev.azure.com/<org>/_usersSettings/tokens with Work Items (Read & write), "
        "Code (Read & write), Build (Read & execute)."
    )


_CONTEXT: dict[str, str] = {}


def set_context(args: argparse.Namespace) -> None:
    load_dotenv()
    defaults = az_devops_defaults()
    org = (
        getattr(args, "org", None)
        or os.environ.get("AZURE_DEVOPS_ORG_URL", "").strip()
        or defaults.get("organization", "")
    )
    project = (
        getattr(args, "project", None)
        or os.environ.get("AZURE_DEVOPS_PROJECT", "").strip()
        or defaults.get("project", "")
    )
    if not org:
        raise SystemExit(
            "No organization. Pass --org https://dev.azure.com/<org>, set "
            "AZURE_DEVOPS_ORG_URL, or run `az devops configure -d organization=<url>`."
        )
    if not project:
        raise SystemExit(
            "No project. Pass --project <name>, set AZURE_DEVOPS_PROJECT, or run "
            "`az devops configure -d project=<name>`."
        )
    _CONTEXT["org"] = org.rstrip("/")
    _CONTEXT["project"] = project


def org() -> str:
    return _CONTEXT["org"]


def project() -> str:
    return _CONTEXT["project"]


# ------------------------------------------------------------------- requests


def request_json(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    content_type: str = "application/json",
    api_version: str = API_VERSION,
) -> Any:
    url = f"{org()}/{path.lstrip('/')}"
    query = dict(params or {})
    query["api-version"] = api_version
    url = f"{url}?{urllib.parse.urlencode(query)}"
    data = None
    headers = {"Authorization": auth_header(), "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = content_type
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except (ValueError, AttributeError):
            pass
        raise ApiError(exc.code, detail) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Azure DevOps connection error: {exc.reason}") from exc
    if not body:
        return {}
    if body.lstrip().startswith("<"):
        raise SystemExit(
            "Azure DevOps returned HTML instead of JSON - the credential is most likely "
            "invalid or expired."
        )
    return json.loads(body)


class ApiError(SystemExit):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"Azure DevOps API error {status}: {message}")


def project_path(path: str) -> str:
    return f"{urllib.parse.quote(project())}/{path.lstrip('/')}"


# -------------------------------------------------------------------- helpers


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def read_text_file(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit(f"{path} is empty")
    return text


def field_text(item: dict[str, Any], field: str) -> str:
    """Return a large-text field as text, honouring its stored format.

    A work item reports its per-field format in `multilineFieldsFormat`
    (e.g. {"System.Description": "markdown"}). Markdown fields are already
    plain text; HTML fields need flattening.
    """
    value = item.get("fields", {}).get(field)
    formats = item.get("multilineFieldsFormat") or {}
    if str(formats.get(field, "")).lower() == "markdown":
        # Azure DevOps stores `"` and `&` as entities even in Markdown fields.
        return html.unescape(value or "")
    return html_to_text(value)


def html_to_text(value: str | None) -> str:
    """Best-effort rendering of a legacy HTML large-text field."""
    if not value:
        return ""
    if "<" not in value:
        return html.unescape(value)
    text = re.sub(r"<\s*br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</\s*(p|div|h[1-6])\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<\s*li\s*>", "- ", text, flags=re.I)
    text = re.sub(r"</\s*li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def tags_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [t.strip() for t in value.split(";") if t.strip()]


def work_item_url(item_id: int | str) -> str:
    return f"{org()}/_apis/wit/workItems/{item_id}"


def web_url(item_id: int | str) -> str:
    return f"{org()}/{urllib.parse.quote(project())}/_workitems/edit/{item_id}"


def confirm_or_dry_run(args: argparse.Namespace, description: str, document: Any) -> bool:
    """Print what would happen. Returns True when the caller should actually write."""
    if getattr(args, "apply", False):
        return True
    print(f"DRY RUN - {description}")
    print_json(document)
    print("\nRe-run with --apply to perform this write.")
    return False


# ------------------------------------------------------------- read commands


def cmd_whoami(args: argparse.Namespace) -> None:
    data = request_json("GET", "_apis/connectionData", api_version="7.1-preview.1")
    user = data.get("authenticatedUser", {})
    info = {
        "organization": org(),
        "project": project(),
        "user": user.get("providerDisplayName") or user.get("customDisplayName"),
        "userId": user.get("id"),
    }
    try:
        proj = request_json(
            "GET",
            f"_apis/projects/{urllib.parse.quote(project())}",
            params={"includeCapabilities": "true"},
        )
        info["projectId"] = proj.get("id")
        info["process"] = (
            proj.get("capabilities", {}).get("processTemplate", {}).get("templateName")
        )
    except ApiError as exc:
        info["projectError"] = exc.message
    if args.json:
        print_json(info)
        return
    for key, value in info.items():
        print(f"{key}: {value}")


def cmd_project_info(args: argparse.Namespace) -> None:
    """Everything /adopt needs to write the Ivan project config, in one call set."""
    proj = request_json(
        "GET",
        f"_apis/projects/{urllib.parse.quote(project())}",
        params={"includeCapabilities": "true"},
    )
    types = request_json("GET", project_path("_apis/wit/workitemtypes"))
    type_names = [t["name"] for t in types.get("value", [])]
    result: dict[str, Any] = {
        "project": proj.get("name"),
        "projectId": proj.get("id"),
        "process": proj.get("capabilities", {}).get("processTemplate", {}).get("templateName"),
        "workItemTypes": type_names,
        "states": {},
    }
    for type_name in args.type or ["Epic", "Feature"]:
        if type_name not in type_names:
            result["states"][type_name] = {"error": "type not present in this process"}
            continue
        states = request_json(
            "GET",
            project_path(f"_apis/wit/workitemtypes/{urllib.parse.quote(type_name)}/states"),
        )
        result["states"][type_name] = [
            {"name": s["name"], "category": s.get("category")} for s in states.get("value", [])
        ]
    repos = request_json("GET", project_path("_apis/git/repositories"))
    result["repositories"] = [
        {"name": r["name"], "id": r["id"], "defaultBranch": r.get("defaultBranch")}
        for r in repos.get("value", [])
    ]
    if args.json:
        print_json(result)
        return
    print(f"project      : {result['project']} ({result['projectId']})")
    print(f"process      : {result['process']}")
    print(f"repositories : {', '.join(r['name'] for r in result['repositories']) or '(none)'}")
    for type_name, states in result["states"].items():
        if isinstance(states, dict):
            print(f"{type_name:<13}: {states['error']}")
            continue
        rendered = ", ".join(f"{s['name']} [{s['category']}]" for s in states)
        print(f"{type_name:<13}: {rendered}")


def fetch_fields(ids: list[int], fields: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for start in range(0, len(ids), MAX_IDS_PER_BATCH):
        chunk = ids[start : start + MAX_IDS_PER_BATCH]
        data = request_json(
            "GET",
            project_path("_apis/wit/workitems"),
            params={
                "ids": ",".join(str(i) for i in chunk),
                "fields": ",".join(fields),
                "$errorPolicy": "omit",
            },
        )
        items.extend(data.get("value", []))
    return items


def run_wiql(query: str) -> list[int]:
    data = request_json(
        "POST", project_path("_apis/wit/wiql"), payload={"query": query}
    )
    return [w["id"] for w in data.get("workItems", [])]


# A Feature is only auto-buildable once /kickoff has settled it and tagged it
# `ready`. /discover's stubs carry `ivan` but not `ready`, which is what stops
# /autopilot building a one-line placeholder.
PRESETS = {
    "open-features": (
        "SELECT [System.Id] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        "AND [System.WorkItemType] = '{type}' "
        "{area}"
        "AND [System.State] NOT IN ('Closed', 'Removed', 'Done', 'Resolved') "
        "AND [System.Tags] CONTAINS 'ready' "
        "AND NOT [System.Tags] CONTAINS 'follow-up' "
        "ORDER BY [System.Id]"
    ),
    "stub-features": (
        "SELECT [System.Id] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        "AND [System.WorkItemType] = '{type}' "
        "{area}"
        "AND [System.State] NOT IN ('Closed', 'Removed', 'Done', 'Resolved') "
        "AND NOT [System.Tags] CONTAINS 'ready' "
        "AND NOT [System.Tags] CONTAINS 'follow-up' "
        "ORDER BY [System.Id]"
    ),
    "all-features": (
        "SELECT [System.Id] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        "AND [System.WorkItemType] = '{type}' "
        "{area}"
        "ORDER BY [System.Id]"
    ),
    "follow-ups": (
        "SELECT [System.Id] FROM WorkItems "
        "WHERE [System.TeamProject] = @project "
        "{area}"
        "AND [System.Tags] CONTAINS 'follow-up' "
        "AND [System.State] NOT IN ('Closed', 'Removed', 'Done') "
        "ORDER BY [System.Id]"
    ),
}


def build_query(args: argparse.Namespace) -> str:
    if args.wiql_file:
        return read_text_file(args.wiql_file)
    if args.wiql:
        return args.wiql
    template = PRESETS[args.preset]
    area = ""
    if args.area:
        area = f"AND [System.AreaPath] UNDER '{args.area}' "
    return template.format(type=args.type, area=area)


def render_rows(items: list[dict[str, Any]]) -> None:
    if not items:
        print("(no work items)")
        return
    for item in items:
        fields = item.get("fields", {})
        tags = tags_to_list(fields.get("System.Tags"))
        line = (
            f"#{fields.get('System.Id', item.get('id'))} "
            f"[{fields.get('System.WorkItemType', '?')}] "
            f"{fields.get('System.State', '?'):<10} "
            f"{fields.get('System.Title', '')}"
        )
        if tags:
            line += f"  ({', '.join(tags)})"
        print(line)


def cmd_query(args: argparse.Namespace) -> None:
    query = build_query(args)
    ids = run_wiql(query)
    if not ids:
        if args.json:
            print_json([])
        else:
            print("(no work items)")
        return
    items = fetch_fields(ids, SUMMARY_FIELDS)
    order = {item_id: i for i, item_id in enumerate(ids)}
    items.sort(key=lambda it: order.get(it.get("id", 0), 0))
    if args.json:
        print_json(
            [
                {
                    "id": it.get("id"),
                    "type": it["fields"].get("System.WorkItemType"),
                    "title": it["fields"].get("System.Title"),
                    "state": it["fields"].get("System.State"),
                    "tags": tags_to_list(it["fields"].get("System.Tags")),
                    "areaPath": it["fields"].get("System.AreaPath"),
                    "parent": it["fields"].get("System.Parent"),
                }
                for it in items
            ]
        )
        return
    render_rows(items)


def get_work_item(item_id: int, *, expand: str = "all") -> dict[str, Any]:
    return request_json(
        "GET", project_path(f"_apis/wit/workitems/{item_id}"), params={"$expand": expand}
    )


def get_comments(item_id: int) -> list[dict[str, Any]]:
    data = request_json(
        "GET",
        project_path(f"_apis/wit/workItems/{item_id}/comments"),
        api_version=COMMENTS_API_VERSION,
    )
    return data.get("comments", [])


def cmd_show(args: argparse.Namespace) -> None:
    item = get_work_item(args.id)
    fields = item.get("fields", {})
    comments = get_comments(args.id) if args.comments else []
    if args.json:
        payload = {"workItem": item}
        if args.comments:
            payload["comments"] = comments
        print_json(payload)
        return
    print(f"#{item['id']} [{fields.get('System.WorkItemType')}] {fields.get('System.Title')}")
    print(f"state    : {fields.get('System.State')}")
    print(f"area     : {fields.get('System.AreaPath')}")
    print(f"tags     : {', '.join(tags_to_list(fields.get('System.Tags'))) or '(none)'}")
    print(f"parent   : {fields.get('System.Parent') or '(none)'}")
    print(f"url      : {web_url(item['id'])}")
    print("\n--- description ---")
    print(field_text(item, DESCRIPTION_FIELD) or "(empty)")
    if args.comments:
        print(f"\n--- comments ({len(comments)}) ---")
        for comment in comments:
            who = comment.get("createdBy", {}).get("displayName", "?")
            when = comment.get("createdDate", "")[:19].replace("T", " ")
            print(f"\n[{when}] {who}:")
            print(html_to_text(comment.get("text")))


def cmd_children(args: argparse.Namespace) -> None:
    ids = run_wiql(
        "SELECT [System.Id] FROM WorkItems "
        f"WHERE [System.TeamProject] = @project AND [System.Parent] = {args.id} "
        "ORDER BY [System.Id]"
    )
    if not ids:
        print("(no children)" if not args.json else "[]")
        return
    items = fetch_fields(ids, SUMMARY_FIELDS)
    if args.json:
        print_json(items)
        return
    render_rows(items)


# ------------------------------------------------------------ write commands


def description_ops(text: str) -> list[dict[str, Any]]:
    """Set the description AND pin the field to Markdown.

    Without the second op Azure DevOps stores large text fields as HTML and the
    Markdown source renders as literal text. `az boards work-item` cannot do this.
    """
    return [
        {"op": "add", "path": f"/fields/{DESCRIPTION_FIELD}", "value": text},
        {"op": "add", "path": f"/multilineFieldsFormat/{DESCRIPTION_FIELD}", "value": "Markdown"},
    ]


def cmd_create(args: argparse.Namespace) -> None:
    ops: list[dict[str, Any]] = [
        {"op": "add", "path": "/fields/System.Title", "value": args.title}
    ]
    if args.description_file:
        ops.extend(description_ops(read_text_file(args.description_file)))
    if args.area:
        ops.append({"op": "add", "path": "/fields/System.AreaPath", "value": args.area})
    if args.iteration:
        ops.append({"op": "add", "path": "/fields/System.IterationPath", "value": args.iteration})
    if args.tag:
        ops.append({"op": "add", "path": "/fields/System.Tags", "value": "; ".join(args.tag)})
    if args.state:
        ops.append({"op": "add", "path": "/fields/System.State", "value": args.state})
    if args.parent:
        ops.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": work_item_url(args.parent),
                },
            }
        )
    if not confirm_or_dry_run(args, f"create {args.type} '{args.title}'", ops):
        return
    item = request_json(
        "POST",
        project_path(f"_apis/wit/workitems/${urllib.parse.quote(args.type)}"),
        payload=ops,
        content_type="application/json-patch+json",
    )
    print(f"Created #{item['id']}: {item['fields'].get('System.Title')}")
    print(web_url(item["id"]))
    if args.json:
        print_json(item)


def cmd_update(args: argparse.Namespace) -> None:
    ops: list[dict[str, Any]] = []
    if args.title:
        ops.append({"op": "add", "path": "/fields/System.Title", "value": args.title})
    if args.description_file:
        ops.extend(description_ops(read_text_file(args.description_file)))
    if args.state:
        ops.append({"op": "add", "path": "/fields/System.State", "value": args.state})
    if args.area:
        ops.append({"op": "add", "path": "/fields/System.AreaPath", "value": args.area})
    if args.iteration:
        ops.append({"op": "add", "path": "/fields/System.IterationPath", "value": args.iteration})
    if args.add_tag or args.remove_tag:
        current = tags_to_list(
            get_work_item(args.id, expand="none").get("fields", {}).get("System.Tags")
        )
        lowered = {t.lower() for t in current}
        for tag in args.add_tag or []:
            if tag.lower() not in lowered:
                current.append(tag)
                lowered.add(tag.lower())
        removals = {t.lower() for t in (args.remove_tag or [])}
        current = [t for t in current if t.lower() not in removals]
        ops.append({"op": "add", "path": "/fields/System.Tags", "value": "; ".join(current)})
    if args.parent:
        ops.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": work_item_url(args.parent),
                },
            }
        )
    if not ops:
        raise SystemExit("Nothing to update - pass at least one field flag.")
    if not confirm_or_dry_run(args, f"update work item #{args.id}", ops):
        return
    item = request_json(
        "PATCH",
        project_path(f"_apis/wit/workitems/{args.id}"),
        payload=ops,
        content_type="application/json-patch+json",
    )
    fields = item.get("fields", {})
    print(f"Updated #{item['id']}: {fields.get('System.Title')} [{fields.get('System.State')}]")
    print(web_url(item["id"]))


def cmd_comment(args: argparse.Namespace) -> None:
    text = read_text_file(args.file) if args.file else args.text
    if not text:
        raise SystemExit("Pass --file <path> or --text <string>.")
    payload = {"text": text, "format": "markdown"}
    if not confirm_or_dry_run(args, f"comment on work item #{args.id}", payload):
        return
    try:
        request_json(
            "POST",
            project_path(f"_apis/wit/workItems/{args.id}/comments"),
            payload=payload,
            api_version=COMMENTS_API_VERSION,
        )
    except ApiError as exc:
        if exc.status != 400:
            raise
        # Older collections reject the `format` field; fall back to a plain comment.
        request_json(
            "POST",
            project_path(f"_apis/wit/workItems/{args.id}/comments"),
            payload={"text": text},
            api_version=COMMENTS_API_VERSION,
        )
    print(f"Commented on #{args.id}.")


def cmd_area(args: argparse.Namespace) -> None:
    if args.action == "list":
        data = request_json(
            "GET",
            project_path("_apis/wit/classificationnodes/areas"),
            params={"$depth": "2"},
        )
        if args.json:
            print_json(data)
            return

        def walk(node: dict[str, Any], indent: int = 0) -> None:
            print("  " * indent + node.get("name", "?"))
            for child in node.get("children", []) or []:
                walk(child, indent + 1)

        walk(data)
        return
    # ensure
    name = args.name
    try:
        request_json(
            "GET",
            project_path(f"_apis/wit/classificationnodes/areas/{urllib.parse.quote(name)}"),
        )
        print(f"Area path already exists: {project()}\\{name}")
        return
    except ApiError as exc:
        if exc.status != 404:
            raise
    payload = {"name": name}
    if not confirm_or_dry_run(args, f"create area path {project()}\\{name}", payload):
        return
    request_json("POST", project_path("_apis/wit/classificationnodes/areas"), payload=payload)
    print(f"Created area path: {project()}\\{name}")


# ------------------------------------------------------------- pull requests


def repo_id(repo: str) -> str:
    data = request_json(
        "GET", project_path(f"_apis/git/repositories/{urllib.parse.quote(repo)}")
    )
    return data["id"]


def project_id() -> str:
    data = request_json("GET", f"_apis/projects/{urllib.parse.quote(project())}")
    return data["id"]


def authenticated_user_id() -> str:
    data = request_json("GET", "_apis/connectionData", api_version="7.1-preview.1")
    return data["authenticatedUser"]["id"]


def ref(branch: str) -> str:
    return branch if branch.startswith("refs/") else f"refs/heads/{branch}"


def cmd_pr_create(args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "sourceRefName": ref(args.source),
        "targetRefName": ref(args.target),
        "title": args.title,
        "description": read_text_file(args.description_file) if args.description_file else "",
    }
    if args.work_item:
        payload["workItemRefs"] = [{"id": str(w)} for w in args.work_item]
    if args.draft:
        payload["isDraft"] = True
    if not confirm_or_dry_run(args, f"create PR {args.source} -> {args.target}", payload):
        return
    pr = request_json(
        "POST",
        project_path(f"_apis/git/repositories/{urllib.parse.quote(args.repo)}/pullrequests"),
        payload=payload,
    )
    pr_id = pr["pullRequestId"]
    print(f"Created PR !{pr_id}: {pr['title']}")
    if args.squash or args.delete_source_branch or args.auto_complete:
        patch: dict[str, Any] = {
            "completionOptions": {
                "mergeStrategy": "squash" if args.squash else "noFastForward",
                "deleteSourceBranch": bool(args.delete_source_branch),
                "transitionWorkItems": False,
            }
        }
        if args.auto_complete:
            patch["autoCompleteSetBy"] = {"id": authenticated_user_id()}
        request_json(
            "PATCH",
            project_path(
                f"_apis/git/repositories/{urllib.parse.quote(args.repo)}/pullrequests/{pr_id}"
            ),
            payload=patch,
        )
        print(
            "Set completion options: "
            f"squash={bool(args.squash)}, deleteSourceBranch={bool(args.delete_source_branch)}, "
            f"autoComplete={bool(args.auto_complete)}"
        )
    print(f"{org()}/{urllib.parse.quote(project())}/_git/{urllib.parse.quote(args.repo)}/pullrequest/{pr_id}")
    if args.json:
        print_json(pr)


def cmd_pr_link(args: argparse.Namespace) -> None:
    """Attach a PR to a work item as an ArtifactLink (what `Closes #N` did on GitHub)."""
    artifact = (
        f"vstfs:///Git/PullRequestId/{project_id()}%2F{repo_id(args.repo)}%2F{args.pr}"
    )
    ops = [
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "ArtifactLink",
                "url": artifact,
                "attributes": {"name": "Pull Request"},
            },
        }
    ]
    if not confirm_or_dry_run(args, f"link PR !{args.pr} to work item #{args.id}", ops):
        return
    request_json(
        "PATCH",
        project_path(f"_apis/wit/workitems/{args.id}"),
        payload=ops,
        content_type="application/json-patch+json",
    )
    print(f"Linked PR !{args.pr} to #{args.id}.")


def pr_state(repo: str, pr_id: int) -> dict[str, Any]:
    return request_json(
        "GET",
        project_path(f"_apis/git/repositories/{urllib.parse.quote(repo)}/pullrequests/{pr_id}"),
    )


def pr_policies(pr_id: int) -> list[dict[str, Any]]:
    artifact = f"vstfs:///CodeReview/CodeReviewId/{project_id()}/{pr_id}"
    data = request_json(
        "GET",
        project_path("_apis/policy/evaluations"),
        params={"artifactId": artifact},
        api_version="7.1-preview.1",
    )
    return data.get("value", [])


def policy_name(policy: dict[str, Any]) -> str:
    return (
        policy.get("configuration", {})
        .get("type", {})
        .get("displayName", "policy")
    )


def blocking(policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in policies if p.get("configuration", {}).get("isBlocking")]


def fail(code: int, message: str) -> None:
    """Exit with a classified code. SystemExit(str) would always be 1."""
    print(message, file=sys.stderr)
    sys.exit(code)


def cmd_pr_wait(args: argparse.Namespace) -> None:
    """The blocking wait `gh pr checks --watch` gave us; Azure DevOps has no equivalent.

    Exits with a PR_WAIT_* code saying *why* it stopped, because the caller's next
    move is completely different for a red build, a conflicted branch, and a PR
    parked behind a human approver.
    """
    deadline = time.time() + args.timeout
    interval = args.interval
    last_summary = ""
    while True:
        pr = pr_state(args.repo, args.pr)
        status = pr.get("status")
        merge_status = pr.get("mergeStatus")
        policies = pr_policies(args.pr)
        summary = ", ".join(
            f"{policy_name(p)}={p.get('status')}" for p in policies
        ) or "(no policies configured)"
        if summary != last_summary:
            print(f"[{time.strftime('%H:%M:%S')}] status={status} merge={merge_status} {summary}")
            last_summary = summary

        if status == "completed":
            print(
                f"PR !{args.pr} completed. "
                f"Merge commit: {pr.get('lastMergeCommit', {}).get('commitId')}"
            )
            return
        if status == "abandoned":
            fail(PR_WAIT_ABANDONED, f"PR !{args.pr} was abandoned.")

        # Conflicts first: a conflicted PR shows no rejected policy and will never
        # auto-complete, so without this check it silently burns the whole timeout.
        if merge_status == "conflicts":
            fail(
                PR_WAIT_CONFLICTS,
                f"PR !{args.pr} has merge conflicts with {pr.get('targetRefName', 'the target')}. "
                f"Rebase the source branch onto the target, re-run the gate, and force-push.",
            )
        if merge_status == "failure":
            fail(PR_WAIT_ERROR, f"PR !{args.pr} failed to produce a merge commit (server-side).")

        rejected = [p for p in blocking(policies) if p.get("status") in ("rejected", "broken")]
        if rejected:
            names = ", ".join(policy_name(p) for p in rejected)
            human = [p for p in rejected if policy_name(p) in HUMAN_GATED_POLICIES]
            code = PR_WAIT_NEEDS_HUMAN if human else PR_WAIT_POLICY_FAILED
            fail(code, f"Blocking policy failed on PR !{args.pr}: {names}")

        # Everything a machine can satisfy is green, and the PR still isn't merging.
        # Waiting longer cannot change that, so say so now instead of at the deadline.
        outstanding = [p for p in blocking(policies) if p.get("status") != "approved"]
        if outstanding and all(policy_name(p) in HUMAN_GATED_POLICIES for p in outstanding):
            names = ", ".join(policy_name(p) for p in outstanding)
            fail(
                PR_WAIT_NEEDS_HUMAN,
                f"PR !{args.pr} is green on every automated policy and is waiting on a person: "
                f"{names}. Ivan cannot satisfy this — a human must act on the PR.",
            )
        if not outstanding and not pr.get("autoCompleteSetBy"):
            fail(
                PR_WAIT_NEEDS_HUMAN,
                f"PR !{args.pr} passes every blocking policy but has no auto-complete set, "
                f"so nothing will merge it. Re-create it with --auto-complete.",
            )

        if time.time() >= deadline:
            fail(
                PR_WAIT_TIMEOUT,
                f"Timed out after {args.timeout}s waiting on PR !{args.pr} "
                f"(status={status}, merge={merge_status}, {summary}). Still in progress — "
                f"this is not a failed build.",
            )
        time.sleep(interval)
        interval = min(interval * 1.5, args.max_interval)


def branch_policies(repo: str, branch: str) -> list[dict[str, Any]]:
    """Policy configurations that apply to `branch` in `repo` (exact-match scopes)."""
    data = request_json("GET", project_path("_apis/policy/configurations"))
    wanted_ref = ref(branch)
    rid = repo_id(repo)
    applies = []
    for cfg in data.get("value", []):
        if not cfg.get("isEnabled"):
            continue
        for scope in cfg.get("settings", {}).get("scope", []):
            same_repo = scope.get("repositoryId") in (None, rid)
            match_kind = scope.get("matchKind", "Exact").lower()
            scope_ref = scope.get("refName") or ""
            hit = (
                scope_ref == wanted_ref
                if match_kind == "exact"
                else wanted_ref.startswith(scope_ref)
            )
            if same_repo and hit:
                applies.append(cfg)
                break
    return applies


def cmd_policy_check(args: argparse.Namespace) -> None:
    """Is this branch's policy set compatible with unattended auto-complete?

    /adopt runs this at setup time so a policy that can only be satisfied by a
    person is found while the user is sitting there, not at 3am mid-autopilot.
    """
    policies = branch_policies(args.repo, args.branch)
    rows = []
    for cfg in policies:
        name = cfg.get("type", {}).get("displayName", "policy")
        rows.append(
            {
                "policy": name,
                "blocking": bool(cfg.get("isBlocking")),
                "humanGated": name in HUMAN_GATED_POLICIES,
                "id": cfg.get("id"),
            }
        )
    blockers = [r for r in rows if r["blocking"] and r["humanGated"]]
    has_build = any(r["policy"] == "Build" and r["blocking"] for r in rows)
    result = {
        "branch": args.branch,
        "repository": args.repo,
        "policies": rows,
        "buildValidation": has_build,
        "autoMergeCompatible": not blockers,
        "humanGatedBlockers": [r["policy"] for r in blockers],
    }
    if args.json:
        print_json(result)
    else:
        if not rows:
            print(f"No enabled policies apply to {args.branch}.")
        for r in rows:
            flags = []
            if r["blocking"]:
                flags.append("blocking")
            if r["humanGated"]:
                flags.append("HUMAN-GATED")
            print(f"{r['policy']:<32} {', '.join(flags) or 'advisory'}")
        if not has_build:
            print(
                "\nWARNING: no blocking Build policy on this branch — nothing validates a PR, "
                "and auto-complete would merge unvalidated code."
            )
    if blockers:
        fail(
            POLICY_CHECK_HUMAN_GATED,
            f"\n{args.branch} has blocking policies only a person can satisfy: "
            f"{', '.join(r['policy'] for r in blockers)}. Ivan's PRs will sit unmerged until "
            f"someone acts on them. Either scope the policy away from Ivan's branches or accept "
            f"that every feature needs a manual approval.",
        )


def failing_build_evaluation(pr_id: int) -> tuple[int | None, str | None]:
    """(build id, policy evaluation id) behind a rejected Build policy on this PR.

    The evaluation id is what re-queues the build without touching the branch —
    the right move when the build died on infrastructure rather than on our code.
    """
    for policy in pr_policies(pr_id):
        if policy_name(policy) != "Build":
            continue
        if policy.get("status") not in ("rejected", "broken"):
            continue
        build = (policy.get("context") or {}).get("buildId")
        if build:
            return int(build), policy.get("evaluationId")
    return None, None


def build_timeline_issues(build_id: int) -> list[tuple[str, str]]:
    timeline = request_json(
        "GET",
        project_path(f"_apis/build/builds/{build_id}/timeline"),
    )
    issues = []
    for record in timeline.get("records", []):
        if record.get("result") not in ("failed", "canceled"):
            continue
        for issue in record.get("issues") or []:
            if issue.get("type") == "error":
                issues.append((record.get("name", "?"), issue.get("message", "")))
    return issues


def cmd_build_triage(args: argparse.Namespace) -> None:
    """Did the build fail on our code, or on the infrastructure?

    A lost agent or a dead package feed is not a quality failure, and charging it
    against the circuit breaker is what turns three flaky builds into a page.
    """
    build_id = args.build
    evaluation_id = None
    if build_id is None:
        if args.pr is None:
            fail(PR_WAIT_ERROR, "Pass a build id or --pr <id>.")
        build_id, evaluation_id = failing_build_evaluation(args.pr)
        if build_id is None:
            fail(
                PR_WAIT_ERROR,
                f"No rejected Build policy with a build id on PR !{args.pr} — "
                f"nothing to triage.",
            )
    build = request_json("GET", project_path(f"_apis/build/builds/{build_id}"))
    issues = build_timeline_issues(build_id)
    infra = [
        (task, message)
        for task, message in issues
        if any(sign in message.lower() for sign in INFRA_FAILURE_SIGNS)
    ]
    # Canceled with no error at all is the classic vanished-agent shape.
    verdict_infra = bool(infra) and len(infra) == len(issues) or (
        build.get("result") == "canceled" and not issues
    )
    verdict = "INFRA" if verdict_infra else "QUALITY"
    result = {
        "buildId": build_id,
        "buildNumber": build.get("buildNumber"),
        "result": build.get("result"),
        "url": build.get("_links", {}).get("web", {}).get("href"),
        "verdict": verdict,
        "evaluationId": evaluation_id,
        "failures": [{"task": t, "message": m} for t, m in issues],
    }
    if args.json:
        print_json(result)
    else:
        print(f"build {result['buildNumber']} (id {build_id}) result={build.get('result')}")
        for task, message in issues:
            print(f"  [{task}] {message.strip().splitlines()[0][:200]}")
        print(f"VERDICT: {verdict}")
        if verdict == "INFRA":
            print("Re-queue the build validation policy; do not count this as a failed cycle.")
            if evaluation_id:
                print(
                    f"  az repos pr policy queue --id {args.pr} "
                    f"--evaluation-id {evaluation_id} --org <org>"
                )
        else:
            print("The code is what failed. Fix it on the branch and push.")
    if verdict == "INFRA":
        sys.exit(BUILD_TRIAGE_INFRA)


# --------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Azure DevOps helper for Ivan")
    parser.add_argument("--org", help="https://dev.azure.com/<org>")
    parser.add_argument("--project", help="ADO team project name")
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("whoami", help="Verify credential, org and project")

    info = subparsers.add_parser(
        "project-info", help="Process, work item types, states and repos (used by /adopt)"
    )
    info.add_argument("--type", action="append", help="Type(s) to report states for")

    query = subparsers.add_parser("query", help="Run a WIQL query")
    source = query.add_mutually_exclusive_group()
    source.add_argument("--wiql", help="Inline WIQL")
    source.add_argument("--wiql-file", help="File containing WIQL")
    source.add_argument(
        "--preset", choices=sorted(PRESETS), default="open-features", help="Canned query"
    )
    query.add_argument("--area", help="Area path to scope a preset to (UNDER)")
    query.add_argument("--type", default="Feature", help="Work item type for a preset")

    show = subparsers.add_parser("show", help="Show one work item")
    show.add_argument("id", type=int)
    show.add_argument("--comments", action="store_true", help="Include the discussion")

    children = subparsers.add_parser("children", help="List child work items")
    children.add_argument("id", type=int)

    create = subparsers.add_parser("create", help="Create a work item")
    create.add_argument("--type", required=True, help="Epic, Feature, User Story, Task, Bug")
    create.add_argument("--title", required=True)
    create.add_argument("--description-file", help="Markdown file for the description")
    create.add_argument("--parent", type=int, help="Parent work item id")
    create.add_argument("--area")
    create.add_argument("--iteration")
    create.add_argument("--state")
    create.add_argument("--tag", action="append")
    create.add_argument("--apply", action="store_true")

    update = subparsers.add_parser("update", help="Update a work item")
    update.add_argument("id", type=int)
    update.add_argument("--title")
    update.add_argument("--description-file", help="Markdown file for the description")
    update.add_argument("--state")
    update.add_argument("--area")
    update.add_argument("--iteration")
    update.add_argument("--parent", type=int)
    update.add_argument("--add-tag", action="append")
    update.add_argument("--remove-tag", action="append")
    update.add_argument("--apply", action="store_true")

    comment = subparsers.add_parser("comment", help="Add a discussion comment")
    comment.add_argument("id", type=int)
    comment.add_argument("--file", help="Markdown file with the comment body")
    comment.add_argument("--text", help="Inline comment text")
    comment.add_argument("--apply", action="store_true")

    area = subparsers.add_parser("area", help="List or create area paths")
    area.add_argument("action", choices=["list", "ensure"])
    area.add_argument("name", nargs="?", help="Area path name (for ensure)")
    area.add_argument("--apply", action="store_true")

    pr_create = subparsers.add_parser("pr-create", help="Create a pull request")
    pr_create.add_argument("--repo", required=True)
    pr_create.add_argument("--source", required=True, help="Source branch")
    pr_create.add_argument("--target", default="main", help="Target branch (default main)")
    pr_create.add_argument("--title", required=True)
    pr_create.add_argument("--description-file", help="Markdown file for the PR body")
    pr_create.add_argument("--work-item", type=int, action="append", help="Work item to link")
    pr_create.add_argument("--squash", action="store_true")
    pr_create.add_argument("--delete-source-branch", action="store_true")
    pr_create.add_argument("--auto-complete", action="store_true")
    pr_create.add_argument("--draft", action="store_true")
    pr_create.add_argument("--apply", action="store_true")

    pr_link = subparsers.add_parser("pr-link", help="Link a PR to a work item")
    pr_link.add_argument("id", type=int, help="Work item id")
    pr_link.add_argument("--pr", type=int, required=True)
    pr_link.add_argument("--repo", required=True)
    pr_link.add_argument("--apply", action="store_true")

    pr_wait = subparsers.add_parser(
        "pr-wait",
        help="Block until a PR completes or stops making progress",
        description=(
            "Exit codes: 0 merged, 2 blocking build policy rejected (fix on the branch), "
            "3 merge conflicts (rebase and force-push), 4 needs a human, 5 abandoned, "
            "6 timed out while still in progress, 1 error."
        ),
    )
    pr_wait.add_argument("pr", type=int)
    pr_wait.add_argument("--repo", required=True)
    pr_wait.add_argument("--timeout", type=int, default=3600)
    pr_wait.add_argument("--interval", type=float, default=15.0)
    pr_wait.add_argument("--max-interval", type=float, default=60.0)

    policy_check = subparsers.add_parser(
        "policy-check",
        help="Is a branch's policy set compatible with unattended auto-complete?",
        description=(
            "Exit 0 if every blocking policy on the branch can be satisfied by CI alone, "
            "4 if one needs a person (Ivan's PRs would sit unmerged)."
        ),
    )
    policy_check.add_argument("--repo", required=True)
    policy_check.add_argument("--branch", default="main")

    build_triage = subparsers.add_parser(
        "build-triage",
        help="Did a failed build fail on our code or on the infrastructure?",
        description=(
            "Exit 0 for a quality failure (fix the code), 7 for an infrastructure failure "
            "(re-queue the policy; do not count it as a failed cycle)."
        ),
    )
    build_triage.add_argument("build", type=int, nargs="?", help="Build id")
    build_triage.add_argument("--pr", type=int, help="Find the failed build from this PR's policies")

    # Accept --json after the subcommand too. SUPPRESS keeps an absent sub-level
    # flag from overwriting the global one with its own default.
    for subparser in subparsers.choices.values():
        subparser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Raw JSON output",
        )

    return parser


COMMANDS = {
    "whoami": cmd_whoami,
    "project-info": cmd_project_info,
    "query": cmd_query,
    "show": cmd_show,
    "children": cmd_children,
    "create": cmd_create,
    "update": cmd_update,
    "comment": cmd_comment,
    "area": cmd_area,
    "pr-create": cmd_pr_create,
    "pr-link": cmd_pr_link,
    "pr-wait": cmd_pr_wait,
    "policy-check": cmd_policy_check,
    "build-triage": cmd_build_triage,
}


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "area" and args.action == "ensure" and not args.name:
        raise SystemExit("`area ensure` needs a name.")
    set_context(args)
    COMMANDS[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
