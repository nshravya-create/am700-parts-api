"""Small builders so tests can state the input rows directly."""
from app.catalogue import build_catalogue


def bom(*triples):
    return [{"parent_pn": p, "child_pn": c, "quantity": str(q)} for p, c, q in triples]


def master(*quads):
    return [
        {"part_number": pn, "revision": rev, "description": desc, "category": "", "unit_cost": "1"}
        for pn, rev, desc in quads
    ]


def service(*rows):
    return [
        {"part_number": pn, "field_replaceable": flag, "serial_from": lo, "serial_to": hi}
        for pn, flag, lo, hi in rows
    ]


def worked_example(root="AS-1"):
    """Appendix Q worked example. Expected answers are written in the tests."""
    return build_catalogue(
        bom(("AS-1", "AS-2", 2), ("AS-1", "FA-9", 4), ("AS-2", "FA-9", 3), ("AS-2", "EL-5", 1)),
        master(("AS-1", "A", "Top assembly"), ("AS-2", "A", "Sub assembly"),
               ("FA-9", "A", "Old fastener"), ("FA-9", "B", "Fastener")),
        service(("AS-2", "Y", "", ""), ("FA-9", "Y", "", ""), ("EL-5", "Y", "1000", "1999")),
        root=root,
    )
