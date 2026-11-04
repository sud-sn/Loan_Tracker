"""Write the OpenAPI document used to generate the typed frontend client.

    python -m app.export_openapi > openapi.json
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("LT_ENV", "development")


def main() -> None:
    from app.main import create_app

    json.dump(create_app().openapi(), sys.stdout, indent=1, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
