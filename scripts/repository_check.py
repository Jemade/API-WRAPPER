"""Check tracked repository hygiene and required contributor documentation.

This is a bounded pattern scan, not a security certification or history scan.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/ENGINEERING.md",
    "docs/REVIEW_CHECKLIST.md",
    ".gitignore",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
)
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{50,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"(?m)^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----$"),
)


def main():
    errors = ["Missing " + name for name in REQUIRED if not (ROOT / name).is_file()]
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, tracked):
        path = Path(name)
        if (
            any(part in {".venv", "venv", "node_modules", "__pycache__"} for part in path.parts)
            or path.name == ".env"
            or path.suffix in {".pyc", ".db", ".sqlite", ".sqlite3"}
        ):
            errors.append("Runtime or private file tracked: " + name)
        file = ROOT / name
        if not file.is_file() or file.stat().st_size > 1_000_000:
            continue
        try:
            content = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            errors.append("Possible credential in " + name + "; inspect privately")
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(
        "Required documentation and tracked-file checks passed. "
        "Pattern scan found no matching credentials; "
        "history and other credential formats are outside this check."
    )


if __name__ == "__main__":
    main()
