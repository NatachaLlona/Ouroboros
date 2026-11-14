"""Single entry point for Basic PostgreSQL + HTTPS API and PostgreSQL-only mode."""

import sys as _sys
from pathlib import Path as _Path
_repository = _Path(__file__).resolve().parents[0]
_sys.path.insert(0, str(_repository))
_sys.path.insert(0, str(_repository / "modules"))
import sys
from pathlib import Path
from database.runtime import main as database_main


def main():
    arguments=sys.argv[1:] or ['--with-api']
    if '--help' in arguments or '-h' in arguments:
        print('Usage: python start.py [--database-only | --with-api | --api-inspect | --api-migrate] [--check]')
        print('--database-only  Start or resume PostgreSQL only.')
        print('--with-api       Start PostgreSQL and HTTPS API in the ouroboros project (default).')
        print('--api-inspect    Inspect the live contract using the existing interactive SQL master password.')
        print('--api-migrate    Prepare the runtime SQL login with additive API migrations.')
        print('--check          Validate the selected module configuration without SQL or Docker changes.')
        return 0
    api_modes={'--with-api','--api-migrate','--api-inspect'}
    selected=api_modes.intersection(arguments)
    if selected:
        if len(selected)>1 or '--database-only' in arguments or set(arguments)-api_modes-{'--check'}:
            print('Choose one API mode or --database-only; incompatible startup options were rejected.',file=sys.stderr)
            return 1
        from api.service.launcher import main as api_main
        return api_main(Path(__file__).resolve().parent,arguments)
    return database_main()


if __name__ == "__main__":
    raise SystemExit(main())
