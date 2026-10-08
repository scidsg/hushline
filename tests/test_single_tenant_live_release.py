"""A customer rollout follows a successful published production release only."""

from copy import deepcopy
from typing import Any

import pytest
from pytest_mock import MockFixture

from scripts.single_tenant_live_release import Release, production_version, resolve, validate_target

SHA = "1" * 40
TAG = "v0.7.27"


def evidence() -> list[dict[str, Any]]:
    return [
        {"tag_name": TAG, "draft": False, "prerelease": False},
        {"sha": SHA, "commit": {"verification": {"verified": True}}},
        {"status": "ahead"},
        {
            "workflow_runs": [
                {
                    "head_sha": SHA,
                    "head_branch": TAG,
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "head_repository": {"full_name": "scidsg/hushline"},
                }
            ]
        },
    ]


def test_resolves_actual_production_release_not_newest_tag(mocker: MockFixture) -> None:
    mocker.patch("scripts.single_tenant_live_release.production_version", return_value=TAG)
    document = mocker.Mock(side_effect=evidence())
    assert resolve("https://tips.hushline.app", document) == Release(TAG, SHA)
    assert document.call_args_list[0].args[0].endswith("releases/tags/" + TAG)


@pytest.mark.parametrize(
    "bad",
    [
        "draft",
        "prerelease",
        "unsigned",
        "foreign_history",
        "failed_build",
        "other_tag",
        "other_repo",
    ],
)
def test_rejects_unapproved_release(mocker: MockFixture, bad: str) -> None:
    mocker.patch("scripts.single_tenant_live_release.production_version", return_value=TAG)
    values = deepcopy(evidence())
    if bad in {"draft", "prerelease"}:
        values[0][bad] = True
    elif bad == "unsigned":
        values[1]["commit"]["verification"]["verified"] = False
    elif bad == "foreign_history":
        values[2]["status"] = "diverged"
    elif bad == "failed_build":
        values[3]["workflow_runs"][0]["conclusion"] = "failure"
    elif bad == "other_tag":
        values[3]["workflow_runs"][0]["head_branch"] = "v0.7.28"
    else:
        values[3]["workflow_runs"][0]["head_repository"]["full_name"] = "foreign/hushline"
    with pytest.raises(ValueError, match="release|history|build"):
        resolve("https://tips.hushline.app", mocker.Mock(side_effect=values))


def test_private_release_target_is_exact_and_bounded() -> None:
    target = {"tag": TAG, "source_sha": SHA, "build_sha": "2" * 40, "previous_sha": "3" * 40}
    validate_target(target)
    with pytest.raises(ValueError, match="target"):
        validate_target({**target, "tag": "latest"})
    with pytest.raises(ValueError, match="target"):
        validate_target({**target, "extra": True})


@pytest.mark.parametrize(
    "origin",
    [
        "http://tips.hushline.app",
        "https://other.foo",
        "https://user@tips.hushline.app",
        "https://tips.hushline.app/private",
    ],
)
def test_release_discovery_never_contacts_an_unapproved_origin(
    origin: str, mocker: MockFixture
) -> None:
    session = mocker.patch("scripts.single_tenant_live_release.requests.Session")
    with pytest.raises(ValueError, match="production portal"):
        production_version(origin)
    session.assert_not_called()


@pytest.mark.parametrize("failure", [None, "redirect", "oversized"])
def test_release_discovery_uses_bounded_nonredirecting_production_login(
    mocker: MockFixture, failure: str | None
) -> None:
    session = mocker.patch("scripts.single_tenant_live_release.requests.Session")
    client = session.return_value.__enter__.return_value
    response = client.get.return_value.__enter__.return_value
    response.status_code = 302 if failure == "redirect" else 200
    response.iter_content.return_value = [
        b"x" * 262145
        if failure == "oversized"
        else b'<a href="https://github.com/scidsg/hushline">v0.7.27</a>'
    ]
    if failure:
        with pytest.raises(ValueError, match="unavailable|bound"):
            production_version("https://tips.hushline.app")
    else:
        assert production_version("https://tips.hushline.app") == TAG
    client.get.assert_called_once_with(
        "https://tips.hushline.app/login", timeout=(5, 20), allow_redirects=False, stream=True
    )
    assert client.trust_env is False
