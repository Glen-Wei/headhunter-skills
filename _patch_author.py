#!/usr/bin/env python3
"""Patch author watermark: fix single-quote argparse + add runtime print for non-argparse scripts."""
import re
from pathlib import Path

BASE = Path("/Users/glen/WorkBuddy/2026-08-10-18-20-29/github-skills")

EPILOG_TAIL = ", epilog=AUTHOR_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)"

def patch_argparse(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    changed = 0
    for i, line in enumerate(lines):
        if "ArgumentParser(" in line and "epilog" not in line:
            # single-line: ends with )
            if line.rstrip().endswith(")"):
                # find last ) and insert before it
                idx = line.rfind(")")
                lines[i] = line[:idx] + EPILOG_TAIL + line[idx:]
                changed += 1
            elif "ArgumentParser()" in line:
                lines[i] = line.replace("ArgumentParser()", f"ArgumentParser(description='CLI tool'{EPILOG_TAIL})")
                changed += 1
    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    print(f"{path.name}: argparse patched={changed}")

def patch_main_print(path: Path):
    """Insert author print at start of main() for scripts without argparse."""
    text = path.read_text(encoding="utf-8")
    if "AUTHOR_EPILOG" not in text:
        return
    # find 'def main():' and insert print after
    if text.count("def main():") == 1:
        m = re.search(r'def main\(\):\n', text)
        if m:
            insert = '    print(AUTHOR_EPILOG, file=sys.stderr)\n'
            if insert not in text:
                text = text[:m.end()] + insert + text[m.end():]
                path.write_text(text, encoding="utf-8")
                print(f"{path.name}: main() print inserted")
    else:
        print(f"{path.name}: main() pattern not unique, skip")

# 1. patch argparse single-quote forms
for f in sorted((BASE / "liepin-search" / "scripts").glob("*.py")):
    patch_argparse(f)

# 2. desktop scripts: no argparse -> print in main()
for f in sorted((BASE / "desktop-organizer" / "scripts").glob("*.py")):
    patch_main_print(f)

# 3. verify: compile all
print("=== compile check ===")
import subprocess, sys
r = subprocess.run([sys.executable, "-m", "py_compile",
    *(str(p) for p in (BASE / "liepin-search" / "scripts").glob("*.py")),
    *(str(p) for p in (BASE / "desktop-organizer" / "scripts").glob("*.py"))])
print("compile OK" if r.returncode == 0 else "compile FAILED")
