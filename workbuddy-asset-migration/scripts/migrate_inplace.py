#!/usr/bin/env python3
"""Same-machine inplace migration between WorkBuddy CN and Intl editions.

When both ~/.workbuddy/ (CN) and ~/.workbuddy-ai/ (Intl) exist on the same
machine, there is no need to export → zip → transfer → unzip → import.
Workspace files are already on the same disk; only metadata (DB rows, config
files, skills, identity files) need to be copied from source root to target
root.

This script performs a direct copy, reusing the same merge semantics as
import.py (INSERT OR IGNORE, skip-if-exists for skills, imported-suffix for
identity, etc.), but skips zip packaging entirely. Memory is cloud-synced and
is not migrated by editing local memory files.

Created & maintained by Glen Wei (韦其像)
Email: glen.keeming@gmail.com
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
from __future__ import annotations

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | Email: glen.keeming@gmail.com | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib import detect, manifest as M, db as DB, fs, configs, report as R


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


def _copy_file_assets(src_root, dst_root: Path, file_assets: list, rep, uid_map: dict) -> None:
    """Copy file assets from src_root to dst_root using same logic as export+import combined."""
    for asset in file_assets:
        rel = asset["path"]
        atype = asset["type"]
        merge_strategy = asset.get("merge")
        src = src_root.path / rel
        dst = dst_root / rel

        if atype == "dir-of-dirs":
            if not src.is_dir():
                continue
            skip = asset.get("skip_indices", [])
            result = fs.merge_skills_dir(
                src, dst, overwrite=False, skip_indices=skip
            )
            rep.add(
                f"file:{rel}",
                {
                    "action": "merged",
                    "created": len(result["created"]),
                    "skipped": len(result["skipped"]),
                    "created_names": result["created"],
                    "skipped_names": result["skipped"],
                },
            )
        elif atype == "json":
            if not src.is_file():
                rep.add(f"file:{rel}", {"action": "skipped", "reason": "src absent"})
                continue
            # Backup target before merging
            ts = fs.make_ts()
            if dst.exists():
                bak = fs.backup(dst, ts)
                if bak:
                    rep.add_backup(bak)
            if merge_strategy == "shallow-target-wins":
                rep.add(f"file:{rel}", configs.shallow_target_wins(src, dst, overwrite=False))
            elif merge_strategy == "mcp-servers-by-name":
                rep.add(f"file:{rel}", configs.merge_mcp_servers(src, dst, overwrite=False))
            elif merge_strategy == "list-by-id":
                rep.add(
                    f"file:{rel}",
                    configs.merge_list_by_id(
                        src, dst,
                        list_field=asset.get("list_field", "items"),
                        id_field=asset.get("id_field", "id"),
                        overwrite=False,
                    ),
                )
        elif atype == "file" and merge_strategy == "imported-suffix":
            if not src.is_file():
                continue
            action = fs.merge_identity_file(src, dst, overwrite=False)
            rep.add(f"file:{rel}", {"action": action})


def _merge_warned_assets(src_root, dst_root: Path, warned_assets: list,
                         no_credentials: bool, rep, uid_map: dict) -> None:
    """Copy connectors from source to target."""
    for asset in warned_assets:
        rel = asset["path"]
        src = src_root.path / rel
        dst = dst_root / rel
        if not src.is_dir():
            rep.add(f"connectors:{rel}", {"action": "skipped"})
            continue
        # Top-level json files via shallow merge
        for child in src.iterdir():
            if child.is_file() and child.suffix == ".json":
                if (dst / child.name).exists():
                    ts = fs.make_ts()
                    bak = fs.backup(dst / child.name, ts)
                    if bak:
                        rep.add_backup(bak)
                configs.shallow_target_wins(child, dst / child.name, overwrite=False)
        result = fs.merge_connectors_dir(
            src, dst,
            overwrite=False,
            no_credentials=no_credentials,
            credentials_files=asset.get("credentials_files", []),
            uid_map=uid_map,
        )
        rep.add(f"connectors:{rel}", {"action": "merged", **result})
        if asset.get("warn") and not no_credentials:
            rep.warn(asset["warn"])


def _copy_conversations(src_root, dst_root: Path, rep) -> None:
    """Copy projects/ (conversation jsonl + meta.json) from src to dst."""
    src_projects = src_root.path / "projects"
    dst_projects = dst_root / "projects"
    if not src_projects.is_dir():
        rep.add("conversations", {"action": "skipped", "reason": "src absent"})
        return
    result = fs.merge_projects_dir(src_projects, dst_projects, overwrite=False)
    rep.add("conversations", {"action": "merged", **result})


def _merge_db(src_root, dst_root: Path, db_tables: list, uid_map: Dict[str, str],
              rep, dry_run: bool, exclude_session_ids: Optional[List[str]] = None) -> None:
    """Merge source DB into target DB using ATTACH, same as import.py."""
    target_db = dst_root / "workbuddy.db"
    src_db = src_root.path / "workbuddy.db"

    if not src_db.is_file():
        rep.add("db", {"action": "skipped", "reason": "source db absent"})
        return

    if not target_db.exists():
        # Simplest case: just copy the whole file
        if not dry_run:
            target_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_db, target_db)
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
        rep.add("db", {"action": "initialized", "reason": "target db absent"})
        return

    if dry_run:
        # Count source rows but don't write
        src_conn = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
        try:
            out = {"action": "would-merge", "tables": {}}
            for t in db_tables:
                name = t["name"]
                try:
                    cur = src_conn.execute(f"SELECT COUNT(*) FROM {name}")
                    out["tables"][name] = {"src_rows": cur.fetchone()[0]}
                except sqlite3.Error:
                    out["tables"][name] = {"src_rows": 0}
            rep.add("db", out)
        finally:
            src_conn.close()
        return

    # Actual merge
    ts = fs.make_ts()
    bak = fs.backup(target_db, ts)
    if bak:
        rep.add_backup(bak)

    try:
        lock_conn = DB.acquire_write_lock(target_db)
        lock_conn.execute("ROLLBACK")
    except BlockingIOError as e:
        raise SystemExit(f"[error] {e}\nexit code: 2") from e

    conn = lock_conn
    try:
        conn.execute("ATTACH DATABASE ? AS src", (str(src_db),))
        section: dict = {"action": "merged", "tables": {}, "orphan_runs_dropped": 0}
        for t in db_tables:
            name = t["name"]
            extra_where = ""
            if name == "automation_runs":
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
            ex_status = t.get("exclude_status") or []
            if ex_status:
                in_list = ", ".join(DB.sqlite3_literal(s) for s in ex_status)
                clause = f"status NOT IN ({in_list})"
                extra_where = f"({extra_where}) AND {clause}" if extra_where else clause

            # Exclude self session (the one running migration)
            if t.get("exclude_self_session") and exclude_session_ids:
                placeholders = ",".join(DB.sqlite3_literal(s) for s in exclude_session_ids)
                clause = f"id NOT IN ({placeholders})"
                extra_where = f"({extra_where}) AND {clause}" if extra_where else clause
                # Count defensively
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM src.{name} WHERE id IN ({placeholders})"
                )
                defensive_skip = cur.fetchone()[0]
                if defensive_skip:
                    section.setdefault("defensive_self_session_skipped", {})[name] = defensive_skip

            inserted, skipped = DB.merge_table(
                conn,
                target_schema="main",
                source_schema="src",
                table=name,
                overwrite=False,
                extra_where=extra_where,
                transform_user_id=uid_map or None,
            )
            section["tables"][name] = {"inserted": inserted, "skipped_or_replaced": skipped}
        conn.commit()
        conn.execute("DETACH DATABASE src")
        rep.add("db", section)
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Same-machine inplace migration (CN <-> Intl). "
                    "Both roots must be on the same disk.",
        epilog=AUTHOR_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        )
    ap.add_argument("--source", required=True,
                    help="Source root directory (e.g. ~/.workbuddy or ~/.workbuddy-ai)")
    ap.add_argument("--target", required=True,
                    help="Target root directory")
    ap.add_argument("--no-conversations", action="store_true")
    ap.add_argument("--no-credentials", action="store_true")
    ap.add_argument("--skip-db", action="store_true")
    ap.add_argument("--skip-skills", action="store_true")
    ap.add_argument("--skip-configs", action="store_true")
    ap.add_argument("--exclude-session-id", action="append", default=None,
                    help="Session ID(s) to exclude from migration (current session). May repeat.")
    ap.add_argument("--uid-map", action="append", default=None, help="src=dst (may repeat)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan only — no files are written")
    ap.add_argument(
        "--inventory",
        default=str(_HERE.parent / "references" / "asset_inventory.md"),
        help="Path to asset_inventory.md",
    )
    args = ap.parse_args()

    # Build exclude_session_ids from CLI args + environment
    exclude_session_ids = args.exclude_session_id or []
    for env_var in ("WORKBUDDY_CURRENT_SESSION_ID", "CODEBUDDY_SESSION_ID"):
        v = os.environ.get(env_var)
        if v and v not in exclude_session_ids:
            exclude_session_ids.append(v)

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    rep = R.Report(mode="inplace-migrate", dry_run=args.dry_run, overwrite=False)
    rep.start()
    inventory = M.load_inventory(Path(args.inventory))
    uid_map = _parse_uid_map(args.uid_map)

    # Resolve source root
    src_path = Path(args.source).expanduser()
    if not src_path.is_dir():
        print(f"[error] Source root does not exist: {src_path}", file=sys.stderr)
        return 1
    src_root = detect.RootInfo(path=src_path, variant=detect._classify(src_path), exists=True)
    rep.source = str(src_root.path)
    rep.note(f"Source: {src_root.path} (variant={src_root.variant})")

    # Resolve target root
    dst_path = Path(args.target).expanduser()
    dst_path.mkdir(parents=True, exist_ok=True)
    dst_variant = detect._classify(dst_path)
    rep.target = str(dst_path)
    rep.note(f"Target: {dst_path} (variant={dst_variant})")

    # Sanity check: source != target
    if src_root.path.resolve() == dst_path.resolve():
        print("[error] Source and target are the same directory.", file=sys.stderr)
        return 1

    # Sanity check: same machine (both directories are local)
    # (This script is only intended for same-machine use, but we verify)

    # ---- UID resolution ----
    # CN and Intl editions use different account systems, so user_id mismatch
    # is expected and normal. We must map every source uid to a target uid so
    # the imported data is visible to the currently logged-in account on the
    # target side.  If we cannot determine the target uid, the imported rows
    # would keep the source uid (via the ELSE branch in DB.merge_table's CASE
    # expression) and be invisible — block and ask the user to resolve.
    target_uids = detect.extract_user_ids(dst_path / "workbuddy.db")
    target_primary = target_uids[0][0] if target_uids else None
    source_uids_all = [u for u, _ in detect.extract_user_ids(src_root.db_path)]

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
            "Then re-run migration.\n"
            "    2. Provide --uid-map <source_uid>=<target_uid> explicitly.\n"
            "\n"
            f"  Source uid(s): {', '.join(source_uids_all)}",
            file=sys.stderr,
        )
        return 1

    # Resolve uid_map: user-provided --uid-map overrides take precedence;
    # any source uid not yet mapped defaults to target_primary.
    if target_primary:
        for u in unmapped_src:
            uid_map[u] = target_primary

    rep.note(f"uid mapping: {uid_map if uid_map else 'none (no source uids)'}")

    # ---- Read-only dry-run plan ----
    if args.dry_run:
        plan = _build_dry_run_plan(
            src_root=src_root,
            dst_path=dst_path,
            inventory=inventory,
            uid_map=uid_map,
            source_uids_all=source_uids_all,
            target_primary=target_primary,
            no_conversations=args.no_conversations,
            no_credentials=args.no_credentials,
            exclude_session_ids=exclude_session_ids or [],
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    # ---- Actual migration ----

    # DB merge
    if not args.skip_db:
        _merge_db(src_root, dst_path, inventory["db_tables"], uid_map, rep, dry_run=False,
                  exclude_session_ids=exclude_session_ids or [])
    else:
        rep.add("db", {"action": "excluded via --skip-db"})

    # File assets
    selected_file_assets = []
    for asset in inventory["file_assets"]:
        rel = asset["path"]
        if args.skip_skills and rel == "skills":
            rep.add(f"file:{rel}", {"action": "excluded via --skip-skills"})
            continue
        if args.skip_configs and rel in ("settings.json", "mcp.json", "models.json"):
            rep.add(f"file:{rel}", {"action": "excluded via --skip-configs"})
            continue
        selected_file_assets.append(asset)
    _copy_file_assets(src_root, dst_path, selected_file_assets, rep, uid_map)

    # Memory is cloud-synced and is not migrated by writing local files.
    rep.add("memory", {"action": "skipped", "reason": "cloud-synced; sync in client settings"})

    # Connectors
    _merge_warned_assets(
        src_root, dst_path, inventory["warned_assets"],
        args.no_credentials, rep, uid_map,
    )

    # Conversations
    if args.no_conversations:
        rep.add("conversations", {"action": "excluded"})
    else:
        _copy_conversations(src_root, dst_path, rep)

    # ---- Finalize ----
    rep.finish()
    restart_spec = inventory.get("restart_required", {})
    needs_restart = _needs_restart(rep, restart_spec)
    rep.add("restart_required", needs_restart)
    rep.add("uid_mapping", uid_map if uid_map else "none")

    report_dir = dst_path / "migration-reports"
    report_path = report_dir / f"inplace-{fs.make_ts()}.json"
    rep.write(report_path)
    rep.note(f"Report saved: {report_path}")

    R.print_report(rep)

    if needs_restart["required"]:
        print()
        print("=" * 60)
        print("✓ 同机迁移完成。请重启 WorkBuddy 客户端使改动生效。")
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
    """Same logic as import.py."""
    touched: List[str] = list(rep.sections.keys())
    restart_after = restart_spec.get("restart_after_any_of", []) or []
    hot_reloaded_spec = restart_spec.get("hot_reloaded", []) or []
    reasons: List[str] = []
    hot: List[str] = []
    for t in touched:
        bare = t.split(":", 1)[1] if ":" in t else t
        for trigger in restart_after:
            if trigger == bare or (trigger.endswith("/*") and bare.startswith(trigger[:-1])):
                reasons.append(bare)
                break
        for hot_trigger in hot_reloaded_spec:
            if hot_trigger == bare or (hot_trigger.endswith("/*") and bare.startswith(hot_trigger[:-1])):
                hot.append(bare)
                break
    seen: set = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    seen = set()
    hot = [h for h in hot if not (h in seen or seen.add(h))]
    return {
        "required": bool(reasons),
        "restart_reasons": reasons,
        "hot_reloaded": hot,
    }


def _build_dry_run_plan(
    *, src_root, dst_path: Path, inventory: dict,
    uid_map: Dict[str, str], source_uids_all: List[str],
    target_primary: Optional[str],
    no_conversations: bool, no_credentials: bool,
    exclude_session_ids: Optional[List[str]] = None,
) -> dict:
    """Build a read-only JSON plan for --dry-run."""
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
        main_summary["memory_local_files_present"] = [
            {"uid": p.stem.rsplit("_memory", 1)[0], "file": p.name, "bytes": p.stat().st_size}
            for p in memory_dir.glob("*_memory.md")
        ]
        main_summary["memory_migration"] = "skipped; Memory is cloud-synced and should be synced in client settings"

    # DB row counts
    if src_root.db_path.is_file():
        try:
            conn = sqlite3.connect(f"file:{src_root.db_path}?mode=ro", uri=True)
            db_counts: Dict[str, int] = {}
            db_excluded_by_self_session: Dict[str, int] = {}
            for t in inventory["db_tables"]:
                try:
                    cur = conn.execute(f"SELECT COUNT(*) FROM {t['name']}")
                    db_counts[t["name"]] = cur.fetchone()[0]
                except sqlite3.Error:
                    db_counts[t["name"]] = 0
                # Count rows that would be excluded by exclude_self_session
                if t.get("exclude_self_session") and exclude_session_ids:
                    try:
                        placeholders = ",".join(DB.sqlite3_literal(s) for s in exclude_session_ids)
                        cur = conn.execute(
                            f"SELECT COUNT(*) FROM {t['name']} WHERE id IN ({placeholders})"
                        )
                        db_excluded_by_self_session[t["name"]] = cur.fetchone()[0]
                    except sqlite3.Error:
                        db_excluded_by_self_session[t["name"]] = 0
            main_summary["db_table_row_counts"] = db_counts
            if db_excluded_by_self_session:
                main_summary["db_table_excluded_by_self_session"] = db_excluded_by_self_session
            conn.close()
        except sqlite3.Error:
            pass

    # Target existing data summary
    target_summary: Dict[str, object] = {}
    target_db = dst_path / "workbuddy.db"
    if target_db.is_file():
        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            target_counts: Dict[str, int] = {}
            for t in inventory["db_tables"]:
                try:
                    cur = conn.execute(f"SELECT COUNT(*) FROM {t['name']}")
                    target_counts[t["name"]] = cur.fetchone()[0]
                except sqlite3.Error:
                    target_counts[t["name"]] = 0
            target_summary["db_table_row_counts"] = target_counts
            conn.close()
        except sqlite3.Error:
            pass
    target_skills_dir = dst_path / "skills"
    if target_skills_dir.is_dir():
        target_summary["skills_count"] = sum(
            1 for p in target_skills_dir.iterdir() if p.is_dir()
        )

    return {
        "kind": "inplace-migrate-plan",
        "mode": "same-machine-cn-intl",
        "source": {
            "root": str(src_root.path),
            "variant": src_root.variant,
        },
        "target": {
            "root": str(dst_path),
            "variant": detect._classify(dst_path),
        },
        "uid_map": uid_map if uid_map else "auto",
        "source_data": main_summary,
        "target_existing": target_summary,
        "options": {
            "conversations": not no_conversations,
            "credentials": not no_credentials,
        },
        "notes": [
            "同机迁移不打包 zip，直接复制数据到目标目录",
            "DB 使用 INSERT OR IGNORE 合并，目标已有数据不会被覆盖",
            "Skills 同名目录会跳过",
            "Memory 不写入目标本地文件，请在客户端设置中同步",
            "Identity 文件目标已存在时写入 .imported.md",
            "导入完成后需重启 WorkBuddy 使改动生效",
        ],
    }


if __name__ == "__main__":
    sys.exit(main())
