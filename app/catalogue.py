"""Reconcile the BOM, parts master and service list into one machine catalogue.

Everything is computed once, when the catalogue is built. Requests only read
the finished tables, so each answer is well under the one-second budget.

The rules come from Appendix Q of the brief. The cleaning steps, and why each
one exists, are written up in DATA.md.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# The AM-700 bottling line. Everything reachable from here is "in the machine".
ROOT_PART = "AS-40000"

_WHITESPACE = re.compile(r"\s+")
_WHOLE_NUMBER = re.compile(r"-?[0-9]+")
_YES = {"Y", "YES", "TRUE", "1"}
_NO = {"N", "NO", "FALSE", "0", ""}
_INVALID = object()  # sentinel for a serial bound that is not a whole number


class CatalogueError(Exception):
    """Raised when the source files are missing or unusable."""


def normalise_part_number(value: Optional[str]) -> str:
    """Part numbers are compared without case or whitespace: 'fa-30019 ' is 'FA-30019'."""
    return _WHITESPACE.sub("", value or "").upper()


def revision_key(revision: str) -> tuple[int, str]:
    """Revisions are letters (A, B, ... Z, AA, ...). Longer means later; then alphabetical."""
    return (len(revision), revision)


def parse_quantity(text: str) -> Optional[int]:
    """A positive whole quantity. Accepts '4' and '4.0' (some exports write whole numbers as decimals)."""
    text = (text or "").strip()
    if re.fullmatch(r"[0-9]+(\.0+)?", text):
        value = int(float(text))
        return value if value > 0 else None
    return None


def parse_whole_number(text: str) -> Optional[int]:
    """Return the integer for a whole-number string, or None if it is not one."""
    text = text.strip()
    if not _WHOLE_NUMBER.fullmatch(text):
        return None
    return int(text)


@dataclass(frozen=True)
class SerialRange:
    """Inclusive serial range. A bound of None means open at that end."""

    low: Optional[int]
    high: Optional[int]

    def covers(self, serial: int) -> bool:
        return (self.low is None or serial >= self.low) and (
            self.high is None or serial <= self.high
        )


@dataclass
class CleaningReport:
    """What was found in the source data and how it was handled. Shown at startup."""

    bom_rows: int = 0
    bom_rows_skipped: list[str] = field(default_factory=list)
    part_numbers_renormalised: int = 0
    duplicate_bom_rows: int = 0
    conflicting_bom_quantities: list[str] = field(default_factory=list)
    dropped_cycle_edges: list[str] = field(default_factory=list)
    ambiguous_cycles: list[str] = field(default_factory=list)
    duplicate_revision_rows: int = 0
    service_rows_invalid: list[str] = field(default_factory=list)
    service_conflicts: list[str] = field(default_factory=list)
    parts_in_machine: int = 0
    parts_missing_from_master: int = 0
    bom_parts_outside_machine: int = 0

    def summary(self) -> str:
        lines = [
            "Catalogue built:",
            f"  parts in machine: {self.parts_in_machine}",
            f"  missing from parts master: {self.parts_missing_from_master}",
            f"  BOM rows read: {self.bom_rows}",
            f"  BOM rows with case or space fixes: {self.part_numbers_renormalised}",
            f"  duplicate BOM rows ignored: {self.duplicate_bom_rows}",
            f"  BOM rows skipped as malformed: {len(self.bom_rows_skipped)}",
            f"  conflicting BOM quantities resolved: {len(self.conflicting_bom_quantities)}",
            f"  cycle edges dropped: {len(self.dropped_cycle_edges)}",
            f"  cycles reachable by more than one path (convention used): {len(self.ambiguous_cycles)}",
            f"  duplicate revision rows ignored: {self.duplicate_revision_rows}",
            f"  service rows invalid: {len(self.service_rows_invalid)}",
            f"  service conflicts resolved conservatively: {len(self.service_conflicts)}",
        ]
        return "\n".join(lines)


@dataclass
class Part:
    """One part in the machine, with everything the API reports about it."""

    part_number: str
    revision: Optional[str]
    description: Optional[str]
    status: str  # "ready", "not_replaceable" or "missing"
    total_quantity: int
    parents: list[str]
    children: list[tuple[str, int]]
    paths: list[list[str]]
    serial_ranges: list[SerialRange] = field(default_factory=list)

    def applies_to(self, serial: int) -> bool:
        if self.status != "ready":
            return False
        return any(rng.covers(serial) for rng in self.serial_ranges)


class Catalogue:
    """The finished, read-only catalogue for one machine."""

    def __init__(self, parts: dict[str, Part], root: str, report: CleaningReport):
        self._parts = parts
        self.root = root
        self.report = report

    def validation(self) -> dict:
        counts = Counter(p.status for p in self._parts.values())
        return {
            "parts": len(self._parts),
            "ready": counts.get("ready", 0),
            "missing": counts.get("missing", 0),
            "not_replaceable": counts.get("not_replaceable", 0),
        }

    def part(self, part_number: str) -> Optional[dict]:
        p = self._parts.get(normalise_part_number(part_number))
        if p is None:
            return None
        return {
            "part_number": p.part_number,
            "description": p.description,
            "revision": p.revision,
            "status": p.status,
            "total_quantity": p.total_quantity,
            "parents": list(p.parents),
            "children": [{"part_number": c, "quantity": q} for c, q in p.children],
        }

    def paths(self, part_number: str) -> Optional[dict]:
        p = self._parts.get(normalise_part_number(part_number))
        if p is None:
            return None
        return {
            "part_number": p.part_number,
            "paths": [list(path) for path in p.paths],
        }

    def applicable_parts(self, serial: int) -> int:
        return sum(1 for p in self._parts.values() if p.applies_to(serial))

    def __contains__(self, part_number: str) -> bool:
        return normalise_part_number(part_number) in self._parts


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _read_csv(path: Path, required: Iterable[str]) -> list[dict]:
    if not path.is_file():
        raise CatalogueError(f"missing data file: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise CatalogueError(f"empty data file: {path}")
        # Tolerate stray spaces and capitals in headers.
        fieldnames = {name.strip().lower(): name for name in reader.fieldnames if name}
        missing = [col for col in required if col not in fieldnames]
        if missing:
            raise CatalogueError(f"{path.name} is missing columns: {', '.join(missing)}")
        rows = []
        for raw in reader:
            row = {key.strip().lower(): (value or "") for key, value in raw.items() if key}
            if any(value.strip() for value in row.values()):
                rows.append(row)
        return rows


def load_catalogue(data_dir: Path, root: str = ROOT_PART) -> Catalogue:
    data_dir = Path(data_dir)
    bom = _read_csv(data_dir / "bom.csv", ["parent_pn", "child_pn", "quantity"])
    master = _read_csv(
        data_dir / "parts_master.csv", ["part_number", "revision", "description"]
    )
    service = _read_csv(
        data_dir / "service_parts.csv", ["part_number", "field_replaceable"]
    )
    return build_catalogue(bom, master, service, root=root)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def build_catalogue(
    bom_rows: list[dict],
    master_rows: list[dict],
    service_rows: list[dict],
    root: str = ROOT_PART,
) -> Catalogue:
    report = CleaningReport()
    root = normalise_part_number(root)

    # 1. Relationships: one fact per (parent, child) pair.
    children_map = _clean_bom(bom_rows, report)

    # 2. Keep only the relationships that describe the machine as a tree of
    #    contained parts, dropping any edge that points back up.
    kept, dropped, postorder = _remove_cycles(children_map, root)
    report.dropped_cycle_edges = [f"{p} -> {c}" for p, c in dropped]

    machine = set(postorder)
    report.ambiguous_cycles = _ambiguous_cycles(children_map, machine, root)
    report.bom_parts_outside_machine = len(
        {p for p in children_map if p not in machine}
    )

    # 3. Current revision and description from the parts master.
    latest = _latest_revisions(master_rows, report)

    # 4. Service rules.
    service_rules = _service_rules(service_rows, report)

    # 5. Totals, parents and paths over the cleaned graph.
    parents: dict[str, list[str]] = defaultdict(list)
    for parent, kids in kept.items():
        for child in kids:
            parents[child].append(parent)
    for child in parents:
        parents[child].sort()

    total = {node: 0 for node in machine}
    total[root] = 1
    for node in reversed(postorder):  # parents before children
        for child, qty in kept.get(node, {}).items():
            total[child] += total[node] * qty

    path_memo: dict[str, list[list[str]]] = {}

    def paths_to(node: str) -> list[list[str]]:
        if node in path_memo:
            return path_memo[node]
        if node == root:
            result = [[root]]
        else:
            result = []
            for parent in parents[node]:
                result.extend(path + [node] for path in paths_to(parent))
            result.sort()
        path_memo[node] = result
        return result

    parts: dict[str, Part] = {}
    for node in machine:
        master = latest.get(node)
        if master is None:
            status = "missing"
            revision = None
            description = None
            report.parts_missing_from_master += 1
        else:
            revision, description = master
            rules = service_rules.get(node)
            status = "ready" if rules is not None else "not_replaceable"
        ranges = service_rules.get(node) or []
        parts[node] = Part(
            part_number=node,
            revision=revision,
            description=description,
            status=status,
            total_quantity=total[node],
            parents=list(parents[node]),
            children=sorted(kept.get(node, {}).items()),
            paths=paths_to(node),
            serial_ranges=list(ranges),
        )

    report.parts_in_machine = len(parts)
    return Catalogue(parts, root=root, report=report)


def _clean_bom(bom_rows, report: CleaningReport) -> dict[str, dict[str, int]]:
    """Turn raw BOM rows into one quantity per (parent, child) pair."""
    seen: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for index, row in enumerate(bom_rows, start=2):
        report.bom_rows += 1
        raw_parent = row.get("parent_pn", "")
        raw_child = row.get("child_pn", "")
        parent = normalise_part_number(raw_parent)
        child = normalise_part_number(raw_child)
        if parent != raw_parent or child != raw_child:
            report.part_numbers_renormalised += 1
        qty_text = row.get("quantity", "")
        if not parent or not child:
            report.bom_rows_skipped.append(f"line {index}: blank part number")
            continue
        qty = parse_quantity(qty_text)
        if qty is None:
            report.bom_rows_skipped.append(f"line {index}: bad quantity {qty_text.strip()!r}")
            continue
        seen[(parent, child)][qty] += 1

    children_map: dict[str, dict[str, int]] = defaultdict(dict)
    for (parent, child), counts in seen.items():
        if sum(counts.values()) > 1:
            report.duplicate_bom_rows += sum(counts.values()) - 1
        if len(counts) > 1:
            report.conflicting_bom_quantities.append(f"{parent} -> {child}: {dict(counts)}")
        # Conflicting quantities should not happen. If they do, take the most
        # common value, and the larger one on a tie, and say so in the report.
        qty = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        children_map[parent][child] = qty
    return children_map


def _remove_cycles(children_map, root: str):
    """Depth-first walk from the root. An edge back to a part already on the
    current path (an ancestor) is the wrong relationship, so it is dropped.

    Returns (kept edges, dropped edges, post-order of every part in the machine).
    """
    state: dict[str, str] = {root: "active"}
    kept: dict[str, dict[str, int]] = defaultdict(dict)
    dropped: list[tuple[str, str]] = []
    postorder: list[str] = []

    stack = [(root, iter(sorted(children_map.get(root, {}))))]
    while stack:
        node, children = stack[-1]
        for child in children:
            if state.get(child) == "active":
                dropped.append((node, child))
                continue
            kept[node][child] = children_map[node][child]
            if child not in state:
                state[child] = "active"
                stack.append((child, iter(sorted(children_map.get(child, {})))))
                break
        else:
            stack.pop()
            state[node] = "done"
            postorder.append(node)
    return kept, dropped, postorder


def _ambiguous_cycles(children_map, machine: set, root: str) -> list[str]:
    """Report cycles that more than one path from the root leads into.

    With one entry point the rule is clear: the link that points back to the
    entry is the wrong one. With two or more entry points, the brief does not
    say which link is wrong, so the choice is a convention and is reported.
    """
    nodes = sorted(machine)
    edges = {n: [c for c in children_map.get(n, {}) if c in machine] for n in nodes}
    parents: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for c in edges[n]:
            parents[c].append(n)

    def reachable(start: str) -> set:
        seen, stack = {start}, [start]
        while stack:
            for c in edges[stack.pop()]:
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
        return seen

    reach = {n: reachable(n) for n in nodes}
    assigned: set = set()
    report_lines: list[str] = []
    for n in nodes:
        if n in assigned:
            continue
        component = sorted(m for m in reach[n] if n in reach[m])  # mutual reachability
        assigned.update(component)
        if len(component) < 2:
            continue
        members = set(component)
        entries = sorted(
            m for m in component
            if m != root and any(p not in members for p in parents[m])
        )
        if root in members:
            entries = sorted(set(entries) | {root})
        if len(entries) > 1:
            report_lines.append(
                f"cycle through {', '.join(component)}: entered at {', '.join(entries)}"
            )
    return report_lines


def _latest_revisions(master_rows, report: CleaningReport):
    """Map part number to (latest revision, description) from the parts master."""
    latest: dict[str, tuple[tuple[int, str], str, Optional[str]]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in master_rows:
        part = normalise_part_number(row.get("part_number"))
        if not part:
            continue
        revision = row.get("revision", "").strip().upper()
        if (part, revision) in seen_pairs:
            report.duplicate_revision_rows += 1
            continue
        seen_pairs.add((part, revision))
        description = row.get("description", "").strip() or None
        key = revision_key(revision)
        if part not in latest or key > latest[part][0]:
            latest[part] = (key, revision or None, description)
    return {part: (rev, desc) for part, (_, rev, desc) in latest.items()}


def _service_rules(service_rows, report: CleaningReport):
    """Map part number to its serial ranges, for parts that are ready.

    A part is ready only if every row for it says Y and every serial bound is a
    whole number. Anything less certain is treated as not replaceable, because
    a wrong part shipped to a customer costs them a day of downtime.
    """
    rows_by_part: dict[str, list[tuple[bool, Optional[SerialRange], str]]] = defaultdict(list)
    for index, row in enumerate(service_rows, start=2):
        part = normalise_part_number(row.get("part_number"))
        if not part:
            report.service_rows_invalid.append(f"line {index}: blank part number")
            continue
        flag = row.get("field_replaceable", "").strip().upper()
        if flag not in _YES | _NO:
            report.service_rows_invalid.append(f"line {index}: unknown flag {flag!r}")
            flag = "N"
        low = _parse_bound(row.get("serial_from", ""))
        high = _parse_bound(row.get("serial_to", ""))
        if low is _INVALID or high is _INVALID:
            report.service_rows_invalid.append(f"line {index}: bad serial range for {part}")
            rows_by_part[part].append((False, None, "bad range"))
            continue
        if low is not None and high is not None and low > high:
            low, high = high, low
        rows_by_part[part].append((flag in _YES, SerialRange(low, high), flag))

    rules: dict[str, list[SerialRange]] = {}
    for part, entries in rows_by_part.items():
        if not all(is_yes for is_yes, _, _ in entries):
            if any(is_yes for is_yes, _, _ in entries):
                report.service_conflicts.append(f"{part}: mixed Y/N rows, treated as not replaceable")
            continue
        rules[part] = [rng for _, rng, _ in entries]
    return rules


def _parse_bound(text: str):
    text = (text or "").strip()
    if not text:
        return None
    value = parse_whole_number(text)
    return _INVALID if value is None else value
