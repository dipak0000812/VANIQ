import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_vaniq_configured", False):
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)
    root._vaniq_configured = True  # type: ignore[attr-defined]
