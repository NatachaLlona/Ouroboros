"""Explicit per-workspace Compose identity; never infer Foundation for a copy."""
from pathlib import Path
import re
from app.config import ConfigurationError, PROJECT_ROOT


def require_infrastructure(config, root=PROJECT_ROOT):
    settings = config.get("infrastructure", {})
    project = settings.get("project_name", "")
    if not isinstance(project, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise ConfigurationError("infrastructure.project_name must be an explicit unique lowercase Compose name (1-63 letters, digits, underscores, or hyphens)")
    workspace = settings.get("workspace", "")
    if not isinstance(workspace, str):
        raise ConfigurationError("infrastructure.workspace must be a string")
    root = Path(root).resolve()
    if workspace and (not Path(workspace).is_absolute() or Path(workspace).resolve() != root):
        raise ConfigurationError("Infrastructure configuration belongs to another workspace; choose a unique project_name and fresh local configuration/secrets for this copy")
    settings["workspace"] = str(root)
    return project


def receipt_matches(root, project):
    import json
    from app.database import DatabaseError
    path = Path(root) / ".secrets/infrastructure_identity.json"
    if not path.exists():
        return False
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt != {"project_name": project, "workspace": str(Path(root).resolve())}:
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise DatabaseError("Infrastructure ownership receipt belongs to another project/workspace or is invalid; use fresh local configuration and secrets for a derived project") from None
    return True


def record_ownership(root, project):
    import json
    from app.database import DatabaseError
    if receipt_matches(root, project):
        return
    path = Path(root) / ".secrets/infrastructure_identity.json"
    try:
        path.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as target:
                json.dump({"project_name": project, "workspace": str(Path(root).resolve())}, target)
                target.write("\n")
        except FileExistsError:
            receipt_matches(root, project)
    except OSError:
        raise DatabaseError("Unable to record workspace ownership; check local metadata permissions") from None
