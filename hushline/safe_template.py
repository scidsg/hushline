import re
from typing import Mapping, Optional

VARIABLE_SYNTAX = re.compile("^[a-zA-Z_][a-zA-Z0-9_]*$")
VAR_START = "{{"
VAR_END = "}}"


class TemplateError(Exception):
    def __init__(self, details: str) -> None:
        super().__init__("There was an error in your template. " + details)
        self._details = details


def safe_render_template(template_string: str, variables: Mapping[str, Optional[str]]) -> str:
    for name, value in variables.items():
        if not VARIABLE_SYNTAX.search(name):
            raise TemplateError(f"Variable with invalid syntax: {name}")
        if not isinstance(value, str) and value is not None:
            # not a template error. this is us making a mistake. don't show to user.
            raise ValueError(f"Variable {name} was not a string: {value}")

    out = ""

    while template_string:
        var_start_idx = template_string.find(VAR_START)

        # no variables, so just append the remaining string
        if var_start_idx < 0:
            if template_string.find(VAR_END) >= 0:
                raise TemplateError("Invalid syntax. Extra variable substitution braces.")

            out += template_string
            break

        if var_start_idx != 0:
            out += template_string[0:var_start_idx]

        var_end_idx = template_string.find(VAR_END)
        if var_end_idx < 0:
            raise TemplateError("Invalid syntax. Variable substitution braces not closed.")

        var_name = template_string[var_start_idx + 2 : var_end_idx].strip()
        if var_name not in variables:
            raise TemplateError(f"Variable not defined: {var_name}")

        out += variables[var_name] or ""  # to account for None
        template_string = template_string[var_end_idx + 2 :]

    return out
