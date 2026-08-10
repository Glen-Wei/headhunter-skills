#!/usr/bin/env python3
"""Import a WorkBuddy migration package into a target root, merging without clobbering.
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
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib import detect, manifest as M, db as DB, fs, configs, report as R
from scripts.lib.pathmap import PathMapper


def _parse_uid_map(args_list: Optional[List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for s in args_list or []:
        if "=" not in s:
            raise ValueError(f"Bad --uid-map value: {s} (expected src=dst)")
        a, b = s.split("=", 1)
        a, b = a.strip(), b.strip()
        if not a or not b:
            raise ValueError(f"Bad --uid-map value: {s}")
        out[a] = b
    return out


def _parse_path_map(args_list: Optional[List[str]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for s in args_list or []:
        if "=" not in s:
            raise ValueError(f"Bad --path-map value: {s} (expected src=dst)")
        a, b = s.split("=", 1)
        a, b = a.strip(), b.strip()
        if not a or not b:
            raise ValueError(f"Bad --path-map value: {s}")
        out.append((a, b))
    return out


def _unpack_to_temp(pkg: Path, td: Path) -> Path:
    """Return path to package root (containing manifest.json)."""
    if pkg.is_dir():
        return pkg
    if pkg.is_file() and pkg.suffix.lower() == ".zip":
        extract_to = td / "unpacked"
        extract_to.mkdir()
        with zipfile.ZipFile(pkg) as zf:
            for info in zf.infolist():
                target = (extract_to / info.filename).resolve()
                if not str(target).startswith(str(extract_to.resolve())):
                    raise ValueError(f"Unsafe zip member path: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        # The zip stores files at the package root directly
        return extract_to
    raise ValueError(f"Unsupported package: {pkg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Import a WorkBuddy migration package.", epilog=AUTHOR_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, help="zip or directory")
    ap.add_argument("--target", default="auto", help="Target root or 'auto'")
    ap.add_argument("--overwrite", action="store_true", help="Replace conflicts (auto backup)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--uid-map", action="append", default=None, help="src=dst (may repeat)"
    )
    ap.add_argument("--no-credentials", action="store_true")
    ap.add_argument("--no-conversations", action="store_true")
    ap.add_argument("--skip-db", action="store_true")
    ap.add_argument("--skip-skills", action="store_true")
    ap.add_argument("--skip-configs", action="store_true")

    # Cross-machine
    ap.add_argument(
        "--path-map", action="append", default=None,
        help="Path prefix mapping src=dst. May repeat. Required when source machine "
             "(per manifest) and target machine layouts differ. Longest prefix wins.",
    )
    ap.add_argument(
        "--target-os", default=None,
        help="Target OS for path normalization (darwin|win32|linux). "
             "Default: current OS (sys.platform).",
    )
    ap.add_argument(
        "--workspaces-package", default=None,
        help="Path to <main>-workspaces.zip. If provided, workspace files are extracted.",
    )
    ap.add_argument(
        "--workspace-destination", default=None,
        help="Root dir for extracted workspaces when path-map can't resolve. "
             "Default: ~/wb-imported-workspaces/",
    )

    ap.add_argument(
        "--inventory",
        default=str(_HERE.parent / "references" / "asset_inventory.md"),
        help="Path to asset_inventory.md",
    )
    args = ap.parse_args()


    # Fix encoding on Windows: default GBK codec corrupts non-ASCII output
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    rep = R.Report(mode="import", dry_run=args.dry_run, overwrite=args.overwrite)
    rep.start()
    inventory = M.load_inventory(Path(args.inventory))
    uid_map = _parse_uid_map(args.uid_map)
    path_map_rules = _parse_path_map(args.path_map)

    with tempfile.TemporaryDirectory(prefix="wb-import-") as td:
        pkg_root = _unpack_to_temp(Path(args.package).expanduser(), Path(td))
        manifest_path = pkg_root / "manifest.json"
        if not manifest_path.is_file():
            print(f"[error] manifest.json not found in package", file=sys.stderr)
            return 1
        meta = M.Manifest.load(manifest_path)
        try:
            meta.validate_for_import()
        except ValueError as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1

        # Resolve target
        try:
            target = detect.resolve_root(args.target, must_exist=False, interactive=True)
        except FileNotFoundError as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1
        rep.source = str(pkg_root)
        rep.target = str(target.path)
        target.path.mkdir(parents=True, exist_ok=True)

        # ---- UID resolution ----
        # CN and Intl editions use different account systems, so user_id mismatch
        # is expected and normal. We must map every source uid to a target uid so
        # the imported data is visible to the currently logged-in account on the
        # target side.  If we cannot determine the target uid, the imported rows
        # would keep the source uid (via the ELSE branch in DB.merge_table's CASE
        # expression) and be invisible — block and ask the user to resolve.
        target_uids = detect.extract_user_ids(target.path / "workbuddy.db")
        target_primary = target_uids[0][0] if target_uids else None
        source_uids_all = meta.source_user_ids_all or (
            [meta.source_user_id] if meta.source_user_id else []
        )

        # First, check if user-provided --uid-map covers all source uids.
        # If --uid-map is explicitly provided and covers all source uids,
        # we can proceed even when target_primary is None (empty target DB).
        unmapped_src = [u for u in source_uids_all if u not in uid_map]

        if not target_primary and unmapped_src:
            print(
                "[error] Cannot determine the target user_id automatically.\n"
                "  The target database is empty (you haven't logged in to the "
                "target WorkBuddy edition yet, or have never created a session).\n"
                "  Without a target uid, imported sessions will keep the source "
                "uid and be invisible in the client.\n"
                "\n"
                "  Please do ONE of the following:\n"
                "    1. Open the target WorkBuddy edition, log in, and create "
                "at least one conversation — this writes your uid into the DB. "
                "Then re-run import.\n"
                "    2. Provide --uid-map <source_uid>=<target_uid> explicitly.\n"
                "\n"
                f"  Source uid(s) in package: {', '.join(source_uids_all)}",
                file=sys.stderr,
            )
            return 1

        # Resolve uid_map: user-provided --uid-map overrides take precedence;
        # any source uid not yet mapped defaults to target_primary.
        if target_primary:
            for u in unmapped_src:
                uid_map[u] = target_primary

        # ---- Cross-machine detection ----
        import socket
        target_os = args.target_os or sys.platform
        current_hostname = socket.gethostname()
        current_home = str(Path.home())
        is_same_machine = (
            meta.source_os == target_os
            and meta.source_hostname == current_hostname
            and meta.source_home == current_home
        )
        rep.note(
            f"Source machine: {meta.source_os}/{meta.source_hostname} ({meta.source_home})"
            if meta.source_os else "Source machine info: <unknown — pre-v2 package>"
        )
        rep.note(
            f"Target machine: {target_os}/{current_hostname} ({current_home})"
        )
        rep.note(
            f"Mode: {'same-machine' if is_same_machine else 'cross-machine'}"
        )

        mapper: Optional[PathMapper] = None
        if path_map_rules or not is_same_machine:
            # Build mapper; if no rules provided, mapper just leaves paths as-is
            # but cross-machine import will warn loudly.
            if not path_map_rules and not is_same_machine:
                rep.warn(
                    "Cross-machine import but no --path-map rules provided. "
                    "DB paths and meta.json cwd fields will keep source values "
                    "(history will not open on target). Consider re-running with "
                    f"--path-map {meta.source_home or '<src>'}={current_home}"
                )
            mapper = PathMapper(
                rules=path_map_rules,
                src_os=meta.source_os or sys.platform,
                dst_os=target_os,
            )

        ts = fs.make_ts()

        # ---- DB merge ----
        if not args.skip_db:
            target_db = target.path / "workbuddy.db"
            src_db = pkg_root / "db" / "workbuddy.db"
            if src_db.is_file():
                if not args.dry_run:
                    bak = fs.backup(target_db, ts) if target_db.exists() else None
                    if bak:
                        rep.add_backup(bak)
                    db_section = _merge_db(
                        target_db,
                        src_db,
                        inventory["db_tables"],
                        overwrite=args.overwrite,
                        uid_map=uid_map,
                    )
                else:
                    db_section = _dryrun_db(
                        target_db, src_db, inventory["db_tables"]
                    )
                rep.add("db", db_section)
            else:
                rep.add("db", {"action": "skipped", "reason": "package has no db"})
        else:
            rep.add("db", {"action": "excluded via --skip-db"})

        # ---- File assets ----
        for asset in inventory["file_assets"]:
            rel = asset["path"]
            atype = asset["type"]
            merge_strategy = asset.get("merge")
            src = pkg_root / rel
            dst = target.path / rel

            if args.skip_skills and rel == "skills":
                rep.add(f"file:{rel}", {"action": "excluded via --skip-skills"})
                continue
            if args.skip_configs and rel in ("settings.json", "mcp.json", "models.json"):
                rep.add(f"file:{rel}", {"action": "excluded via --skip-configs"})
                continue

            if atype == "dir-of-dirs":
                if args.dry_run:
                    counts = _dryrun_dir_of_dirs(src, dst, asset.get("skip_indices", []))
                    rep.add(f"file:{rel}", counts)
                    continue
                result = fs.merge_skills_dir(
                    src, dst, overwrite=args.overwrite,
                    skip_indices=asset.get("skip_indices", []),
                )
                rep.add(
                    f"file:{rel}",
                    {
                        "action": "merged",
                        "created": len(result["created"]),
                        "skipped": len(result["skipped"]),
                        "overwritten": len(result["overwritten"]),
                        "created_names": result["created"],
                        "skipped_names": result["skipped"],
                    },
                )
            elif atype == "json":
                if not src.is_file():
                    rep.add(f"file:{rel}", {"action": "skipped", "reason": "src absent"})
                    continue
                if dst.exists() and not args.dry_run:
                    bak = fs.backup(dst, ts)
                    if bak:
                        rep.add_backup(bak)
                if args.dry_run:
                    rep.add(
                        f"file:{rel}",
                        {"action": "would-merge", "strategy": merge_strategy},
                    )
                    continue
                if merge_strategy == "shallow-target-wins":
                    rep.add(f"file:{rel}", configs.shallow_target_wins(src, dst, overwrite=args.overwrite))
                elif merge_strategy == "mcp-servers-by-name":
                    rep.add(f"file:{rel}", configs.merge_mcp_servers(src, dst, overwrite=args.overwrite))
                elif merge_strategy == "list-by-id":
                    rep.add(
                        f"file:{rel}",
                        configs.merge_list_by_id(
                            src, dst,
                            list_field=asset.get("list_field", "items"),
                            id_field=asset.get("id_field", "id"),
                            overwrite=args.overwrite,
                        ),
                    )
                else:
                    rep.add(f"file:{rel}", {"action": "skipped", "reason": "unknown strategy"})
            elif atype == "file" and merge_strategy == "imported-suffix":
                if not src.is_file():
                    continue
                if dst.exists() and not args.dry_run:
                    bak = fs.backup(dst, ts)
                    if bak:
                        rep.add_backup(bak)
                if args.dry_run:
                    rep.add(
                        f"file:{rel}",
                        {
                            "action": "would-keep-target+write-imported" if dst.exists() else "would-create",
                        },
                    )
                    continue
                action = fs.merge_identity_file(src, dst, overwrite=args.overwrite)
                rep.add(f"file:{rel}", {"action": action})

        memory_export = pkg_root / "memory-export.md"
        if memory_export.is_file():
            rep.add(
                "memory_export",
                {
                    "action": "reference-only",
                    "path": "memory-export.md",
                    "note": "not imported; sync Memory in client settings on the target side",
                },
            )
            rep.note(
                "Package contains memory-export.md for reference only. "
                "Memory is cloud-synced and is not written to local memory files."
            )

        # ---- Connectors ----
        for asset in inventory["warned_assets"]:
            rel = asset["path"]
            src = pkg_root / rel
            dst = target.path / rel
            if not src.is_dir():
                rep.add(f"connectors:{rel}", {"action": "skipped"})
                continue
            if args.dry_run:
                uids = sorted([p.name for p in src.iterdir() if p.is_dir()])
                rep.add(
                    f"connectors:{rel}",
                    {"action": "would-merge", "uids": uids, "no_credentials": args.no_credentials},
                )
                continue
            # Top-level files (e.g. mcp.json) via shallow merge if json
            for child in src.iterdir():
                if child.is_file() and child.suffix == ".json":
                    if (dst / child.name).exists():
                        bak = fs.backup(dst / child.name, ts)
                        if bak:
                            rep.add_backup(bak)
                    configs.shallow_target_wins(child, dst / child.name, overwrite=args.overwrite)
            result = fs.merge_connectors_dir(
                src, dst,
                overwrite=args.overwrite,
                no_credentials=args.no_credentials,
                credentials_files=asset.get("credentials_files", []),
                uid_map=uid_map,
            )
            rep.add(f"connectors:{rel}", {"action": "merged", **result})
            if asset.get("warn") and not args.no_credentials:
                rep.warn(asset["warn"])

        # ---- Conversations ----
        if args.no_conversations or not meta.options.get("conversations", True):
            rep.add("conversations", {"action": "excluded"})
        else:
            convo = inventory["conversations"]
            src_projects = pkg_root / convo["path"]
            dst_projects = target.path / convo["path"]
            if args.dry_run:
                count = len(fs.list_session_jsonls(src_projects))
                rep.add("conversations", {"action": "would-merge", "jsonl_count": count})
            else:
                result = fs.merge_projects_dir(
                    src_projects, dst_projects, overwrite=args.overwrite
                )
                rep.add("conversations", {"action": "merged", **result})

        # ---- Cross-machine: rewrite paths in DB + meta.json + JSON configs ----
        if mapper is not None and mapper.rules and not args.dry_run:
            target_db = target.path / "workbuddy.db"
            path_rewrite_spec = inventory.get("path_rewrite", {})
            db_cols = path_rewrite_spec.get("db_columns", [])
            if target_db.exists() and db_cols:
                try:
                    rewrite_conn = sqlite3.connect(str(target_db), timeout=5.0)
                    try:
                        rw_result = DB.rewrite_path_columns(
                            rewrite_conn, "main", db_cols, mapper
                        )
                        rep.add("path_rewrite_db", rw_result)
                    finally:
                        rewrite_conn.close()
                except sqlite3.Error as e:
                    rep.warn(f"DB path rewrite failed: {e}")

            # Rename projects/<oldId>/ dirs based on rewritten cwd
            target_projects = target.path / "projects"
            if target_projects.is_dir():
                rename_result = fs.rename_project_dirs(target_projects, mapper)
                rep.add("path_rewrite_projects", {
                    "renamed": len(rename_result["renamed"]),
                    "cwd_updated": len(rename_result["cwd_updated"]),
                    "skipped": rename_result["skipped"][:5],
                    "rename_sample": rename_result["renamed"][:5],
                })

            # Rewrite JSON file fields (settings.json, mcp.json, etc.)
            json_specs = path_rewrite_spec.get("files", [])
            json_results: List[Dict] = []
            for spec in json_specs:
                file_glob = spec["path"]
                for fp in target.path.glob(file_glob):
                    if not fp.is_file():
                        continue
                    rj = configs.rewrite_paths_in_json(fp, spec, mapper)
                    if rj.get("rewritten"):
                        json_results.append({"file": str(fp.relative_to(target.path)), **rj})
            if json_results:
                rep.add("path_rewrite_json", json_results)

            # After path rewrite, ensure workspace directories exist on disk
            # so that WorkBuddy can open the imported conversations.
            ws_dir_result = _ensure_workspace_dirs(target_db, args.dry_run)
            if ws_dir_result["created"] or ws_dir_result["errors"]:
                rep.add("ensure_workspace_dirs", ws_dir_result)

            # Clean up leftover source-prefixed project dirs that weren't
            # renamed during the initial pass (e.g. dirs without meta.json).
            if target_projects.is_dir():
                cleanup_result = _cleanup_leftover_project_dirs(
                    target_projects, mapper, args.dry_run
                )
                if (
                    cleanup_result["moved_files"]
                    or cleanup_result["renamed_dirs"]
                    or cleanup_result["errors"]
                ):
                    rep.add("project_dir_cleanup", cleanup_result)

        # ---- Workspace bundle extraction ----
        if args.workspaces_package and not args.dry_run:
            bundle_path = Path(args.workspaces_package).expanduser()
            if not bundle_path.exists():
                rep.warn(f"Workspace bundle not found: {bundle_path}")
            else:
                dest_root = Path(
                    args.workspace_destination or Path.home() / "wb-imported-workspaces"
                ).expanduser()
                dest_root.mkdir(parents=True, exist_ok=True)
                ws_result = fs.extract_workspace_bundle(
                    bundle_path, dest_root, mapper, overwrite=args.overwrite
                )
                rep.add("workspaces", {
                    "action": "extracted",
                    "count": len(ws_result["workspaces"]),
                    "files_written": sum(w.get("files_written", 0) for w in ws_result["workspaces"]),
                    "skipped_existing": sum(w.get("skipped_existing", 0) for w in ws_result["workspaces"]),
                    "errors": ws_result["errors"][:5],
                    "destinations_sample": [
                        w["destination"] for w in ws_result["workspaces"][:5]
                    ],
                })

    # ---- Finalize ----
    rep.finish()

    # Determine if restart is required (any of the always-restart resources changed)
    restart_spec = inventory.get("restart_required", {})
    needs_restart = _needs_restart(rep, restart_spec)
    if not args.dry_run:
        report_dir = target.path / "migration-reports"
        report_path = report_dir / f"import-{fs.make_ts()}.json"
        # Attach restart metadata to the report before writing
        rep.add("restart_required", needs_restart)
        rep.add("uid_mapping", uid_map if uid_map else "none")
        rep.write(report_path)
        rep.note(f"Report saved: {report_path}")

    R.print_report(rep)

    # Print restart hint to stdout (separate from report so it's always visible)
    if needs_restart["required"]:
        print()
        print("=" * 60)
        print("✓ 导入完成。请重启 WorkBuddy 客户端使改动生效。")
        print()
        print(f"重启后生效：{', '.join(needs_restart['restart_reasons'])}")
        if needs_restart["hot_reloaded"]:
            print(f"已热加载（不用重启）：{', '.join(needs_restart['hot_reloaded'])}")
        if uid_map:
            print()
            print(f"uid 自动映射：{uid_map}")
        print()
        print("提示：直接关闭并重新打开 WorkBuddy 即可，无需退出账号。")
        print("=" * 60)

    return 0


def _needs_restart(rep, restart_spec: dict) -> dict:
    """Inspect what was actually touched in this import and decide if restart is needed."""
    touched: List[str] = list(rep.sections.keys())
    restart_after = restart_spec.get("restart_after_any_of", []) or []
    hot_reloaded_spec = restart_spec.get("hot_reloaded", []) or []
    reasons: List[str] = []
    hot: List[str] = []
    for t in touched:
        # t is like 'db', 'file:settings.json', 'file:IDENTITY.md', etc.
        bare = t.split(":", 1)[1] if ":" in t else t
        for trigger in restart_after:
            if trigger == bare or (trigger.endswith("/*") and bare.startswith(trigger[:-1])):
                reasons.append(bare)
                break
        for hot_trigger in hot_reloaded_spec:
            if hot_trigger == bare or (hot_trigger.endswith("/*") and bare.startswith(hot_trigger[:-1])):
                hot.append(bare)
                break
    # Dedup while preserving order
    seen: Set[str] = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    seen = set()
    hot = [h for h in hot if not (h in seen or seen.add(h))]
    return {
        "required": bool(reasons),
        "restart_reasons": reasons,
        "hot_reloaded": hot,
    }


# --- helpers ---

def _merge_db(
    target_db: Path,
    src_db: Path,
    tables: list,
    *,
    overwrite: bool,
    uid_map: Dict[str, str],
) -> dict:
    """Apply ATTACH-based merge. Returns section dict."""
    target_db.parent.mkdir(parents=True, exist_ok=True)
    # If target_db doesn't exist, copy src as initial (no merge needed)
    if not target_db.exists():
        shutil.copy2(src_db, target_db)
        # Apply uid_map rewrite in place if needed
        if uid_map:
            conn = sqlite3.connect(str(target_db))
            try:
                for src_uid, dst_uid in uid_map.items():
                    conn.execute(
                        "UPDATE sessions SET user_id = ? WHERE user_id = ?",
                        (dst_uid, src_uid),
                    )
                conn.commit()
            finally:
                conn.close()
        return {"action": "initialized", "reason": "target db absent"}

    # Try to lock target db
    try:
        lock_conn = DB.acquire_write_lock(target_db)
        lock_conn.execute("ROLLBACK")  # release immediate, keep connection
    except BlockingIOError as e:
        raise SystemExit(f"[error] {e}\nexit code: 2") from e

    conn = lock_conn
    try:
        conn.execute("ATTACH DATABASE ? AS src", (str(src_db),))
        section: dict = {"action": "merged", "tables": {}, "orphan_runs_dropped": 0}

        # Snapshot for sessions.deleted_at protection (only if overwrite)
        deleted_at_snapshot: dict = {}
        if overwrite:
            deleted_at_snapshot = DB.protect_sessions_deleted_at(conn, "main")

        for t in tables:
            name = t["name"]
            extra_where = ""
            if name == "automation_runs":
                # Drop orphans
                orphan = DB.count_orphan_runs(conn, "src", "main")
                section["orphan_runs_dropped"] = orphan
                extra_where = (
                    "automation_id IN (SELECT id FROM main.automations) "
                    "OR automation_id IN (SELECT id FROM src.automations)"
                )
            if t.get("has_deleted_at"):
                extra_where = (
                    f"({extra_where}) AND deleted_at IS NULL"
                    if extra_where
                    else "deleted_at IS NULL"
                )
            # Defensive: also skip in-flight sessions on import side, in case
            # the package was built by an older tool that didn't filter.
            ex_status = t.get("exclude_status") or []
            if ex_status:
                in_list = ", ".join(DB.sqlite3_literal(s) for s in ex_status)
                clause = f"status NOT IN ({in_list})"
                extra_where = f"({extra_where}) AND {clause}" if extra_where else clause
                # Count what we're defensively skipping
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM src.{name} WHERE status IN ({in_list})"
                )
                defensive_skip = cur.fetchone()[0]
                if defensive_skip:
                    section.setdefault("defensive_in_flight_skipped", {})[name] = defensive_skip

            inserted, skipped = DB.merge_table(
                conn,
                target_schema="main",
                source_schema="src",
                table=name,
                overwrite=overwrite,
                extra_where=extra_where,
                transform_user_id=uid_map or None,
            )
            section["tables"][name] = {"inserted": inserted, "skipped_or_replaced": skipped}

        if overwrite and deleted_at_snapshot:
            restored = DB.restore_sessions_deleted_at(conn, "main", deleted_at_snapshot)
            section["sessions_deleted_at_restored"] = restored

        conn.commit()
        conn.execute("DETACH DATABASE src")
        return section
    finally:
        conn.close()


def _dryrun_db(target_db: Path, src_db: Path, tables: list) -> dict:
    out = {"action": "would-merge", "tables": {}}
    if not target_db.exists():
        out["note"] = "target db absent → would initialize from package"
        return out
    src_conn = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    try:
        for t in tables:
            name = t["name"]
            try:
                cur = src_conn.execute(f"SELECT COUNT(*) FROM {name}")
                src_rows = cur.fetchone()[0]
            except sqlite3.Error:
                src_rows = 0
            out["tables"][name] = {"src_rows": src_rows}
    finally:
        src_conn.close()
    return out


def _dryrun_dir_of_dirs(src: Path, dst: Path, skip_indices: list) -> dict:
    if not src.is_dir():
        return {"action": "skipped", "reason": "src absent"}
    src_names = [p.name for p in src.iterdir() if p.is_dir() and p.name not in skip_indices]
    dst_names = set(p.name for p in dst.iterdir() if p.is_dir()) if dst.is_dir() else set()
    would_create = [n for n in src_names if n not in dst_names]
    would_skip = [n for n in src_names if n in dst_names]
    return {
        "action": "would-merge",
        "would_create": would_create,
        "would_skip": would_skip,
    }


def _ensure_workspace_dirs(target_db: Path, dry_run: bool) -> dict:
    """Create any workspace directories referenced by sessions that don't exist on disk.

    After cross-machine import, session cwds point to mapped paths that may not
    exist yet. Without these directories, WorkBuddy cannot open the conversations.
    """
    result: dict = {"created": [], "existing": 0, "errors": []}
    conn = sqlite3.connect(str(target_db))
    try:
        cur = conn.execute(
            "SELECT DISTINCT cwd FROM sessions WHERE deleted_at IS NULL AND cwd IS NOT NULL"
        )
        cwds = [row[0] for row in cur if row[0]]
    finally:
        conn.close()

    for cwd in cwds:
        cwd_path = Path(cwd)
        if cwd_path.is_dir():
            result["existing"] += 1
            continue
        if dry_run:
            result["created"].append(cwd)
        else:
            try:
                cwd_path.mkdir(parents=True, exist_ok=True)
                result["created"].append(cwd)
            except OSError as e:
                result["errors"].append({"cwd": cwd, "error": str(e)})
    return result


def _cleanup_leftover_project_dirs(
    projects_root: Path, mapper, dry_run: bool
) -> dict:
    """After path rewrite, scan for leftover source-prefixed project dirs.

    Some dirs may not have been renamed during the initial pass (e.g. missing
    meta.json). This post-pass moves their JSONL files to the corresponding
    target-prefixed dir or renames the dir directly.
    """
    from scripts.lib.pathmap import compress_workspace_path, decompress_workspace_path

    result = {"moved_files": 0, "renamed_dirs": [], "deleted_dirs": 0, "errors": []}
    if not projects_root.is_dir():
        return result

    # Walk existing dirs and find orphans
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue
        dir_name = project_dir.name

        # Try to reverse-engineer the original cwd from the dir name
        reconstructed = decompress_workspace_path(dir_name)
        if not reconstructed:
            continue

        rewritten = mapper.rewrite(reconstructed)
        if not rewritten:
            continue

        new_project_id = compress_workspace_path(rewritten.new_path)
        if new_project_id == dir_name:
            continue  # Already correct

        new_dir = projects_root / new_project_id
        if not new_dir.exists():
            # Target dir doesn't exist: just rename
            if not dry_run:
                try:
                    project_dir.rename(new_dir)
                    result["renamed_dirs"].append(
                        {"from": dir_name, "to": new_project_id}
                    )
                except OSError as e:
                    result["errors"].append(f"rename {dir_name}: {e}")
            else:
                result["renamed_dirs"].append(
                    {"from": dir_name, "to": new_project_id}
                )
        else:
            # Both exist: move files from old to new, then delete old
            if not dry_run:
                moved = 0
                for child in project_dir.rglob("*"):
                    if not child.is_file():
                        continue
                    rel = child.relative_to(project_dir)
                    dst = new_dir / rel
                    if dst.exists():
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.move(str(child), str(dst))
                        moved += 1
                    except OSError:
                        pass
                result["moved_files"] += moved
                if moved > 0:
                    # Try to delete old dir if empty
                    try:
                        _rmtree_if_empty(project_dir)
                        result["deleted_dirs"] += 1
                    except OSError:
                        pass
            else:
                result["moved_files"] += len(
                    list(project_dir.rglob("*.jsonl"))
                )

    return result


def _rmtree_if_empty(d: Path) -> None:
    """Remove a directory tree if it contains no files."""
    has_files = False
    for root, dirs, files in os.walk(d):
        if files:
            has_files = True
            break
    if not has_files:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
