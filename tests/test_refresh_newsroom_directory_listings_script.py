from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "refresh_newsroom_directory_listings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "refresh_newsroom_directory_listings", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_serialize_rows_is_deterministic_without_node_tooling() -> None:
    module = _load_module()

    rows = [
        {
            "id": "newsroom-sample",
            "slug": "newsroom~sample",
            "name": "Sample Newsroom",
            "languages": ["English", "Spanish"],
        }
    ]

    serialized = module._serialize_rows(rows)

    assert serialized == json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
