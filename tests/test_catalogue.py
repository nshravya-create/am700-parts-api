import random
import unittest
from pathlib import Path

from app.catalogue import (
    ROOT_PART,
    CatalogueError,
    SerialRange,
    build_catalogue,
    load_catalogue,
    parse_whole_number,
)
from tests.helpers import bom, master, service, worked_example

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class WorkedExampleTests(unittest.TestCase):
    """The brief's worked example, checked against the answers printed in Appendix Q."""

    def setUp(self):
        self.cat = worked_example()

    def test_validation_counts(self):
        self.assertEqual(
            self.cat.validation(),
            {"parts": 4, "ready": 2, "missing": 1, "not_replaceable": 1},
        )

    def test_statuses(self):
        self.assertEqual(self.cat.part("AS-1")["status"], "not_replaceable")
        self.assertEqual(self.cat.part("AS-2")["status"], "ready")
        self.assertEqual(self.cat.part("FA-9")["status"], "ready")
        self.assertEqual(self.cat.part("EL-5")["status"], "missing")

    def test_fa9_detail_matches_example(self):
        fa9 = self.cat.part("FA-9")
        self.assertEqual(fa9["revision"], "B")
        self.assertEqual(fa9["description"], "Fastener")
        self.assertEqual(fa9["total_quantity"], 10)
        self.assertEqual(fa9["parents"], ["AS-1", "AS-2"])
        self.assertEqual(fa9["children"], [])

    def test_fa9_paths_in_sorted_order(self):
        self.assertEqual(
            self.cat.paths("FA-9")["paths"],
            [["AS-1", "AS-2", "FA-9"], ["AS-1", "FA-9"]],
        )

    def test_serial_2500_counts_ready_parts(self):
        self.assertEqual(self.cat.applicable_parts(2500), 2)

    def test_missing_part_has_null_description_and_revision(self):
        el5 = self.cat.part("EL-5")
        self.assertIsNone(el5["description"])
        self.assertIsNone(el5["revision"])

    def test_root_has_total_one_and_no_parents(self):
        root = self.cat.part("AS-1")
        self.assertEqual(root["total_quantity"], 1)
        self.assertEqual(root["parents"], [])

    def test_outside_machine_is_absent(self):
        self.assertIsNone(self.cat.part("ZZ-1"))
        self.assertIsNone(self.cat.paths("ZZ-1"))


class RuleTests(unittest.TestCase):

    def test_part_numbers_ignore_case_and_whitespace(self):
        messy = build_catalogue(
            bom((" as-1 ", "fa-9 ", 4)),
            master(("FA-9", "A", "Fastener")),
            service(("fa-9", "y", "", "")),
            root="AS-1",
        )
        clean = build_catalogue(
            bom(("AS-1", "FA-9", 4)),
            master(("FA-9", "A", "Fastener")),
            service(("FA-9", "Y", "", "")),
            root="AS-1",
        )
        self.assertEqual(messy.part("FA-9"), clean.part("FA-9"))
        self.assertEqual(messy.part(" fa-9 ")["status"], "ready")

    def test_duplicate_bom_rows_count_once(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 4), ("AS-1", "FA-9", 4), ("AS-1", "FA-9", 4)),
            master(("FA-9", "A", "Fastener")),
            service(),
            root="AS-1",
        )
        self.assertEqual(cat.part("FA-9")["total_quantity"], 4)
        self.assertEqual(cat.report.duplicate_bom_rows, 2)

    def test_quantity_written_as_decimal_is_read_as_whole_number(self):
        cat = build_catalogue(
            [{"parent_pn": "AS-1", "child_pn": "FA-9", "quantity": " 4.0 "}],
            master(), service(), root="AS-1",
        )
        self.assertEqual(cat.part("AS-1")["children"], [{"part_number": "FA-9", "quantity": 4}])

    def test_malformed_quantities_are_skipped_and_reported(self):
        cat = build_catalogue(
            [{"parent_pn": "AS-1", "child_pn": "FA-9", "quantity": "2.5"},
             {"parent_pn": "AS-1", "child_pn": "EL-5", "quantity": "0"},
             {"parent_pn": "AS-1", "child_pn": "ME-7", "quantity": "lots"},
             {"parent_pn": "AS-1", "child_pn": "ME-8", "quantity": "3"}],
            master(), service(), root="AS-1",
        )
        self.assertEqual(cat.part("AS-1")["children"], [{"part_number": "ME-8", "quantity": 3}])
        self.assertEqual(len(cat.report.bom_rows_skipped), 3)

    def test_conflicting_quantities_use_most_common_value(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 4), ("AS-1", "FA-9", 4), ("AS-1", "FA-9", 6)),
            master(), service(), root="AS-1",
        )
        self.assertEqual(cat.part("AS-1")["children"], [{"part_number": "FA-9", "quantity": 4}])
        self.assertEqual(cat.part("FA-9")["total_quantity"], 4)

    def test_back_edge_is_dropped_and_reported(self):
        # AS-1 -> AS-2 -> AS-3 -> AS-2: the last edge points back up into the machine
        cat = build_catalogue(
            bom(("AS-1", "AS-2", 1), ("AS-2", "AS-3", 1), ("AS-3", "AS-2", 1), ("AS-3", "FA-9", 2)),
            master(), service(), root="AS-1",
        )
        self.assertEqual(cat.part("AS-2")["parents"], ["AS-1"])
        self.assertEqual(cat.part("AS-3")["parents"], ["AS-2"])
        self.assertEqual(cat.part("FA-9")["total_quantity"], 2)
        self.assertEqual(cat.report.dropped_cycle_edges, ["AS-3 -> AS-2"])

    def test_self_containing_part_is_dropped(self):
        cat = build_catalogue(bom(("AS-1", "AS-1", 1), ("AS-1", "FA-9", 1)), master(), service(), root="AS-1")
        self.assertEqual(cat.part("AS-1")["children"], [{"part_number": "FA-9", "quantity": 1}])

    def test_total_quantity_sums_over_paths(self):
        cat = worked_example()
        self.assertEqual(cat.part("FA-9")["total_quantity"], 10)

    def test_current_revision_is_highest_letter(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1)),
            master(("FA-9", "C", "Third"), ("FA-9", "A", "First"), ("FA-9", "B", "Second")),
            service(), root="AS-1",
        )
        self.assertEqual(cat.part("FA-9")["revision"], "C")
        self.assertEqual(cat.part("FA-9")["description"], "Third")

    def test_revision_ordering_handles_two_letters(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1)),
            master(("FA-9", "Z", "Z one"), ("FA-9", "AA", "AA one")),
            service(), root="AS-1",
        )
        self.assertEqual(cat.part("FA-9")["revision"], "AA")

    def test_not_in_service_list_is_not_replaceable(self):
        cat = build_catalogue(bom(("AS-1", "FA-9", 1)), master(("FA-9", "A", "F")), service(), root="AS-1")
        self.assertEqual(cat.part("FA-9")["status"], "not_replaceable")

    def test_mixed_flags_are_conservative(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1)),
            master(("FA-9", "A", "F")),
            service(("FA-9", "Y", "", ""), ("FA-9", "N", "", "")),
            root="AS-1",
        )
        self.assertEqual(cat.part("FA-9")["status"], "not_replaceable")
        self.assertTrue(cat.report.service_conflicts)

    def test_bad_serial_range_makes_part_not_ready(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1)),
            master(("FA-9", "A", "F")),
            service(("FA-9", "Y", "abc", "")),
            root="AS-1",
        )
        self.assertEqual(cat.part("FA-9")["status"], "not_replaceable")
        self.assertTrue(cat.report.service_rows_invalid)

    def test_reversed_serial_range_is_swapped(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1)),
            master(("FA-9", "A", "F")),
            service(("FA-9", "Y", "2999", "1000")),
            root="AS-1",
        )
        self.assertEqual(cat.applicable_parts(1000), 1)
        self.assertEqual(cat.applicable_parts(2999), 1)
        self.assertEqual(cat.applicable_parts(3000), 0)

    def test_serial_ranges_include_both_ends(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1)),
            master(("FA-9", "A", "F")),
            service(("FA-9", "Y", "1000", "1999")),
            root="AS-1",
        )
        self.assertEqual(cat.applicable_parts(999), 0)
        self.assertEqual(cat.applicable_parts(1000), 1)
        self.assertEqual(cat.applicable_parts(1999), 1)
        self.assertEqual(cat.applicable_parts(2000), 0)

    def test_ready_part_without_range_applies_to_every_serial(self):
        cat = build_catalogue(bom(("AS-1", "FA-9", 1)), master(("FA-9", "A", "F")),
                              service(("FA-9", "Y", "", "")), root="AS-1")
        self.assertEqual(cat.applicable_parts(-5), 1)
        self.assertEqual(cat.applicable_parts(123456789), 1)

    def test_not_replaceable_part_never_applies(self):
        cat = build_catalogue(bom(("AS-1", "FA-9", 1)), master(("FA-9", "A", "F")),
                              service(("FA-9", "N", "", "")), root="AS-1")
        self.assertEqual(cat.applicable_parts(2500), 0)

    def test_missing_part_never_applies_even_with_open_range(self):
        cat = build_catalogue(bom(("AS-1", "FA-9", 1)), master(), service(("FA-9", "Y", "", "")),
                              root="AS-1")
        self.assertEqual(cat.part("FA-9")["status"], "missing")
        self.assertEqual(cat.applicable_parts(2500), 0)

    def test_paths_sorted_by_part_number_from_the_top(self):
        cat = build_catalogue(
            bom(("AS-1", "AS-2", 1), ("AS-1", "FA-9", 1), ("AS-2", "FA-9", 1)),
            master(), service(), root="AS-1",
        )
        self.assertEqual(cat.paths("FA-9")["paths"], [["AS-1", "AS-2", "FA-9"], ["AS-1", "FA-9"]])

    def test_parents_and_children_are_sorted(self):
        cat = build_catalogue(
            bom(("AS-1", "FA-9", 1), ("AS-1", "AS-2", 1), ("AS-2", "FA-9", 1), ("AS-1", "EL-5", 2)),
            master(), service(), root="AS-1",
        )
        self.assertEqual(cat.part("FA-9")["parents"], ["AS-1", "AS-2"])
        self.assertEqual(
            cat.part("AS-1")["children"],
            [{"part_number": "AS-2", "quantity": 1}, {"part_number": "EL-5", "quantity": 2},
             {"part_number": "FA-9", "quantity": 1}],
        )

    def test_parts_outside_root_are_not_in_catalogue(self):
        cat = build_catalogue(bom(("AS-1", "FA-9", 1), ("AS-9", "EL-5", 1)), master(), service(),
                              root="AS-1")
        self.assertIsNone(cat.part("EL-5"))
        self.assertIsNone(cat.part("AS-9"))
        self.assertEqual(cat.validation()["parts"], 2)


class ParseTests(unittest.TestCase):

    def test_whole_numbers(self):
        self.assertEqual(parse_whole_number("2500"), 2500)
        self.assertEqual(parse_whole_number(" 2500 "), 2500)
        self.assertEqual(parse_whole_number("-7"), -7)

    def test_non_whole_numbers_are_rejected(self):
        for text in ["25.5", "2500.0", "abc", "", "1e3", "12 34", "+5"]:
            self.assertIsNone(parse_whole_number(text), text)

    def test_serial_range_covers(self):
        self.assertTrue(SerialRange(None, None).covers(0))
        self.assertTrue(SerialRange(5, None).covers(10**9))
        self.assertFalse(SerialRange(5, 9).covers(10))


class RealDataTests(unittest.TestCase):
    """Checks against the brief's data folder. These numbers are our own reading of it."""

    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalogue(DATA_DIR, ROOT_PART)

    def test_machine_size_and_statuses(self):
        self.assertEqual(
            self.cat.validation(),
            {"parts": 875, "ready": 483, "missing": 25, "not_replaceable": 367},
        )

    def test_cycle_edge_is_the_one_from_inside(self):
        self.assertEqual(self.cat.report.dropped_cycle_edges, ["AS-40209 -> AS-40002"])
        self.assertEqual(self.cat.part("AS-40002")["parents"], ["AS-40001"])
        self.assertEqual(self.cat.part("AS-40209")["parents"], ["AS-40208"])

    def test_retired_assembly_is_outside_machine(self):
        self.assertIsNone(self.cat.part("AS-40210"))

    def test_lowercase_service_row_is_found(self):
        self.assertEqual(self.cat.part("AS-40024")["status"], "not_replaceable")
        self.assertEqual(self.cat.part("EL-10227")["status"], "not_replaceable")

    def test_top_part(self):
        top = self.cat.part("AS-40000")
        self.assertEqual(top["total_quantity"], 1)
        self.assertEqual(top["parents"], [])
        self.assertEqual(top["revision"], "A")
        self.assertEqual(top["description"], "AM-700 bottling line")

    def test_fa19_total_is_sum_over_all_routes(self):
        self.assertEqual(self.cat.part("FA-30019")["total_quantity"], 178)

    def test_part_numbers_work_in_any_case(self):
        self.assertEqual(self.cat.part("fa-30019 "), self.cat.part("FA-30019"))

    def test_serial_count_is_within_ready_parts(self):
        ready = self.cat.validation()["ready"]
        for serial in (0, 1000, 2500, 3000, 9999, 123456):
            self.assertLessEqual(self.cat.applicable_parts(serial), ready)

    def test_row_order_and_noise_do_not_change_answers(self):
        """Grading uses a second export with new problems. Answers must follow the rules, not the rows."""
        import csv

        def read(name):
            with (DATA_DIR / name).open(newline="", encoding="utf-8-sig") as fh:
                return list(csv.DictReader(fh))

        bom_rows, master_rows, service_rows = read("bom.csv"), read("parts_master.csv"), read("service_parts.csv")
        rng = random.Random(7)
        rng.shuffle(bom_rows)
        rng.shuffle(master_rows)
        rng.shuffle(service_rows)
        for row in bom_rows:
            if rng.random() < 0.2:
                row["parent_pn"] = " " + row["parent_pn"].lower() + "  "
        shuffled = build_catalogue(bom_rows, master_rows, service_rows, root=ROOT_PART)

        self.assertEqual(shuffled.validation(), self.cat.validation())
        for pn in ["AS-40000", "FA-30019", "AS-40002", "EL-10024", "ME-20304"]:
            self.assertEqual(shuffled.part(pn), self.cat.part(pn), pn)
            self.assertEqual(shuffled.paths(pn), self.cat.paths(pn), pn)
        for serial in (0, 1000, 2500, 9999):
            self.assertEqual(shuffled.applicable_parts(serial), self.cat.applicable_parts(serial))

    def test_every_machine_part_has_a_path_from_the_root(self):
        for pn in list(self.cat._parts)[:400]:
            paths = self.cat.paths(pn)["paths"]
            self.assertTrue(paths, pn)
            for path in paths:
                self.assertEqual(path[0], ROOT_PART)
                self.assertEqual(path[-1], pn)


class LoadingTests(unittest.TestCase):

    def test_missing_file_is_reported_clearly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CatalogueError):
                load_catalogue(Path(tmp), ROOT_PART)

    def test_missing_column_is_reported_clearly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "bom.csv").write_text("parent,child,quantity\nA,B,1\n")
            (d / "parts_master.csv").write_text("part_number,revision,description\n")
            (d / "service_parts.csv").write_text("part_number,field_replaceable\n")
            with self.assertRaisesRegex(CatalogueError, "parent_pn"):
                load_catalogue(d, "A")


if __name__ == "__main__":
    unittest.main()
