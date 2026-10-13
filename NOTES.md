Decisions:

Standard library only, no FastAPI : The brief says Python with FastAPI is a sensible default, but any stack is allowed. A zero-dependency service removes the install step, which is the most likely way a clean-machine start fails. The HTTP layer is about 100 lines, and it is the part I would swap first if the team wants a framework.
Everything is computed once, at startup : The graph and catalogue are built when the service starts. Requests only read the finished tables, so answers take well under a millisecond.
Cycle handling by depth-first walk : The edge that points back up from inside the machine is removed, and only that edge. It is reported at startup. Where two branches lead into the same cycle, the brief gives no rule. The code follows part-number order, which is deterministic, and reports the case. Row order never changes the result.
Conservative on service rules : A part is ready only if every service row for it says Y and every serial range is valid. Anything less certain is not_replaceable.
Fail loudly on bad structure : A missing file or missing column stops startup with a clear message. Bad rows inside a good file are skipped and counted, not hidden.

What I cut:

Authentication, rate limiting and caching: none is needed for read-only lookups that take well under a millisecond.
Part descriptions in other languages, and the unit cost column: the brief does not ask for them.
A file upload page: none of the endpoints takes a file, so the page takes text input.
Packaging (a pyproject.toml, a Dockerfile): one command is enough for the brief.

What I would do next:

Settle the multi-entry cycle rule with the data owners. Right now it follows part-number order, which is arbitrary. A structural rule, such as the shortest path from the top, would still need a tie-break, so the real answer has to come from them.
Replace the startup-only load with a file watcher or an explicit reload endpoint, so a new export does not need a restart. I did not build it, because the grader starts the service fresh on a clean copy.
Add a /api/parts/{pn}/where-used endpoint for the reverse question, and a check that the data is internally consistent (every service row has a parts master row) that fails the build.
Ask the data owners why 25 machine parts are missing from the parts master, and why AS-40209 lists AS-40002 as a child.