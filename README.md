# AM-700 service parts catalogue API

Serves the parts tree of the AM-700 bottling line (`AS-40000` and everything inside it),
built by reconciling three files from three systems: the BOM, the parts master and the service list.

## Run it

Needs Python 3.10 or newer. There are no third-party packages, so there is nothing to install.

```
python3 -m app
```

On Windows, use `python` instead of `python3` in every command in this file.

The service listens on port 8000. Open http://localhost:8000/ for the page, or call the API.
To use another port, set `PORT`: `PORT=8080 python3 -m app`.
To read another data folder, set `DATA_DIR`. By default it reads `data/` at the repo root.

The service loads and checks the data at startup, then answers requests using the in-memory catalogue. It makes no network calls.

Check it is up: `curl localhost:8000/health` returns `{"status": "ok"}`.

## Run the tests

```
python3 -m unittest discover -s tests -t . -v
```

The tests need no network. They include the worked example from Appendix Q with its exact
answers, the rules on their own, checks on the real data folder, and HTTP tests against the running server.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/api/validation` | counts of parts in the machine, ready, missing, not_replaceable |
| GET | `/api/parts/{part_number}` | description, revision, status, total quantity, parents, children |
| GET | `/api/parts/{part_number}/paths` | every path from `AS-40000` to the part, sorted |
| GET | `/api/serial/{serial}` | number of ready parts that apply to that serial |
| GET | `/` | a page where you can try the endpoints |

Part numbers are not case-sensitive and ignore spaces: `/api/parts/fa-30019` works.
A part that is not in the machine returns 404. A serial that is not a whole number returns 400.

## Where things are

- `app/catalogue.py`: loading, cleaning, the graph, and all the catalogue rules.
- `app/server.py`: HTTP routes. Standard library only.
- `app/static/index.html`: the page at `/`.
- `data/`: the three CSV files.
- `tests/`: unit tests, data tests and HTTP tests.
- `DATA.md`: what was wrong in the data and what was decided. `NOTES.md`: decisions and cuts. `AI.md`: AI tools used.
