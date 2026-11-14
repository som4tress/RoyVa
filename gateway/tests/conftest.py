"""Tests must not depend on the live dry-run flag (runtime/gateway/dry_run exists while the owner rehearses): point it at a file that never exists.
Modules read ROYVA_DRY_RUN_FLAG when imported, so this runs before any test module loads."""
import os

os.environ["ROYVA_DRY_RUN_FLAG"] = "/nonexistent/royva-dry-run-flag"
os.environ.pop("ROYVA_DRY_RUN", None)
