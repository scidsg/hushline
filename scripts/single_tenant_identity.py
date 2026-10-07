"""Provider identity syntax shared by read-only and privileged ownership checks."""

import re


def valid_team_id(value: object) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", value)
    )
