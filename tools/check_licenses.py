"""License gate for the shipped (runtime) dependency closure.

T010 â€” spec Â§10.1 / Â§11, DATA_TRACKER D-022.

Walks requirements.txt -> installed distributions -> their own requirements, and classifies
every package in that closure against tools/license_policy.toml. Dev-only tools are not
reachable from requirements.txt, so they are never checked. License data comes from
pip-licenses. Exit code 1 on any violation.
"""

from __future__ import annotations

import argparse
import json
import re

# subprocess runs pip-licenses from this venv with a fixed argv and no shell.
import subprocess  # nosec B404
import sys
import tomllib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
UNKNOWN = "UNKNOWN"
TRACKER_ID = re.compile(r"^D-\d{3}$")
MAX_METADATA_LEN = 80  # longer "License:" fields are usually the full license text
_TOKEN = re.compile(r"\(|\)|[^\s()]+")


@dataclass(frozen=True)
class Policy:
    allowed: frozenset[str]
    lgpl_ids: frozenset[str]
    lgpl_packages: frozenset[str]
    aliases: Mapping[str, str]
    # Installed as a dependency but stripped from the shipped app: package -> DATA_TRACKER id.
    excluded: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class Override:
    package: str
    license: str
    tracker: str
    reason: str


@dataclass(frozen=True)
class LicenseRecord:
    """The three license fields pip-licenses reports for one package."""

    name: str
    expression: str = UNKNOWN
    classifier: str = UNKNOWN
    metadata: str = UNKNOWN


@dataclass(frozen=True)
class Verdict:
    package: str
    license: str
    ok: bool
    reason: str


# ---------------------------------------------------------------- loading


def load_policy(path: Path) -> Policy:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Policy(
        allowed=frozenset(data["allowed"]),
        lgpl_ids=frozenset(data["lgpl_ids"]),
        lgpl_packages=frozenset(canonicalize_name(p) for p in data["lgpl_packages"]),
        aliases=dict(data.get("aliases", {})),
        excluded=_excluded(data.get("excluded", {})),
    )


def _excluded(entries: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for package, tracker in entries.items():
        if not isinstance(tracker, str) or not TRACKER_ID.match(tracker):
            raise ValueError(
                f"excluded package {package!r} must cite a DATA_TRACKER id like 'D-027', "
                f"got {tracker!r}"
            )
        result[canonicalize_name(package)] = tracker
    return result


def load_overrides(path: Path) -> dict[str, Override]:
    """Overrides must cite a DATA_TRACKER id; a malformed entry is a hard error."""
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = data.get("override", [])
    result: dict[str, Override] = {}
    for entry in entries:
        missing = [k for k in ("package", "license", "tracker", "reason") if not entry.get(k)]
        if missing:
            raise ValueError(f"override {entry!r} is missing {', '.join(missing)}")
        tracker = str(entry["tracker"])
        if not TRACKER_ID.match(tracker):
            raise ValueError(
                f"override for {entry['package']!r} must cite a DATA_TRACKER id like "
                f"'D-022', got {tracker!r}"
            )
        name = canonicalize_name(str(entry["package"]))
        result[name] = Override(name, str(entry["license"]), tracker, str(entry["reason"]))
    return result


def parse_requirements(text: str) -> list[Requirement]:
    """Top-level requirement lines; comments, blanks and pip options are skipped."""
    reqs: list[Requirement] = []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        try:
            reqs.append(Requirement(line))
        except InvalidRequirement as exc:
            raise ValueError(f"invalid requirement line {raw!r}: {exc}") from exc
    return reqs


# ---------------------------------------------------------------- closure


def runtime_closure(
    roots: Iterable[Requirement],
    get_requires: Callable[[str], list[str] | None],
) -> tuple[set[str], set[str]]:
    """Return (installed packages reachable from roots, reachable packages not installed).

    get_requires(name) returns the distribution's Requires-Dist lines, or None when the
    package is not installed. Markers are evaluated for this interpreter, including extras
    requested by the parent requirement.
    """
    seen_extras: dict[str, set[str]] = {}
    missing: set[str] = set()
    queue: list[tuple[str, frozenset[str]]] = []

    for req in roots:
        if req.marker is None or req.marker.evaluate({"extra": ""}):
            queue.append((canonicalize_name(req.name), frozenset(req.extras)))

    while queue:
        name, extras = queue.pop()
        known = seen_extras.get(name)
        if known is not None and extras <= known:
            continue
        seen_extras.setdefault(name, set()).update(extras)

        requires = get_requires(name)
        if requires is None:
            missing.add(name)
            continue
        active = {"", *extras}
        for line in requires:
            child = Requirement(line)
            if child.marker is not None and not any(
                child.marker.evaluate({"extra": e}) for e in active
            ):
                continue
            queue.append((canonicalize_name(child.name), frozenset(child.extras)))

    return set(seen_extras) - missing, missing


def installed_requires(name: str) -> list[str] | None:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    return dist.requires or []


# ---------------------------------------------------------------- classification


def _id_allowed(spdx_id: str, package: str, policy: Policy) -> bool:
    spdx_id = policy.aliases.get(spdx_id, spdx_id)
    if spdx_id.endswith("+"):
        spdx_id = spdx_id[:-1] + "-or-later"
    if spdx_id in policy.allowed:
        return True
    return spdx_id in policy.lgpl_ids and package in policy.lgpl_packages


class _Parser:
    """Minimal SPDX expression parser: WITH binds tightest, then AND, then OR."""

    def __init__(self, expression: str, package: str, policy: Policy) -> None:
        self.tokens = _TOKEN.findall(expression)
        self.pos = 0
        self.package = package
        self.policy = policy
        self.denied: list[str] = []

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _take(self) -> str:
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        self.pos += 1
        return tok

    def parse(self) -> bool:
        if not self.tokens:
            raise ValueError("empty expression")
        result = self._or()
        if self._peek() is not None:
            raise ValueError(f"unexpected token {self._peek()!r}")
        return result

    def _or(self) -> bool:
        result = self._and()
        while (tok := self._peek()) is not None and tok.upper() == "OR":
            self._take()
            right = self._and()
            result = result or right
        return result

    def _and(self) -> bool:
        result = self._atom()
        while (tok := self._peek()) is not None and tok.upper() == "AND":
            self._take()
            right = self._atom()
            result = result and right
        return result

    def _atom(self) -> bool:
        tok = self._take()
        if tok == "(":
            result = self._or()
            if self._take() != ")":
                raise ValueError("missing ')'")
            return result
        if tok == ")" or tok.upper() in ("AND", "OR", "WITH"):
            raise ValueError(f"unexpected token {tok!r}")
        # An exception only adds permissions, so judge the base license alone.
        if (nxt := self._peek()) is not None and nxt.upper() == "WITH":
            self._take()
            self._take()
        ok = _id_allowed(tok, self.package, self.policy)
        if not ok:
            self.denied.append(tok)
        return ok


def _license_text(record: LicenseRecord, override: Override | None) -> tuple[str, str]:
    """Pick the most reliable license field: (text, source)."""
    if override is not None:
        return override.license, f"override {override.tracker}"
    if record.expression != UNKNOWN:
        return record.expression, "expression"
    if record.classifier != UNKNOWN:
        return record.classifier, "classifier"
    meta = record.metadata.strip()
    if meta != UNKNOWN and meta and len(meta) <= MAX_METADATA_LEN and "\n" not in meta:
        return meta, "metadata"
    return UNKNOWN, "none"


def evaluate(record: LicenseRecord, policy: Policy, override: Override | None = None) -> Verdict:
    package = canonicalize_name(record.name)
    text, source = _license_text(record, override)

    if text == UNKNOWN:
        return Verdict(
            package,
            UNKNOWN,
            False,
            "license unknown: verify it and add an override citing a DATA_TRACKER id",
        )

    # Classifiers list several licenses; require all of them (safe direction).
    parts = text.split("; ") if source == "classifier" else [text]
    denied: list[str] = []
    ok = True
    for part in parts:
        expression = policy.aliases.get(part, part)
        words = expression.split()
        if len(words) > 1 and not any(w.upper() in ("AND", "OR", "WITH") for w in words):
            # A free-text name such as "Some Custom License": one unknown license.
            if not _id_allowed(expression, package, policy):
                denied.append(expression)
                ok = False
            continue
        parser = _Parser(expression, package, policy)
        try:
            part_ok = parser.parse()
        except ValueError as exc:
            return Verdict(package, text, False, f"cannot parse license ({exc})")
        denied.extend(parser.denied)
        ok = ok and part_ok

    if ok:
        return Verdict(package, text, True, f"allowed ({source})")
    lgpl = [d for d in denied if policy.aliases.get(d, d).startswith("LGPL")]
    if lgpl and len(lgpl) == len(denied):
        reason = "LGPL is only allowed for " + ", ".join(sorted(policy.lgpl_packages))
    else:
        reason = "not on the allow-list: " + ", ".join(dict.fromkeys(denied))
    return Verdict(package, text, False, reason)


# ---------------------------------------------------------------- CLI


def fetch_records(names: Iterable[str]) -> dict[str, LicenseRecord]:
    """Ask pip-licenses (in this interpreter's environment) for the license fields."""
    names = sorted(names)
    if not names:
        return {}
    argv = [
        sys.executable,
        "-m",
        "piplicenses",
        "--format=json",
        "--from=all",
        "--with-system",
        "--packages",
        *names,
    ]
    out = subprocess.run(argv, capture_output=True, text=True, check=True)  # nosec B603
    rows: list[dict[str, str]] = json.loads(out.stdout)
    return {
        canonicalize_name(row["Name"]): LicenseRecord(
            name=row["Name"],
            expression=row.get("License-Expression", UNKNOWN),
            classifier=row.get("License-Classifier", UNKNOWN),
            metadata=row.get("License-Metadata", UNKNOWN),
        )
        for row in rows
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="License gate for the runtime dependency closure.")
    parser.add_argument("--requirements", type=Path, default=ROOT / "requirements.txt")
    parser.add_argument("--policy", type=Path, default=ROOT / "tools" / "license_policy.toml")
    parser.add_argument("--overrides", type=Path, default=ROOT / "tools" / "license_overrides.toml")
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    overrides = load_overrides(args.overrides)

    if not args.requirements.exists():
        print(f"license gate: {args.requirements.name} not found; no runtime deps to check.")
        return 0

    roots = parse_requirements(args.requirements.read_text(encoding="utf-8"))
    closure, missing = runtime_closure(roots, installed_requires)
    if missing:
        print("license gate: FAIL, not installed (run pip install -r requirements.txt):")
        for name in sorted(missing):
            print(f"  - {name}")
        return 1

    excluded = sorted(closure & set(policy.excluded))
    shipped = closure - set(excluded)
    records = fetch_records(shipped)
    verdicts = [
        evaluate(records.get(name, LicenseRecord(name)), policy, overrides.get(name))
        for name in sorted(shipped)
    ]
    failures = [v for v in verdicts if not v.ok]

    width = max((len(v.package) for v in verdicts), default=7)
    for v in verdicts:
        mark = "ok  " if v.ok else "FAIL"
        print(f"{mark} {v.package:<{width}}  {v.license}  [{v.reason}]")
    for name in excluded:
        tracker = policy.excluded[name]
        print(f"excl {name:<{width}}  not shipped: the build must strip it ({tracker})")
    print(f"license gate: {len(verdicts)} runtime packages, {len(failures)} violation(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
