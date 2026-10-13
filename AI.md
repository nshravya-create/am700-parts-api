## Claude (Anthropic)

I used Claude in a chat conversation to help with this assignment. What it was used for:

* **Reading the brief and the data.** I asked it to unzip the data folder and profile the three CSV files. The profiling
scripts (duplicates, whitespace, cycles, missing parts) were written by it and run in a sandbox. I checked their results
against the brief's worked example.
* **Writing the catalogue module** (`app/catalogue.py`). The cleaning steps and the rules follow Appendix Q. Claude proposed
the depth-first cycle removal, the conservative service rules and the decision to precompute everything at startup.
* **Writing the HTTP layer and the page** (`app/server.py`, `app/static/index.html`).
* **Writing the tests** (`tests/`), including the worked example and the shuffle-and-noise test.
* **Drafting DATA.md, NOTES.md, README.md and this file.** I checked each claim against the code and the measured counts,
and I corrected several statements that overstated what the data contains.

I reviewed the code and ran the tests. I have not used FastAPI or any other framework in this submission, because the
standard library version was the one I could run and test in the time available.


* The decisions in DATA.md and NOTES.md are the ones I agree with after checking the evidence, and I am responsible for them.
* The final submission (GitHub repository, collaborator invite and form) is done by me.

