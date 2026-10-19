"""Independent cleanup attempts with diagnostics that contain no exception messages."""
from app.log_safety import error_details


class ResourceCleanupError(RuntimeError):
    def __init__(self, failures):
        super().__init__("One or more resources could not be closed")
        self.failures = failures


def cleanup_actions(actions, report=None):
    failures = []
    for name, action in actions:
        if action is None:
            continue
        try:
            action()
        except BaseException as error:
            detail = {"resource": name, **error_details(error)}
            failures.append(detail)
            if report is not None:
                try:
                    report(detail)
                except BaseException:
                    # A broken reporter must not prevent subsequent cleanup attempts.
                    pass
    return failures
