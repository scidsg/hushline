import random
import string
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple, TypeVar

from bs4 import BeautifulSoup
from flask import url_for
from flask.testing import FlaskClient
from wtforms import FieldList, FormField, SubmitField

T = TypeVar("T")


def one_of(xs: Sequence[T], predicate: Callable[[T], bool]) -> T:
    matches = [x for x in xs if predicate(x)]
    match len(matches):
        case 1:
            return matches[0]
        case 0:
            raise ValueError("No matches")
        case _:
            raise ValueError(f"Too many matches: {matches}")


def random_bool() -> bool:
    return bool(random.getrandbits(1))


def random_optional_bool() -> Optional[bool]:
    if random_bool():
        return None
    return random_bool()


def random_string(length: int) -> str:
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


def random_optional_string(length: int) -> Optional[str]:
    if random_bool():
        return None
    return random_string(length)


def format_param_dict(params: Mapping[str, Any]) -> Tuple[str, str]:
    return (", ".join(params.keys()), ", ".join(f":{x}" for x in params))


def _field_to_data(field: Any, submit_name: str | None) -> dict[str, Any]:
    if isinstance(field, FormField):
        return form_to_data(field.form, submit_name=submit_name)

    if isinstance(field, FieldList):
        data: dict[str, Any] = {}
        for entry in field.entries:
            if isinstance(entry, FormField):
                data.update(form_to_data(entry.form, submit_name=submit_name))
            else:
                data[entry.name] = entry.data
        return data

    if isinstance(field, SubmitField) and submit_name is not None and field.name != submit_name:
        return {}

    return {field.name: field.data}


def form_to_data(form: Any, submit_name: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in form:
        data.update(_field_to_data(field, submit_name))
    return data


class Missing:
    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return True


# ridiculous formatting because `ruff` won't allow `not (x == y)`
assert (Missing() == Missing()) ^ bool("x")
assert Missing() != Missing()


def get_captcha_from_session_register(client: FlaskClient) -> str:
    """Retrieve the CAPTCHA answer from the session."""
    # Simulate loading the registration page to generate the CAPTCHA
    response = client.get(url_for("register"))
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer, "CAPTCHA answer not found in session"
        return captcha_answer


def get_captcha_from_session_password_reset(client: FlaskClient) -> str:
    response = client.get(url_for("request_password_reset"))
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer, "CAPTCHA answer not found in session"
        return captcha_answer


def get_captcha_from_session(client: FlaskClient, username: str) -> str:
    # Simulate loading the profile page to generate and retrieve the CAPTCHA from the session
    response = client.get(url_for("profile", username=username))
    assert response.status_code == 200

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer
        return captcha_answer


def get_profile_submission_data(client: FlaskClient, username: str) -> dict[str, str]:
    response = client.get(url_for("profile", username=username))
    assert response.status_code == 200

    soup = BeautifulSoup(response.data, "html.parser")
    nonce_input = soup.find("input", attrs={"name": "owner_guard_nonce"})
    signature_input = soup.find("input", attrs={"name": "owner_guard_signature"})
    assert nonce_input is not None
    assert signature_input is not None

    nonce = nonce_input.get("value")
    signature = signature_input.get("value")
    assert nonce
    assert signature

    with client.session_transaction() as session:
        captcha_answer = session.get("math_answer")
        assert captcha_answer

    return {
        "owner_guard_nonce": str(nonce),
        "owner_guard_signature": str(signature),
        "captcha_answer": str(captcha_answer),
    }
