"""Entry point: python3 -m app"""
import os
import sys
from pathlib import Path

from .catalogue import ROOT_PART, CatalogueError, load_catalogue
from .server import make_server

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    data_dir = Path(os.environ.get("DATA_DIR", REPO_ROOT / "data"))
    port = int(os.environ.get("PORT", "8000"))
    try:
        catalogue = load_catalogue(data_dir, root=ROOT_PART)
    except CatalogueError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        return 1
    print(catalogue.report.summary(), flush=True)
    server = make_server(catalogue, host="0.0.0.0", port=port)
    print(f"Serving on http://localhost:{port}  (ready)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
