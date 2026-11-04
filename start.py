"""Single standard-library entry point; application dependencies run inside Docker."""
from modules.orchestration import main


if __name__ == "__main__":
    raise SystemExit(main())
