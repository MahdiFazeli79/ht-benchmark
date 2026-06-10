"""Fail-closed secret scanner (generation-unit pre-flight).

Encodes the Tier-3 guard rather than trusting vigilance (same philosophy as the
forbidden-key validator): scan files for known API-key prefixes and high-entropy
tokens, exit non-zero on any hit. Wired as a pre-commit check and in CI before
the repo ever holds an LLM API key.

Usage:
    htbench-scan-secrets <path> [<path> ...]      # scan files/dirs
    htbench-scan-secrets --staged                 # scan git-staged content
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

# Known key shapes (prefix-anchored, low false-positive).
_KEY_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style key (sk-...)"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "Anthropic key (sk-ant-...)"),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "Google API key (AIza...)"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "GitHub token (ghp_/gho_/...)"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id (AKIA...)"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token (xox...)"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key block"),
]

# Assignment to a secret-looking name with a long opaque value.
_ASSIGN = re.compile(
    r"""(?i)(api[_-]?key|secret|token|password|passwd|credential)\s*[:=]\s*['"]([^'"]{16,})['"]"""
)

# Skip binary/large/vendored content.
_SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".pdf", ".gz", ".zip", ".pkl", ".pyc", ".so", ".bin"}
_SKIP_DIR = {".git", "__pycache__", ".venv", "venv", "node_modules"}


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


# Explicit per-line escape hatch for legitimate fixtures/examples.
_ALLOWLIST = "pragma: allowlist secret"


def scan_text(text: str, label: str) -> list[str]:
    hits: list[str] = []
    for ln, line in enumerate(text.splitlines(), 1):
        if _ALLOWLIST in line:
            continue
        for pat, what in _KEY_PATTERNS:
            if pat.search(line):
                hits.append(f"{label}:{ln}: {what}")
        m = _ASSIGN.search(line)
        if m:
            val = m.group(2)
            # High-entropy opaque value assigned to a secret-looking name.
            if _shannon_entropy(val) >= 3.5 and not val.startswith(("$", "{{", "<")):
                hits.append(f"{label}:{ln}: high-entropy value assigned to {m.group(1)!r}")
    return hits


def _iter_files(paths):
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and not (set(f.parts) & _SKIP_DIR) and f.suffix.lower() not in _SKIP_SUFFIX:
                    yield f
        elif p.is_file():
            yield p


def scan_paths(paths) -> list[str]:
    hits: list[str] = []
    for f in _iter_files(paths):
        try:
            hits += scan_text(f.read_text(errors="ignore"), str(f))
        except Exception:
            continue
    return hits


def scan_staged() -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                         capture_output=True, text=True)
    hits: list[str] = []
    for name in out.stdout.split():
        if Path(name).suffix.lower() in _SKIP_SUFFIX:
            continue
        blob = subprocess.run(["git", "show", f":{name}"], capture_output=True, text=True)
        if blob.returncode == 0:
            hits += scan_text(blob.stdout, name)
    return hits


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    hits = scan_staged() if "--staged" in argv else scan_paths([a for a in argv if not a.startswith("--")] or ["."])
    if hits:
        print("SECRET SCAN FAILED — refusing to proceed:")
        for h in hits:
            print(f"  - {h}")
        print("\nRemove the secret, add the file to .gitignore, or move it to an env var.")
        return 1
    print("secret scan clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
