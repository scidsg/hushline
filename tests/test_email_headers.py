import io
import zipfile

from flask import url_for
from flask.testing import FlaskClient
import pytest
from pytest_mock import MockFixture

from hushline.email_headers import analyze_raw_email_headers


class _FakeTXTRecord:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return f'"{self._text}"'


class _FakeResolver:
    def __init__(self) -> None:
        self.timeout = 0.0
        self.lifetime = 0.0

    def resolve(self, qname: str, rdtype: str) -> list[_FakeTXTRecord]:
        assert qname == "selector1._domainkey.example.org"
        assert rdtype == "TXT"
        return [_FakeTXTRecord("v=DKIM1; k=rsa; p=MIIB12345")]


def test_analyze_raw_email_headers_extracts_auth_results_and_dkim_key(mocker: MockFixture) -> None:
    mocker.patch("hushline.email_headers.dns.resolver.Resolver", return_value=_FakeResolver())
    raw_headers = (
        "From: Alerts <alerts@example.org>\n"
        "Return-Path: <bounce@example.org>\n"
        "Reply-To: alerts@example.org\n"
        "Authentication-Results: mx.example.net; dkim=pass header.d=example.org; "
        "spf=pass smtp.mailfrom=example.org; dmarc=pass header.from=example.org\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; "
        "c=relaxed/relaxed; bh=abc123=; b=def456=\n"
    )

    report = analyze_raw_email_headers(raw_headers)

    assert report["from_domain"] == "example.org"
    assert report["auth_results"]["dkim"] == "pass"
    assert report["auth_results"]["spf"] == "pass"
    assert report["auth_results"]["dmarc"] == "pass"
    assert report["alignment"]["from_matches_any_dkim_domain"] is True
    assert report["dkim_key_lookups"][0]["status"] == "found"
    assert report["dkim_key_lookups"][0]["has_public_key"] is True
    assert report["executive_summary"]["verdict"] == "looks valid"


def test_email_headers_page_renders(client: FlaskClient) -> None:
    response = client.get(url_for("email_headers"), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


def test_email_headers_export_requires_authentication(client: FlaskClient) -> None:
    response = client.post(
        url_for("email_headers_evidence_zip"), data={"raw_headers": "From: x@y\n"}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("login"))


@pytest.mark.usefixtures("_authenticated_user")
def test_email_headers_page_renders_authenticated(
    client: FlaskClient,
) -> None:
    response = client.get(url_for("email_headers"))
    assert response.status_code == 200
    assert "Validate Raw Email Headers" in response.text
    assert "Tools" in response.text
    assert "Vision Assistant" in response.text
    assert "Download Report" not in response.text
    assert 'aria-current="page"' in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_email_headers_post_without_dkim_still_reports_auth_results(
    client: FlaskClient,
) -> None:
    raw_headers = (
        "From: Person <person@example.org>\n"
        "Authentication-Results: mx.example.net; spf=neutral; dmarc=fail\n"
    )
    response = client.post(
        url_for("email_headers"),
        data={"raw_headers": raw_headers},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Validation Summary" in response.text
    assert "Email Summary" in response.text
    assert "Download Report" in response.text
    assert "⚠️ This email appears inauthentic." in response.text
    assert "No DKIM-Signature headers were found." in response.text
    assert "SPF result is neutral." in response.text
    assert "DMARC result is fail." in response.text


def test_analyze_raw_email_headers_marks_likely_forged_on_triple_fail() -> None:
    raw_headers = (
        "From: Person <person@example.org>\n"
        "Authentication-Results: mx.example.net; dkim=fail; spf=fail; dmarc=fail\n"
    )
    report = analyze_raw_email_headers(raw_headers)
    assert report["executive_summary"]["verdict"] == "likely forged"


@pytest.mark.usefixtures("_authenticated_user")
def test_email_headers_export_zip_contains_evidence_artifacts(
    client: FlaskClient, mocker: MockFixture
) -> None:
    mocker.patch("hushline.email_headers.dns.resolver.Resolver", return_value=_FakeResolver())
    raw_headers = (
        "From: Alerts <alerts@example.org>\n"
        "Authentication-Results: mx.example.net; dkim=pass header.d=example.org\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; "
        "c=relaxed/relaxed; bh=abc123=; b=def456=\n"
    )
    response = client.post(
        url_for("email_headers_evidence_zip"),
        data={"raw_headers": raw_headers},
    )
    assert response.status_code == 200
    assert response.mimetype == "application/zip"

    archive = zipfile.ZipFile(io.BytesIO(response.data))
    names = set(archive.namelist())
    assert "raw-headers.txt" in names
    assert "report.json" in names
    assert "report.pdf" in names
    assert "checksums.sha256" in names
    assert "dkim-keys/selector1._domainkey.example.org.txt" in names
