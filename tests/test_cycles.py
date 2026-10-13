"""Cycles: the cases where the brief's rule needs a convention, and random graphs."""
import itertools
import random
import unittest

from app.catalogue import build_catalogue
from tests.helpers import bom, master, service


def snapshot(cat):
    """Everything the API would say about the machine, as a comparable value."""
    return (
        tuple(sorted(cat.validation().items())),
        tuple(cat.report.dropped_cycle_edges),
        tuple(
            (pn, tuple(cat.part(pn)["parents"]), cat.part(pn)["total_quantity"],
             tuple(map(tuple, cat.paths(pn)["paths"])))
            for pn in sorted(cat._parts)
        ),
    )


def is_acyclic(cat):
    graph = {pn: [c["part_number"] for c in cat.part(pn)["children"]] for pn in cat._parts}
    state = {}

    def visit(n):
        state[n] = "active"
        for c in graph[n]:
            if state.get(c) == "active":
                return False
            if c not in state and not visit(c):
                return False
        state[n] = "done"
        return True

    return all(visit(n) for n in graph if n not in state)


def everything_reachable_from(cat, root):
    seen, stack = {root}, [root]
    while stack:
        for c in cat.part(stack.pop())["children"]:
            if c["part_number"] not in seen:
                seen.add(c["part_number"])
                stack.append(c["part_number"])
    return seen


# Root reaches the cycle X <-> Y through two different branches, A and B.
TWO_ENTRY_EDGES = [("R", "A", 1), ("R", "B", 1), ("A", "X", 1), ("B", "Y", 1), ("X", "Y", 1), ("Y", "X", 1)]


class TwoEntryCycleTests(unittest.TestCase):

    def test_every_row_order_gives_the_same_answer(self):
        """Row order must never decide which link is dropped. Checked over all 720 orders."""
        outcomes = set()
        for order in itertools.permutations(TWO_ENTRY_EDGES):
            cat = build_catalogue(bom(*order), master(), service(), root="R")
            outcomes.add(snapshot(cat))
        self.assertEqual(len(outcomes), 1)

    def test_the_choice_is_a_documented_convention_not_a_row_effect(self):
        """Part numbers, not rows, pick the branch that wins. This pins the current convention:
        the walk visits children in part-number order, so the branch whose name sorts first
        enters the cycle, and the link back into that entry point is dropped."""
        cat = build_catalogue(bom(*TWO_ENTRY_EDGES), master(), service(), root="R")
        self.assertEqual(cat.report.dropped_cycle_edges, ["Y -> X"])
        self.assertEqual(cat.part("X")["parents"], ["A"])

        relabelled = [("R", "M", 1), ("R", "Z", 1), ("M", "P", 1), ("Z", "Q", 1), ("P", "Q", 1), ("Q", "P", 1)]
        cat2 = build_catalogue(bom(*relabelled), master(), service(), root="R")
        self.assertEqual(cat2.report.dropped_cycle_edges, ["Q -> P"])

    def test_two_entry_cycle_is_reported_as_ambiguous(self):
        cat = build_catalogue(bom(*TWO_ENTRY_EDGES), master(), service(), root="R")
        self.assertEqual(len(cat.report.ambiguous_cycles), 1)
        self.assertIn("entered at X, Y", cat.report.ambiguous_cycles[0])

    def test_result_is_still_a_tree_with_every_part_reachable(self):
        cat = build_catalogue(bom(*TWO_ENTRY_EDGES), master(), service(), root="R")
        self.assertTrue(is_acyclic(cat))
        self.assertEqual(everything_reachable_from(cat, "R"), set(cat._parts))


class SingleEntryCycleTests(unittest.TestCase):

    def test_single_entry_cycle_is_not_ambiguous(self):
        cat = build_catalogue(
            bom(("R", "A", 1), ("A", "B", 1), ("B", "C", 1), ("C", "A", 1)),
            master(), service(), root="R",
        )
        self.assertEqual(cat.report.dropped_cycle_edges, ["C -> A"])
        self.assertEqual(cat.report.ambiguous_cycles, [])

    def test_no_cycle_means_nothing_reported(self):
        cat = build_catalogue(bom(("R", "A", 1), ("A", "B", 1)), master(), service(), root="R")
        self.assertEqual(cat.report.dropped_cycle_edges, [])
        self.assertEqual(cat.report.ambiguous_cycles, [])


class RandomCyclicGraphTests(unittest.TestCase):
    """Random graphs full of cycles. Whatever they contain, the answer must be a valid tree,
    every machine part must still be reachable, and row order must not matter."""

    def random_graph(self, rng):
        nodes = ["R"] + [f"P{i}" for i in range(rng.randint(3, 9))]
        edges = []
        for _ in range(rng.randint(2, 20)):
            p, c = rng.choice(nodes), rng.choice(nodes)  # may create cycles and self-loops
            edges.append((p, c, rng.randint(1, 3)))
        return edges

    def test_random_graphs_give_valid_trees_and_stable_answers(self):
        rng = random.Random(2024)
        for _ in range(300):
            edges = self.random_graph(rng)
            cat = build_catalogue(bom(*edges), master(), service(), root="R")
            self.assertTrue(is_acyclic(cat), edges)
            self.assertEqual(everything_reachable_from(cat, "R"), set(cat._parts), edges)

            shuffled = list(edges)
            rng.shuffle(shuffled)
            again = build_catalogue(bom(*shuffled), master(), service(), root="R")
            self.assertEqual(snapshot(cat), snapshot(again), edges)


if __name__ == "__main__":
    unittest.main()
