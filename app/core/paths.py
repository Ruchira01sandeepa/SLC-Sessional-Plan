"""Where the app's files live. Every module finds static files, data and templates through these paths,
so a module can move between packages without breaking a file path."""
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]          # app/
ROOT_DIR = APP_DIR.parent                              # the project folder
STATIC_DIR = APP_DIR / "static"                        # the web UI (served at /ui)
BRAND_DIR = STATIC_DIR / "brand"                       # logo and icon
DATA_DIR = APP_DIR / "data"                            # exercise library (built by scripts/dev/build_exercise_library.py)
TEMPLATES_DIR = ROOT_DIR / "templates"                 # the PDP workbooks the seeder reads
