DATA.md: data sourcing and test design
Where the data came from

The brief’s data folder holds three CSV files exported from three systems that were never reconciled:

bom.csv (1,287 rows): engineering’s bill of materials. Each row says a parent contains a quantity of a child.
parts_master.csv (950 rows, 855 part numbers): the parts master. A part can have several revisions (A, B, C).
service_parts.csv (854 rows): the service team’s list. Y or N for whether an engineer may replace the part on site, and optionally an inclusive serial range.

I treat the three files as the only source. I did not guess at missing data or fill it from outside.

What I found, and what I decided

I measured each problem with a script before writing any rules, so the decisions rest on counts.

1. Part numbers typed inconsistently. 20 BOM rows contain a part number with a stray space or in lowercase, for example AS-40133, as-40100 and fa-30015 . Six service rows use lowercase (as-40024, el-10227, and four more).
Decision: every part number is normalised before any comparison: all whitespace removed, uppercased. Without this, those parts would look missing, or appear twice.

2. Duplicate relationships. 40 BOM (parent, child) pairs appear more than once, each with the same quantity. Appendix Q says a relationship is one fact however many times it is exported.
Decision: each pair counts once. Quantities are not summed, because summing would double-count the parts. (There were no conflicting quantities in this data. If there were, the code takes the most common value and reports it.)

3. A cycle. The BOM says AS-40002 → AS-40208 → AS-40209 → AS-40002. Coming down from AS-40000, the machine reaches AS-40002 first, and AS-40209 sits inside it. The edge AS-40209 → AS-40002 is the wrong relationship, because it points back up from inside the machine.
Decision: a depth-first walk from AS-40000 drops an edge whose child is already on the current path. Only that one edge is dropped, and it is listed in the startup report. Parts in the cycle keep their correct parents.

This data has one entry point into its cycle, so the brief’s rule identifies the edge to remove without ambiguity. A cycle that two different branches lead into is different: the brief does not say which edge is wrong. For that case the code uses a convention, and I tested it:

Row order never changes the result. A test checks all 720 row orders of a two-branch cycle.
Part numbers do decide it. The walk visits children in part-number order, so the branch whose parent sorts first enters the cycle, and the link back into that entry point is dropped. Renaming the parts can change which link is dropped. A test pins this convention so it cannot change silently.
The startup report counts these cycles under “cycles reachable by more than one path (convention used)”. This data has none.

The result is always a valid tree with every part still reachable from AS-40000. This is the one place where the answer is a convention rather than a rule from the brief. If such a cycle ever appears in production data, the data owners should confirm which relationship is incorrect.

4. A retired assembly. AS-40210 (“Retired dosing unit”) is a parent in the BOM, but nothing in the machine reaches it. Four of its children (EL-10336, EL-10337, ME-20307, ME-20308) are used only through it, so they are outside the machine. The fifth, FA-30022, is also used elsewhere in the machine, so it stays, and its relationship to AS-40210 is ignored.
Decision: a part is in the catalogue only if the machine reaches it from AS-40000. Anything else returns 404.

5. Parts in the machine but not in the parts master. 25 parts in the machine have no entry in the parts master (for example EL-10024, ME-20032, ME-20291). They are not in the service list either.
Decision: status missing, with description and revision null. They never count as ready. Their own children are still part of the machine and are counted.

6. Superseded revisions. 95 older revisions have “(superseded)” in their description. No latest revision does.
Decision: a part’s description and revision come from its highest revision letter, as Appendix Q says. The “(superseded)” text is kept verbatim in older revisions and never reaches the API for current parts.

7. Parts in the parts master or service list but not in the machine. Five parts (AS-40210, EL-10336, EL-10337, ME-20307, ME-20308) appear in the service list or parts master but are not in the machine.
Decision: they are ignored. The API returns 404 for them, and they do not count in the validation totals.

8. Machine parts with no service row. 26 machine parts have no service row. That is AS-40000, the top assembly, and the 25 missing parts from point 5.
Decision: a part with no service row is not_replaceable. That is the conservative choice. Only a part explicitly marked Y can be shipped on site.

9. Service rules. Ranges in this data are whole numbers, and every range is on a Y row. There are no mixed Y/N duplicates. The brief does not say what to do with malformed input, so I decided the following, and the code handles these cases even though this data does not contain them.
Decision: a range is inclusive at both ends. Reversed bounds are swapped. A range with a non-whole-number bound makes the part not_replaceable, because the safe answer is to refuse rather than guess. A blank or unknown flag counts as N.

10. Quantities. This data has only whole-number quantities. A new export might write 4.0, so that is read as 4. A quantity that is zero, negative or not numeric is skipped, and the skip is reported at startup.

Results on this data
875 parts in the machine (including AS-40000).
483 ready, 367 not_replaceable, 25 missing.
FA-30019 appears in 22 paths, with a total quantity of 178. I checked both figures with a separate calculation.
1,242 paths in total across the machine.
How I tested it

The test suite has four parts:

The brief’s worked example. Every number and path in Appendix Q is asserted exactly, so the rules are checked against the brief’s own answers, not my reading of them.
Each rule on its own. Small hand-made inputs check the cycle rule, duplicates, revisions, serial boundaries, the status rules and sorting.
Robustness to the replacement data. The grader uses a second export with new problems, so the tests do not only check the real data. One test shuffles all rows, adds random case and spacing noise to part numbers, and asserts that every answer on the real data is identical. Together with the rule tests, this checks that answers follow the rules and not the order or formatting of the rows.
Cycles. Separate tests cover a cycle with one entry point (the rule applies cleanly), a cycle with two entry points (row order does not matter, the convention is pinned, and the case is reported), and 300 random graphs full of cycles. Each result must be a valid tree with every part reachable, and must not change when the rows are shuffled.

The HTTP tests start the real server on a free port and call every endpoint, including the error paths.

What I did not verify

I have no access to the hidden test set. If it contains a cycle with two entry points, the choice of dropped link follows the part-number convention described in point 3. The report will flag it. I did not check the page on a phone.