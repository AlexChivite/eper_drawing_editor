from __future__ import annotations

import importlib
from typing import Any


__all__ = ["process_pdf", "process_pdf_with_changes"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    processor = importlib.import_module(".processor", __name__)
    return getattr(processor, name)
