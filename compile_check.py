#!/usr/bin/env python3
"""compile_check.py -- syntax-check the project without writing anything.

Compiles process_analyzer_allinone.py and every plugins/*.py IN MEMORY
(builtin compile()), so unlike `python -m py_compile` / `compileall` it never
creates __pycache__/ or .pyc files: the tree stays exactly as shipped.

Used by install.sh, install.ps1, build.sh, both .command launchers and CI,
so there is one definition of "the code compiles" instead of five.

Usage:
    python compile_check.py            # main script + plugins/*.py next to this file
    python compile_check.py a.py b.py  # explicit files
Exit code: 0 = everything compiles, 1 = at least one SyntaxError (each one
is printed as  path:line: message  on stderr).
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(HERE, "process_analyzer_allinone.py")
PLUGINS_DIR = os.path.join(HERE, "plugins")


def default_files():
    files = [MAIN_SCRIPT] if os.path.isfile(MAIN_SCRIPT) else []
    files += sorted(glob.glob(os.path.join(PLUGINS_DIR, "*.py")))
    return files


def main(argv):
    files = argv[1:] or default_files()
    if not files:
        print("compile_check: nothing to check (no main script, no plugins/*.py)", file=sys.stderr)
        return 1
    errors = 0
    for path in files:
        try:
            with open(path, "rb") as fh:
                compile(fh.read(), path, "exec")  # in-memory only
        except SyntaxError as exc:
            errors += 1
            print(f"  SYNTAX ERROR {path}:{exc.lineno}: {exc.msg}", file=sys.stderr)
        except OSError as exc:
            errors += 1
            print(f"  UNREADABLE {path}: {exc}", file=sys.stderr)
    n_plugins = sum(1 for f in files if os.path.dirname(os.path.abspath(f)) == PLUGINS_DIR)
    print(f"  compile check: {len(files) - errors}/{len(files)} files OK "
          f"({n_plugins} plugins, {len(files) - n_plugins} other)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
