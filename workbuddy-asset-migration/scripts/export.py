#!/usr/bin/env python3
"""Export WorkBuddy personal assets to a portable .zip package.

Two-package layout:
  <output>.zip                  - main: configs, skills, DB, conversations, memory-export.md reference
  <output>-workspaces.zip       - optional: workspace file trees (cross-machine only)

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
from __future__ import annotations

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

import argparse
import json
import os
import platform
import shutil
import sqlite3
import socket
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make `scripts.lib` importable when invoked directly
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib import detect, manifest as M, db as DB, fs, report as R, walk


def _readme_for_package(meta: dict) -> str:
    return f"""# WorkBuddy 资产迁移包

导出时间：{meta['export_time']}
源版本：{meta['source_variant']} ({meta['source_root']})
源 OS / 主机 / Home：{meta.get('source_os', '?')} / {meta.get('source_hostname', '?')} / {meta.get('source_home', '?')}
源 user_id：{meta['source_user_id']}
{'多 uid 警告：' + ', '.join(meta['source_user_ids_all']) if len(meta.get('source_user_ids_all', [])) > 1 else ''}

## 怎么用

```
python <skill_path>/scripts/import.py --package <this.zip> --target auto --dry-run
python <skill_path>/scripts/import.py --package <this.zip> --target auto
```

跨机器（路径有变化）时：
```
python <skill_path>/scripts/import.py --package <this.zip> \\
    --target ~/.workbuddy \\
    --path-map {meta.get('source_home', '~')}={'/<target_home>'} \\
    --target-os {'<darwin|win32|linux>'}
```

附带 workspace 内容时再加：`--workspaces-package <this>-workspaces.zip --workspace-destination <dir>`

## 包含

{json.dumps(meta['asset_inventory'], indent=2, ensure_ascii=False)}

## 注意

- 导入前请退出 WorkBuddy 客户端，避免 SQLite 写锁冲突
- **导入完成后请重启 WorkBuddy** 使改动生效（详见 import 报告）
- 默认合并不覆盖；要覆盖加 `--overwrite`（自动备份 `.bak-<ts>`）
- 若包里含 `.credentials.json`：OAuth refresh_token 跨机器可能失效，导入后请到 connector 面板重新授权
- `memory-export.md` 仅供人工参考，不会被导入；Memory 请在目标客户端设置中同步
- 若两端 user_id 不同：用 `--uid-map 源uid=目标uid` 显式映射
- 若两端目录布局不同（跨机器、用户名不同等）：用 `--path-map 源前缀=目标前缀` 重写所有路径相关字段
"""


def _build_args():
    ap = argparse.ArgumentParser(description="Export WorkBuddy personal assets.", epilog=AUTHOR_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="auto", help="Source root path or 'auto'")
    ap.add_argument("--output", default=None, help="Output zip or dir")
    ap.add_argument("--no-conversations", action="store_true")
    ap.add_argument("--no-credentials", action="store_true")
    ap.add_argument("--no-archive", action="store_true", help="Output directory instead of zip")
    ap.add_argument("--include-logs", action="store_true", help="(debug) include logs/")
    ap.add_argument(
        "--exclude-session-id",
        action="append", default=None,
        help="Exclude session(s) from sessions table. May repeat. Also reads "
             "WORKBUDDY_CURRENT_SESSION_ID / CODEBUDDY_SESSION_ID env vars.",
    )
    ap.add_argument(
        "--all-users", action="store_true",
        help="Export assets from ALL user_ids (default: only current user). "
             "When omitted, the script auto-detects the current user by matching "
             "the workspace directory against sessions.cwd.",
    )

    # Workspace bundling
    ap.add_argument(
        "--with-workspaces", action="store_true",
        help="Produce a second zip <output>-workspaces.zip containing workspace files. "
             "Off by default to avoid large packages on cross-machine migration."
    )
    ap.add_argument(
        "--workspace-include", action="append", default=None,
        help="Explicit workspace path(s) to include. May repeat. "
             "Default: all paths in workspaces table.",
    )
    ap.add_argument(
        "--workspace-exclude-pattern", action="append", default=None,
        help="Additional exclude glob pattern. May repeat. Appended to defaults from "
             "references/workspace_excludes.md. Supports three styles: "
             "(1) dir basename with trailing / e.g. 'node_modules/' — prunes any directory "
             "matching by name; "
             "(2) filename glob without / e.g. '*.pyc' — matches against filename; "
             "(3) path glob containing / but not ending with / e.g. 'subdir/*.env' or "
             "'20260320184503/*' — matches against the full relative path (POSIX separators).",
    )
    ap.add_argument(
        "--no-default-excludes", action="store_true",
        help="Disable the default exclude list (not recommended)",
    )
    ap.add_argument(
        "--workspace-size-limit", type=int, default=5 * 1024 * 1024 * 1024,
        help="Per-workspace size limit after excludes (bytes). Default 5GB. "
             "Auto-discovered workspaces over this are skipped; explicit --workspace-include paths are kept.",
    )
    ap.add_argument(
        "--workspace-output", default=None,
        help="Path for the workspace bundle zip. Default: <output>-workspaces.zip",
    )

    # Dry-run
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Don't write any files. Print a single JSON plan to stdout instead.",
    )

    ap.add_argument(
        "--inventory",
        default=str(_HERE.parent / "references" / "asset_inventory.md"),
        help="Path to asset_inventory.md",
    )
    ap.add_argument(
        "--workspace-excludes",
        default=str(_HERE.parent / "references" / "workspace_excludes.md"),
        help="Path to workspace_excludes.md",
    )
    return ap.parse_args()


def main() -> int:
    args = _build_args()
    rep = R.Report(mode="export", dry_run=args.dry_run)
    rep.start()

    inventory = M.load_inventory(Path(args.inventory))

    # 1. Resolve source
    try:
        src_root = detect.resolve_root(args.source, must_exist=True, interactive=not args.dry_run)
    except FileNotFoundError as e:
        if args.dry_run:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[error] {e}", file=sys.stderr)
        return 1
    rep.source = str(src_root.path)
    if not args.dry_run:
        R.echo(f"Source: {src_root.path} (variant={src_root.variant})")

    # 2. user_id detection
    uids = detect.extract_user_ids(src_root.db_path)
    primary_uid = uids[0][0] if uids else None
    all_uids = [u for u, _ in uids]

    # 2a. Detect current user_id from workspace path
    current_uid: Optional[str] = None
    if not args.all_users and src_root.db_path.is_file():
        current_uid = detect.detect_current_user_id(src_root.db_path)
        if not args.dry_run:
            if current_uid:
                R.echo(f"Current user: {current_uid}")
                if primary_uid and current_uid != primary_uid:
                    R.echo(
                        f"  (primary user by session count: {primary_uid}, "
                        f"exporting only current user)"
                    )
            else:
                R.echo(
                    "Could not detect current user (no matching workspace). "
                    "Falling back to export all users."
                )
    elif args.all_users and not args.dry_run:
        R.echo("Exporting all users (--all-users)")

    # 3. Detect host info for cross-machine awareness
    src_os = sys.platform
    src_hostname = socket.gethostname()
    src_home = str(Path.home())

    # 4. Exclude self/active sessions
    exclude_session_ids: list = list(args.exclude_session_id or [])
    for env_key in ("WORKBUDDY_CURRENT_SESSION_ID", "CODEBUDDY_SESSION_ID"):
        v = os.environ.get(env_key)
        if v and v not in exclude_session_ids:
            exclude_session_ids.append(v)

    # 5. Determine workspace candidates
    workspace_paths = _collect_workspace_paths(
        src_root.db_path, args.workspace_include
    )

    # 6. Build the default-excludes list
    default_excludes = (
        []
        if args.no_default_excludes
        else walk.load_default_excludes(Path(args.workspace_excludes))
    )
    user_excludes = args.workspace_exclude_pattern or []
    all_excludes = default_excludes + user_excludes

    # 7. Scan workspaces (always — gives accurate sizes even for non-bundle dry-run)
    explicit_workspace_paths = {str(Path(p).expanduser()) for p in (args.workspace_include or [])}
    workspace_scans: List[Tuple[str, walk.WorkspaceScan, bool]] = []
    if args.with_workspaces or args.dry_run:
        for wp in workspace_paths:
            root = Path(wp).expanduser()
            if not root.is_dir():
                # workspace path no longer exists on disk; skip
                continue
            scan = walk.scan_workspace(root, all_excludes)
            workspace_scans.append((wp, scan, str(root) in explicit_workspace_paths))

    # ---- DRY-RUN: emit JSON and exit ----
    if args.dry_run:
        plan = _build_dry_run_plan(
            src_root=src_root,
            src_os=src_os, src_hostname=src_hostname, src_home=src_home,
            uids=all_uids, exclude_session_ids=exclude_session_ids,
            current_uid=current_uid, all_users=args.all_users,
            inventory=inventory,
            workspace_scans=workspace_scans,
            with_workspaces=args.with_workspaces,
            args=args,
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if len(all_uids) > 1 and (args.all_users or not current_uid):
        rep.warn(
            f"Multiple user_ids in source ({len(all_uids)}): "
            + ", ".join(all_uids)
            + ". Import will require --uid-map to disambiguate."
        )

    # ---- ACTUAL EXPORT ----
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    if args.output:
        out = Path(args.output).expanduser()
    else:
        out = Path.cwd() / f"workbuddy-assets-{ts}{'.dir' if args.no_archive else '.zip'}"
    workspace_out = (
        Path(args.workspace_output).expanduser()
        if args.workspace_output
        else out.with_name(out.stem + "-workspaces.zip")
    )

    with tempfile.TemporaryDirectory(prefix="wb-export-") as td:
        staging = Path(td) / "package"
        staging.mkdir(parents=True)

        # 4a. Reduced DB
        counts: Dict[str, int] = {}
        session_ids: set = set()
        db_dir = staging / "db"
        db_dir.mkdir(parents=True)
        out_db = db_dir / "workbuddy.db"
        if src_root.db_path.is_file():
            db_result = DB.export_reduced_db(
                src_root.db_path, out_db, inventory["db_tables"],
                exclude_session_ids=exclude_session_ids,
                user_id_filter=current_uid if not args.all_users else None,
            )
            counts = db_result["counts"]
            db_section = {"action": "exported", **counts}
            if db_result["excluded"]:
                db_section["excluded"] = db_result["excluded"]
            rep.add("db", db_section)
            if exclude_session_ids:
                rep.note(
                    f"Excluded self/active session ids: "
                    + ", ".join(exclude_session_ids)
                )
            sess_ex = db_result["excluded"].get("sessions", {})
            if sess_ex.get("by_status"):
                rep.note(
                    f"Sessions with non-terminal status skipped: "
                    f"{sess_ex['by_status']}"
                )
            R.echo(f"DB: {sum(counts.values())} rows across {len(counts)} tables")
            conn = sqlite3.connect(str(out_db))
            cur = conn.execute("SELECT id FROM sessions")
            session_ids = {row[0] for row in cur.fetchall()}
            conn.close()
        else:
            rep.warn(f"Source DB missing: {src_root.db_path}")

        # 4b. File assets
        _copy_file_assets(src_root, staging, inventory["file_assets"], rep)

        # 4b1. Memory is cloud-synced; export local records as a reference-only markdown file.
        memory_export_info = _write_memory_export_markdown(
            src_root, staging, current_uid=current_uid, all_users=args.all_users, rep=rep
        )

        # 4c. Warned assets (connectors)
        _copy_warned_assets(src_root, staging, inventory["warned_assets"],
                            args.no_credentials, rep)

        # 4c1. Filter connectors by current user_id
        if current_uid and not args.all_users:
            _filter_connectors_by_user(staging, current_uid, rep)

        # 4d. Conversations
        if not args.no_conversations:
            convo = inventory["conversations"]
            src_projects = src_root.path / convo["path"]
            jsonls = fs.list_session_jsonls(src_projects)
            kept = fs.filter_jsonls_by_session_ids(jsonls, session_ids, src_projects)
            dst_projects = staging / convo["path"]
            total_bytes = 0
            for jp in kept:
                rel = jp.relative_to(src_projects)
                dst = dst_projects / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(jp, dst)
                total_bytes += jp.stat().st_size

            # Also copy *.meta.json sidecar files for retained sessions only.
            meta_count = 0
            if src_projects.is_dir():
                for mf in src_projects.glob("**/*.meta.json"):
                    rel = mf.relative_to(src_projects)
                    session_id = rel.parts[0] if rel.parts else ""
                    if session_id not in session_ids:
                        continue
                    dst = dst_projects / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(mf, dst)
                    meta_count += 1
            rep.add("conversations", {
                "action": "copied", "jsonl_count": len(kept),
                "meta_files": meta_count, "bytes": total_bytes,
                "orphans_dropped": len(jsonls) - len(kept),
            })
        else:
            rep.add("conversations", {"action": "excluded"})

        # 4e. Logs (debug only)
        if args.include_logs:
            logs_src = src_root.path / "logs"
            if logs_src.is_dir():
                shutil.copytree(logs_src, staging / "logs")
                rep.add("logs", {"action": "copied (debug)"})

        # 5. Workspace bundle (separate zip)
        workspaces_in_manifest: List[Dict] = []
        workspace_bundle_path: Optional[Path] = None
        if args.with_workspaces and workspace_scans:
            workspace_bundle_path, workspaces_in_manifest = _write_workspace_bundle(
                workspace_scans=workspace_scans,
                output=workspace_out,
                size_limit=args.workspace_size_limit,
                rep=rep,
            )

        # 6. Manifest
        asset_inv = {
            "db": counts,
            "skills": sorted(
                [p.name for p in (staging / "skills").iterdir() if p.is_dir()]
                if (staging / "skills").is_dir()
                else []
            ),
            "memory_export": memory_export_info,
            "projects": {
                "jsonl_count": rep.sections.get("conversations", {}).get("jsonl_count", 0),
                "bytes": rep.sections.get("conversations", {}).get("bytes", 0),
            },
            "connectors_uids": rep.sections.get("warned:connectors", {}).get("uids", []),
            "identity_files": sorted(
                p.name for p in staging.glob("*.md")
                if p.name in ("IDENTITY.md", "SOUL.md", "USER.md")
            ),
            "configs": sorted(
                p.name for p in staging.glob("*.json")
                if p.name in ("settings.json", "mcp.json", "models.json")
            ),
        }
        manifest_meta = M.Manifest.now(
            source_variant=src_root.variant,
            source_root=str(src_root.path),
            source_user_id=primary_uid,
            source_user_ids_all=all_uids,
            source_os=src_os,
            source_hostname=src_hostname,
            source_home=src_home,
            source_workbuddy_dir=str(src_root.path),
            options={
                "conversations": not args.no_conversations,
                "credentials": not args.no_credentials,
                "with_workspaces": args.with_workspaces,
            },
            asset_inventory=asset_inv,
            workspaces=workspaces_in_manifest,
            workspaces_package=workspace_bundle_path.name if workspace_bundle_path else None,
        )

        if out_db.is_file():
            manifest_meta.checksums["db/workbuddy.db"] = M.sha256_file(out_db)

        (staging / "manifest.json").write_text(
            manifest_meta.to_json(), encoding="utf-8"
        )
        (staging / "README.md").write_text(
            _readme_for_package(json.loads(manifest_meta.to_json())),
            encoding="utf-8",
        )

        # 7. Materialize main output
        if args.no_archive:
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(staging, out)
        else:
            with zipfile.ZipFile(
                out, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as zf:
                for f in staging.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(staging))

    # 8. Finalize report
    rep.finish()
    size_mb = out.stat().st_size / (1024 * 1024) if out.is_file() else _dir_size(out) / (1024 * 1024)
    rep.note(f"Main package: {out} ({size_mb:.1f} MB)")
    if workspace_bundle_path and workspace_bundle_path.exists():
        ws_mb = workspace_bundle_path.stat().st_size / (1024 * 1024)
        rep.note(f"Workspace bundle: {workspace_bundle_path} ({ws_mb:.1f} MB)")
    R.print_report(rep)
    return 0


# --- helpers ---

def _collect_workspace_paths(db_path: Path, override: Optional[List[str]]) -> List[str]:
    """Return list of absolute directory paths to include in the workspace bundle.

    Combines two sources:
    1. workspaces table (formally opened projects)
    2. sessions.cwd (all conversation working directories)

    This ensures temporary/ad-hoc conversation directories that were never
    registered as a workspace are also included, so their generated artifacts
    (reports, scripts, etc.) are carried over during migration.
    """
    if override:
        return [str(Path(p).expanduser().resolve()) for p in override]
    if not db_path.is_file():
        return []
    paths: List[str] = []
    seen: set = set()
    try:
        conn = sqlite3.connect(str(db_path))
        # 1. Registered workspaces
        cur = conn.execute("SELECT DISTINCT path FROM workspaces ORDER BY last_opened_at DESC")
        for row in cur.fetchall():
            p = row[0]
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
        # 2. Session working directories (captures ad-hoc conversations)
        try:
            cur2 = conn.execute("SELECT DISTINCT cwd FROM sessions WHERE cwd IS NOT NULL AND cwd != ''")
            for row in cur2.fetchall():
                p = row[0]
                if p and p not in seen:
                    seen.add(p)
                    paths.append(p)
        except sqlite3.Error:
            pass  # older DBs may lack cwd column
        return paths
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _copy_file_assets(src_root, staging: Path, file_assets: list, rep) -> None:
    for asset in file_assets:
        rel = asset["path"]
        src_path = src_root.path / rel
        dst_path = staging / rel
        if asset["type"] == "dir-of-dirs":
            if src_path.is_dir():
                dst_path.mkdir(parents=True, exist_ok=True)
                skip = asset.get("skip_indices", [])
                copied = []
                for child in sorted(src_path.iterdir()):
                    if child.name in skip:
                        continue
                    if child.is_dir():
                        shutil.copytree(child, dst_path / child.name)
                        copied.append(child.name)
                rep.add(f"file:{rel}", {"action": "copied", "count": len(copied)})
        elif asset["type"] == "dir-of-files":
            if src_path.is_dir():
                dst_path.mkdir(parents=True, exist_ok=True)
                pat = asset.get("pattern", "*")
                excl = tuple(asset.get("exclude_suffix", []))
                copied = 0
                for child in src_path.glob(pat):
                    if not child.is_file():
                        continue
                    if any(child.name.endswith(s) for s in excl):
                        continue
                    shutil.copy2(child, dst_path / child.name)
                    copied += 1
                rep.add(f"file:{rel}", {"action": "copied", "count": copied})
        elif asset["type"] in ("json", "file"):
            if src_path.is_file():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                rep.add(f"file:{rel}", {"action": "copied"})


def _copy_warned_assets(src_root, staging: Path, warned_assets: list,
                        no_credentials: bool, rep) -> None:
    for asset in warned_assets:
        rel = asset["path"]
        src_path = src_root.path / rel
        dst_path = staging / rel
        if not src_path.is_dir():
            continue
        dst_path.mkdir(parents=True, exist_ok=True)
        connector_uids = []
        for child in src_path.iterdir():
            if child.is_file():
                shutil.copy2(child, dst_path / child.name)
            elif child.is_dir():
                shutil.copytree(child, dst_path / child.name)
                connector_uids.append(child.name)
                if no_credentials:
                    for fn in asset.get("credentials_files", []):
                        cf = dst_path / child.name / fn
                        if cf.exists():
                            cf.unlink()
        rep.add(f"warned:{rel}", {
            "action": "copied", "uids": connector_uids,
            "credentials_dropped": no_credentials,
            "warning": asset.get("warn"),
        })
        if asset.get("warn") and not no_credentials:
            rep.warn(asset["warn"])


def _write_memory_export_markdown(
    src_root,
    staging: Path,
    *,
    current_uid: Optional[str],
    all_users: bool,
    rep,
) -> Dict[str, object]:
    """Write local memory files as reference-only markdown; never import them."""
    memory_dir = src_root.path / "memory"
    if not memory_dir.is_dir():
        info = {"action": "skipped", "reason": "source memory dir absent"}
        rep.add("memory_export", info)
        return info

    selected = []
    for mf in sorted(memory_dir.glob("*_memory.md")):
        if not mf.is_file():
            continue
        uid_in_name = mf.stem.rsplit("_memory", 1)[0]
        if current_uid and not all_users and uid_in_name != current_uid:
            continue
        selected.append((uid_in_name, mf))

    if not selected:
        info = {"action": "skipped", "reason": "no matching local memory files"}
        rep.add("memory_export", info)
        return info

    out = staging / "memory-export.md"
    lines = [
        "# WorkBuddy Memory 导出参考",
        "",
        "> 这份文件仅用于人工参考，不会被 import.py 或 migrate_inplace.py 自动导入。",
        "> WorkBuddy Memory 由云端同步；请在目标客户端登录账号后，到客户端设置中执行 Memory 同步。",
        "",
        f"导出时间：{datetime.now().isoformat(timespec='seconds')}",
        f"源目录：{src_root.path}",
        f"导出范围：{'全部本地 user_id' if all_users else (current_uid or '未识别当前账号，保留全部本地 memory 文件')}",
        "",
    ]
    for uid, mf in selected:
        text = mf.read_text(encoding="utf-8", errors="replace")
        rel = mf.relative_to(src_root.path)
        lines.extend([
            "---",
            "",
            f"## user_id: `{uid}`",
            "",
            f"源文件：`{rel.as_posix()}`",
            "",
            "````markdown",
            text.rstrip(),
            "````",
            "",
        ])
    out.write_text("\n".join(lines), encoding="utf-8")
    info = {
        "action": "exported-reference",
        "path": "memory-export.md",
        "files": len(selected),
        "uids": sorted({uid for uid, _ in selected}),
        "note": "reference only; sync Memory in client settings on the target side",
    }
    rep.add("memory_export", info)
    return info


def _filter_connectors_by_user(staging: Path, current_uid: str, rep) -> None:
    """Remove connector subdirectories belonging to other user_ids."""
    connectors_dir = staging / "connectors"
    if not connectors_dir.is_dir():
        return
    removed = 0
    for child in list(connectors_dir.iterdir()):
        if child.is_dir() and child.name != current_uid:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    if removed:
        rep.add("filter:connectors", {"action": "removed", "count": removed, "kept_uid": current_uid})


def _write_workspace_bundle(
    workspace_scans: List[Tuple[str, walk.WorkspaceScan, bool]],
    output: Path,
    size_limit: int,
    rep,
) -> Tuple[Path, List[Dict]]:
    """Pack scanned workspaces into output zip. Returns (path, manifest_entries)."""
    from scripts.lib.pathmap import compress_workspace_path

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_entries: List[Dict] = []
    bundle_manifest = {"workspaces": []}

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for src_path, scan, explicit_include in workspace_scans:
            project_id = compress_workspace_path(src_path)
            if scan.files_kept_bytes > size_limit and not explicit_include:
                rep.warn(
                    f"Workspace {src_path} ({scan.files_kept_bytes:,} bytes after excludes) "
                    f"exceeds limit {size_limit:,} — skipped. "
                    f"Use --workspace-include {src_path} to force, or raise --workspace-size-limit."
                )
                continue
            written = walk.pack_workspace_files(scan, zf, f"workspaces/{project_id}")
            entry = {
                "source_path": src_path,
                "project_id": project_id,
                "files_kept": len(scan.files_kept),
                "bytes_uncompressed": written,
                "excluded_count": scan.files_excluded_count,
                "explicit_include": explicit_include,
            }
            bundle_manifest["workspaces"].append(entry)
            manifest_entries.append(entry)

        zf.writestr("manifest.json", json.dumps(bundle_manifest, ensure_ascii=False, indent=2))

    if not manifest_entries:
        # Nothing got packed — remove the empty bundle
        output.unlink(missing_ok=True)
    return output, manifest_entries


def _build_dry_run_plan(
    *, src_root, src_os: str, src_hostname: str, src_home: str,
    uids: List[str], exclude_session_ids: List[str],
    current_uid: Optional[str], all_users: bool,
    inventory: dict,
    workspace_scans: List[Tuple[str, walk.WorkspaceScan, bool]],
    with_workspaces: bool,
    args,
) -> dict:
    from scripts.lib.pathmap import compress_workspace_path

    # Estimate main package contents
    main_summary: Dict[str, object] = {
        "configs_present": [
            p for p in ("settings.json", "mcp.json", "models.json")
            if (src_root.path / p).is_file()
        ],
        "identity_files_present": [
            p for p in ("IDENTITY.md", "SOUL.md", "USER.md")
            if (src_root.path / p).is_file()
        ],
    }
    skills_dir = src_root.path / "skills"
    if skills_dir.is_dir():
        main_summary["skills_count"] = sum(
            1 for p in skills_dir.iterdir() if p.is_dir()
        )
    memory_dir = src_root.path / "memory"
    if memory_dir.is_dir():
        memory_files = []
        for p in memory_dir.glob("*_memory.md"):
            uid = p.stem.rsplit("_memory", 1)[0]
            if current_uid and not all_users and uid != current_uid:
                continue
            memory_files.append({"uid": uid, "file": p.name, "bytes": p.stat().st_size})
        main_summary["memory_export_reference"] = {
            "action": "would-write-memory-export.md",
            "files": memory_files,
            "note": "reference only; Memory must be synced in client settings",
        }

    # DB row counts (read-only)
    if src_root.db_path.is_file():
        try:
            conn = sqlite3.connect(f"file:{src_root.db_path}?mode=ro", uri=True)
            db_counts: Dict[str, int] = {}
            for t in inventory["db_tables"]:
                try:
                    cur = conn.execute(f"SELECT COUNT(*) FROM {t['name']}")
                    db_counts[t["name"]] = cur.fetchone()[0]
                except sqlite3.Error:
                    db_counts[t["name"]] = 0
            main_summary["db_table_row_counts"] = db_counts
            conn.close()
        except sqlite3.Error:
            pass

    # Workspaces analysis
    workspaces_out = []
    caveats = []
    total_kept = 0

    # Collect user exclude patterns for format hint
    user_excludes = getattr(args, "workspace_exclude_pattern", None) or []
    path_like_excludes = [p for p in user_excludes if "/" in p and not p.endswith("/")]
    format_hint = ""
    if path_like_excludes:
        format_hint = (
            f"Path-pattern exclude(s) detected: {path_like_excludes}. "
            "These match against the full relative path using / as separator."
        )

    for src_path, scan, explicit_include in workspace_scans:
        wcaveats = walk.detect_caveats(scan)
        if wcaveats:
            caveats.append({"workspace": src_path, "items": wcaveats})
        workspaces_out.append({
            "source_path": src_path,
            "project_id": compress_workspace_path(src_path),
            "source_du_bytes": scan.source_du_bytes,
            "files_kept": len(scan.files_kept),
            "files_excluded": scan.files_excluded_count,
            "after_excludes_bytes": scan.files_kept_bytes,
            "estimated_zip_bytes": walk.estimate_zip_bytes(scan.files_kept_bytes),
            "explicit_include": explicit_include,
            "excluded_by_pattern_top": dict(
                sorted(scan.excluded_by_pattern.items(),
                       key=lambda kv: -kv[1])[:5]
            ),
            "warnings": [],
        })
        total_kept += scan.files_kept_bytes

    return {
        "kind": "export-plan",
        "source": {
            "root": str(src_root.path),
            "variant": src_root.variant,
            "os": src_os,
            "hostname": src_hostname,
            "home": src_home,
            "user_ids": uids,
            "current_user_id": current_uid,
            "all_users": all_users,
            "exclude_session_ids": exclude_session_ids,
        },
        "main_package": {
            "contents_summary": main_summary,
        },
        "workspaces": workspaces_out,
        "workspaces_package": (
            {
                "estimated_total_bytes": total_kept,
                "estimated_zip_bytes": walk.estimate_zip_bytes(total_kept),
            } if with_workspaces and workspaces_out else None
        ),
        "caveats": caveats,
        "notes": [
            "After import, target user must restart WorkBuddy to see DB changes.",
            "Cross-machine: use --path-map src_prefix=dst_prefix on import to rewrite paths.",
            "Cross-machine workspaces require --with-workspaces (off by default).",
            "--workspace-exclude-pattern supports path globs (e.g. 'dir/subdir/*'), "
            "dir names with trailing / (e.g. 'node_modules/'), and filename globs (e.g. '*.pyc').",
        ] + ([format_hint] if format_hint else []),
    }


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


if __name__ == "__main__":
    sys.exit(main())
