from typing import Callable, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")


def if_not_none(
    value: Optional[T], func: Callable[[T], U], allow_falsey: bool = True
) -> Optional[U]:
    if allow_falsey:
        if value is not None:
            return func(value)
    elif value:
        return func(value)
    return None


def parse_bool(val: str) -> bool:
    match val:
        case "true":
            return True
        case "false":
            return False
    raise ValueError(f"Unparseable boolean value: {val!r}")
