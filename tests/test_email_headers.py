import io
import json
import zipfile
from datetime import UTC, datetime

import dns.exception
import dns.resolver
import pytest
from flask import url_for
from flask.testing import FlaskClient
from pytest_mock import MockFixture

from hushline import email_headers
from hushline.email_headers import analyze_raw_email_headers, create_evidence_zip


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


class _RaisingResolver:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.timeout = 0.0
        self.lifetime = 0.0

    def resolve(self, qname: str, rdtype: str) -> list[_FakeTXTRecord]:
        assert qname == "selector1._domainkey.example.org"
        assert rdtype == "TXT"
        raise self._exc


def test_analyze_raw_email_headers_extracts_auth_results_and_dkim_key(mocker: MockFixture) -> None:
    mocker.patch("hushline.email_headers.dns.resolver.Resolver", return_value=_FakeResolver())
    raw_headers = (
        "From: Alerts <alerts@example.org>\n"
        "Return-Path: <bounce@example.org>\n"
        "Reply-To: alerts@example.org\n"
        "Authentication-Results: mx.example.net; dkim=pass header.d=example.org; "
        "spf=pass smtp.mailfrom=example.org; dmarc=pass header.from=example.org\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; "
        "c=relaxed/relaxed; h=from:subject:sender; bh=abc123=; b=def456=\n"
    )

    report = analyze_raw_email_headers(raw_headers)

    assert report["from_domain"] == "example.org"
    assert report["auth_results"]["dkim"] == "pass"
    assert report["auth_results"]["spf"] == "pass"
    assert report["auth_results"]["dmarc"] == "pass"
    assert report["alignment"]["from_matches_any_dkim_domain"] is True
    assert report["dkim_key_lookups"][0]["status"] == "found"
    assert report["dkim_key_lookups"][0]["has_public_key"] is True
    assert report["dkim_key_lookups"][0]["dnssec_validated"] is False
    assert report["dkim_overview"]["key_advertised_in_dns"] is True
    assert report["dkim_signatures"][0]["signed_headers"] == ["from", "subject", "sender"]
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
    assert "Email Validation" in response.text
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
    assert "Header Context" in response.text
    assert "Validation Summary" in response.text
    assert "Chain of Trust" in response.text
    assert "Download Report" in response.text
    assert "⚠️ This email might not be from the stated sender." in response.text
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
    assert (
        report["executive_summary"]["headline"]
        == "🚨 This email likely did not originate from the stated sender."
    )


def test_analyze_raw_email_headers_marks_valid_on_spf_dmarc_pass_without_dkim() -> None:
    raw_headers = (
        "From: Notifications <notifications@hushline.app>\n"
        "Return-Path: <notifications@hushline.app>\n"
        "Authentication-Results: mx.example.net; spf=pass smtp.mailfrom=hushline.app; "
        "dmarc=pass header.from=hushline.app\n"
    )

    report = analyze_raw_email_headers(raw_headers)
    assert report["executive_summary"]["verdict"] == "looks valid"
    assert (
        report["executive_summary"]["headline"]
        == "✅ This email appears to originate from the stated sender."
    )


def test_analyze_raw_email_headers_marks_appears_inauthentic() -> None:
    raw_headers = (
        "From: Person <person@example.org>\n"
        "Authentication-Results: mx.example.net; spf=neutral; dmarc=fail\n"
    )

    report = analyze_raw_email_headers(raw_headers)
    assert report["executive_summary"]["verdict"] == "appears inauthentic"
    assert (
        report["executive_summary"]["headline"]
        == "⚠️ This email might not be from the stated sender."
    )


def test_analyze_raw_email_headers_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="No email headers detected"):
        analyze_raw_email_headers("")


def test_analyze_raw_email_headers_with_header_body_mix_parses_headers_only() -> None:
    raw_email = (
        "From: Reporter <reporter@example.org>\n"
        "Authentication-Results: mx.example.net; dkim=pass; spf=pass; dmarc=pass\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; bh=abc=; b=def=\n"
        "\n"
        "This is message body content and should not affect header parsing.\n"
    )
    report = analyze_raw_email_headers(raw_email)
    assert report["from_domain"] == "example.org"
    assert report["auth_results"]["dkim"] == "pass"


def test_analyze_raw_email_headers_warns_on_unparseable_from_and_incomplete_dkim() -> None:
    raw_headers = (
        "From: not-an-address\n"
        "Authentication-Results: mx.example.net; dkim=fail\n"
        "DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; bh=abc=; b=def=\n"
    )
    report = analyze_raw_email_headers(raw_headers)
    assert "From header does not contain a parseable email domain." in report["warnings"]
    assert "DKIM signature found, but selector/domain tags were incomplete." in report["warnings"]
    assert "DKIM did not show a pass result in Authentication-Results." in report["warnings"]
    assert report["dkim_key_lookups"] == []


@pytest.mark.parametrize(
    ("raised", "expected_status", "expected_error_snippet"),
    [
        (dns.resolver.NXDOMAIN(), "not_found", "No DKIM key found"),
        (dns.resolver.NoAnswer(), "error", "DNS lookup failed: NoAnswer"),
        (dns.resolver.NoNameservers(), "error", "DNS lookup failed: NoNameservers"),
        (dns.exception.Timeout(), "error", "DNS lookup failed: Timeout"),
        (dns.exception.DNSException("boom"), "error", "DNS error: DNSException"),
    ],
)
def test_analyze_raw_email_headers_handles_dns_lookup_errors(
    mocker: MockFixture, raised: Exception, expected_status: str, expected_error_snippet: str
) -> None:
    mocker.patch(
        "hushline.email_headers.dns.resolver.Resolver", return_value=_RaisingResolver(raised)
    )
    raw_headers = (
        "From: Alerts <alerts@example.org>\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; bh=abc=; b=def=\n"
    )

    report = analyze_raw_email_headers(raw_headers)
    lookup = report["dkim_key_lookups"][0]
    assert lookup["status"] == expected_status
    assert expected_error_snippet in (lookup["error"] or "")


def test_create_evidence_zip_contains_pdf_json_and_valid_checksums(mocker: MockFixture) -> None:
    mocker.patch("hushline.email_headers.dns.resolver.Resolver", return_value=_FakeResolver())
    raw_headers = (
        "From: Alerts <alerts@example.org>\n"
        "Authentication-Results: mx.example.net; dkim=pass header.d=example.org\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; "
        "h=from:subject:sender; bh=abc=; b=def=\n"
    )

    archive = zipfile.ZipFile(io.BytesIO(create_evidence_zip(raw_headers)))
    report_json = json.loads(archive.read("report.json").decode("utf-8"))
    report_pdf = archive.read("report.pdf")
    report_pdf_text = report_pdf.decode("latin-1", errors="ignore")
    checksums = archive.read("checksums.sha256").decode("utf-8")

    assert report_json["from_domain"] == "example.org"
    assert report_json["executive_summary"]["headline"]
    assert report_json["interpretation"]["auth_results"]
    assert report_pdf.startswith(b"%PDF-1.4")
    assert "Validation Summary:" in report_pdf_text
    assert "Chain of Trust:" in report_pdf_text
    assert "Header Context:" in report_pdf_text
    assert "DKIM Signatures:" in report_pdf_text
    assert "signed_headers=from, subject" in report_pdf_text
    assert (
        "DKIM indicates the message was signed by a key linked to the signing domain."
        in report_pdf_text
    )
    assert "report.json" in checksums
    assert "report.pdf" in checksums


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


@pytest.mark.usefixtures("_authenticated_user")
def test_email_headers_post_invalid_form_shows_validation_flash(client: FlaskClient) -> None:
    response = client.post(
        url_for("email_headers"),
        data={"raw_headers": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Please paste valid raw headers before submitting." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_email_headers_post_value_error_shows_flash(
    client: FlaskClient, mocker: MockFixture
) -> None:
    mocker.patch(
        "hushline.routes.email_headers.analyze_raw_email_headers",
        side_effect=ValueError("No email headers detected. Paste the raw headers and try again."),
    )
    response = client.post(
        url_for("email_headers"),
        data={"raw_headers": "From: not-an-address\n"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "No email headers detected. Paste the raw headers and try again." in response.text


@pytest.mark.usefixtures("_authenticated_user")
def test_email_headers_export_invalid_form_redirects_with_flash(client: FlaskClient) -> None:
    response = client.post(
        url_for("email_headers_evidence_zip"),
        data={"raw_headers": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Could not generate report. Re-run validation first." in response.text


def test_parse_tag_value_pairs_ignores_invalid_parts_and_empty_keys() -> None:
    tags = email_headers._parse_tag_value_pairs("no-equals; =blank; s=selector1; d=example.org")
    assert tags == {"s": "selector1", "d": "example.org"}


def test_build_interpretation_includes_strong_chain_multiple_signatures_and_strong_keys() -> None:
    interpretation = email_headers._build_interpretation(
        {
            "auth_results": {"dkim": "pass", "spf": "pass", "dmarc": "pass"},
            "alignment": {
                "from_matches_return_path": True,
                "from_matches_any_dkim_domain": True,
            },
            "dkim_signatures": [
                {"domain": "example.org"},
                {"domain": "example.org"},
            ],
            "dkim_key_lookups": [
                {
                    "query_name": "selector1._domainkey.example.org",
                    "status": "found",
                    "has_public_key": True,
                    "dnssec_validated": True,
                }
            ],
            "dkim_overview": {"key_advertised_in_dns": True, "dnssec_validated": True},
            "from_domain": "example.org",
            "warnings": [],
        }
    )
    assert any("DNS evidence is strong" in line for line in interpretation["auth_chain"])
    assert any(
        "DNSSEC validation strengthens confidence" in line for line in interpretation["auth_chain"]
    )
    assert any(
        "Multiple DKIM signatures may reflect forwarding/list handling or layered signing." in line
        for line in interpretation["dkim_signatures"]
    )
    assert any(
        "Key lookup corroboration is strong for current DNS state." in line
        for line in interpretation["dkim_keys"]
    )


def test_render_minimal_pdf_renders_when_no_lines_provided() -> None:
    pdf = email_headers._render_minimal_pdf([])
    assert pdf.startswith(b"%PDF-1.4")


def test_render_report_pdf_includes_none_sections_and_warnings_block() -> None:
    report = {
        "executive_summary": {
            "headline": "⚠️ This email might not be from the stated sender.",
            "reasons": [],
        },
        "dkim_overview": {"key_advertised_in_dns": False, "dnssec_validated": False},
        "interpretation": {
            "auth_chain": [],
            "header_context": [],
            "auth_results": [],
            "dkim_signatures": [],
            "dkim_keys": [],
            "warnings": ["Treat this result cautiously."],
        },
        "from_header": "",
        "return_path_header": "",
        "reply_to_header": "",
        "from_domain": None,
        "return_path_domain": None,
        "reply_to_domain": None,
        "alignment": {"from_matches_return_path": False, "from_matches_any_dkim_domain": False},
        "auth_results": {},
        "dkim_signatures": [],
        "dkim_key_lookups": [],
        "warnings": ["DKIM did not show a pass result in Authentication-Results."],
        "note": "Note.",
    }
    pdf_text = email_headers._render_report_pdf(report, datetime.now(UTC)).decode(
        "latin-1", errors="ignore"
    )
    assert "DKIM Signatures:" in pdf_text
    assert "  None" in pdf_text
    assert "DKIM Key Lookups:" in pdf_text
    assert "Warnings:" in pdf_text
    assert "DKIM did not show a pass result in Authentication-Results." in pdf_text
    assert "Treat this result cautiously." in pdf_text


def test_create_evidence_zip_includes_lookup_error_details(mocker: MockFixture) -> None:
    mocker.patch(
        "hushline.email_headers.dns.resolver.Resolver",
        return_value=_RaisingResolver(dns.resolver.NoAnswer()),
    )
    raw_headers = (
        "From: Alerts <alerts@example.org>\n"
        "DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=selector1; bh=abc=; b=def=\n"
    )
    archive = zipfile.ZipFile(io.BytesIO(create_evidence_zip(raw_headers)))
    dkim_key_details = archive.read("dkim-keys/selector1._domainkey.example.org.txt").decode(
        "utf-8"
    )
    assert "status: error" in dkim_key_details
    assert "error: DNS lookup failed: NoAnswer" in dkim_key_details
