import hashlib
import io
import json
import re
import textwrap
import zipfile
from datetime import UTC, datetime
from email.parser import HeaderParser
from email.utils import parseaddr
from typing import Any

import dns.exception
import dns.flags
import dns.resolver

_AUTH_RESULTS_RE = re.compile(r"\b(dkim|spf|dmarc)\s*=\s*([a-zA-Z0-9_-]+)")


def _parse_tag_value_pairs(value: str) -> dict[str, str]:
    tags: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip().lower()
        if not key:
            continue
        tags[key] = val.strip()
    return tags


def _domain_from_address(value: str) -> str | None:
    _, addr = parseaddr(value or "")
    if "@" not in addr:
        return None
    domain = addr.rsplit("@", 1)[1].strip().lower()
    return domain or None


def _extract_authentication_results(headers: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for header in headers:
        for match in _AUTH_RESULTS_RE.finditer(header):
            method = match.group(1).lower()
            verdict = match.group(2).lower()
            if method not in results:
                results[method] = verdict
    return results


def _lookup_dkim_key(
    selector: str, domain: str, resolver: dns.resolver.Resolver | None = None
) -> dict[str, Any]:
    resolver = resolver or dns.resolver.Resolver()
    resolver.lifetime = 3.0
    resolver.timeout = 3.0

    query_name = f"{selector}._domainkey.{domain}".strip(".")

    try:
        records = resolver.resolve(query_name, "TXT")
    except dns.resolver.NXDOMAIN:
        return {
            "selector": selector,
            "domain": domain,
            "query_name": query_name,
            "status": "not_found",
            "txt_records": [],
            "has_public_key": False,
            "dnssec_validated": False,
            "error": "No DKIM key found at this DNS name.",
        }
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        return {
            "selector": selector,
            "domain": domain,
            "query_name": query_name,
            "status": "error",
            "txt_records": [],
            "has_public_key": False,
            "dnssec_validated": False,
            "error": f"DNS lookup failed: {type(e).__name__}",
        }
    except dns.exception.DNSException as e:
        return {
            "selector": selector,
            "domain": domain,
            "query_name": query_name,
            "status": "error",
            "txt_records": [],
            "has_public_key": False,
            "dnssec_validated": False,
            "error": f"DNS error: {type(e).__name__}",
        }

    txt_records: list[str] = []
    has_public_key = False
    for record in records:
        txt = record.to_text().strip('"')
        txt_records.append(txt)
        tags = _parse_tag_value_pairs(txt)
        if tags.get("p"):
            has_public_key = True

    response = getattr(records, "response", None)
    dnssec_validated = bool(response and (response.flags & dns.flags.AD))

    return {
        "selector": selector,
        "domain": domain,
        "query_name": query_name,
        "status": "found",
        "txt_records": txt_records,
        "has_public_key": has_public_key,
        "dnssec_validated": dnssec_validated,
        "error": None,
    }


def _build_executive_summary(
    auth_results: dict[str, str],
    alignment: dict[str, bool],
    dkim_signatures: list[dict[str, Any]],
    warnings: list[str],
    from_domain: str | None,
) -> dict[str, Any]:
    dkim = auth_results.get("dkim", "not present")
    spf = auth_results.get("spf", "not present")
    dmarc = auth_results.get("dmarc", "not present")

    reasons: list[str] = []
    if dkim == "pass":
        reasons.append("DKIM passed in Authentication-Results.")
    if spf == "pass":
        reasons.append("SPF passed in Authentication-Results.")
    if dmarc == "pass":
        reasons.append("DMARC passed in Authentication-Results.")
    if alignment.get("from_matches_any_dkim_domain"):
        reasons.append("From domain aligns with a DKIM signing domain.")
    if alignment.get("from_matches_return_path"):
        reasons.append("From domain aligns with Return-Path domain.")
    if warnings:
        reasons.append("One or more warnings were detected in header checks.")

    strong_auth_failure = dkim == "fail" and spf == "fail" and dmarc == "fail"
    if strong_auth_failure and from_domain:
        return {
            "verdict": "likely forged",
            "headline": "🚨 This email likely did not originate from the stated sender.",
            "reasons": reasons or ["DKIM, SPF, and DMARC all failed in Authentication-Results."],
        }

    aligned = alignment.get("from_matches_any_dkim_domain") or alignment.get(
        "from_matches_return_path"
    )
    strong_auth_success = (
        dmarc == "pass"
        or (spf == "pass" and aligned)
        or (dkim == "pass" and alignment.get("from_matches_any_dkim_domain"))
    )
    if strong_auth_success and aligned and not warnings:
        return {
            "verdict": "looks valid",
            "headline": "✅ This email appears to originate from the stated sender.",
            "reasons": reasons or ["Key authentication checks passed and domains are aligned."],
        }

    return {
        "verdict": "appears inauthentic",
        "headline": "⚠️ This email might not be from the stated sender.",
        "reasons": reasons or ["Authentication checks are incomplete, conflicting, or weak."],
    }


def _build_interpretation(report: dict[str, Any]) -> dict[str, list[str]]:
    interpretation: dict[str, list[str]] = {}
    auth_results = report["auth_results"]
    alignment = report["alignment"]
    dkim_signatures = report["dkim_signatures"]
    dkim_key_lookups = report["dkim_key_lookups"]
    dkim_overview = report["dkim_overview"]
    from_domain = report["from_domain"]
    warnings = report["warnings"]

    has_dkim_key = dkim_overview["key_advertised_in_dns"]
    dnssec_ok = dkim_overview["dnssec_validated"]
    auth_chain_lines: list[str] = []
    if has_dkim_key and dnssec_ok:
        auth_chain_lines.append(
            "This DNS evidence is strong: a DKIM key is present and the DNS answer was "
            "DNSSEC-validated."
        )
    elif has_dkim_key:
        auth_chain_lines.append(
            "This DNS evidence is moderate: a DKIM key is present, but DNSSEC validation "
            "was not observed."
        )
    else:
        auth_chain_lines.append(
            "This DNS evidence is weak: no corroborating DKIM key was found in current DNS."
        )
    if has_dkim_key:
        auth_chain_lines.append(
            "A published DKIM key supports that the signing domain is configured for DKIM."
        )
    else:
        auth_chain_lines.append(
            "No DKIM key in current DNS means this lookup cannot independently corroborate "
            "the signer."
        )
    if dnssec_ok:
        auth_chain_lines.append(
            "DNSSEC validation strengthens confidence that this DNS answer was not tampered "
            "with in transit."
        )
    else:
        auth_chain_lines.append(
            "Without DNSSEC validation, treat DNS-based evidence as lower-confidence."
        )
    auth_chain_lines.append("Technical note: DNSSEC status is based on the resolver AD flag.")
    interpretation["auth_chain"] = auth_chain_lines

    align_rp = alignment["from_matches_return_path"]
    align_dkim = alignment["from_matches_any_dkim_domain"]
    header_lines: list[str] = []
    if from_domain and align_rp and align_dkim:
        header_lines.append("Header context is consistent with the stated sender identity.")
    elif from_domain and (align_rp or align_dkim):
        header_lines.append("Header context is mixed: some identity signals align, others do not.")
    elif from_domain:
        header_lines.append(
            "Header context is weak for sender identity due to domain misalignment."
        )
    else:
        header_lines.append(
            "Header context is incomplete because a parseable From domain is missing."
        )
    if from_domain:
        header_lines.append("A parseable From domain lets alignment checks be evaluated.")
    else:
        header_lines.append(
            "Without a parseable From domain, sender-identity interpretation is limited."
        )
    if align_rp and align_dkim:
        header_lines.append(
            "Consistent domain alignment supports that the visible sender identity matches "
            "authenticated paths."
        )
    elif align_rp or align_dkim:
        header_lines.append(
            "Partial alignment provides some support, but identity assurance is incomplete."
        )
    else:
        header_lines.append(
            "Misalignment raises spoofing risk, though forwarding or list services can also "
            "cause this pattern."
        )
    interpretation["header_context"] = header_lines

    dkim = auth_results.get("dkim", "not present")
    spf = auth_results.get("spf", "not present")
    dmarc = auth_results.get("dmarc", "not present")
    auth_results_lines: list[str] = []
    if dmarc == "pass":
        auth_results_lines.append(
            "DMARC pass is the strongest signal here because it requires aligned domain "
            "authentication."
        )
    elif dkim == "pass" or spf == "pass":
        auth_results_lines.append(
            "DKIM/SPF pass provides partial evidence, but without DMARC pass sender "
            "identity assurance is weaker."
        )
    else:
        auth_results_lines.append(
            "Missing or failing results across DKIM/SPF/DMARC materially reduce confidence "
            "in sender authenticity."
        )
    if dkim == "pass":
        auth_results_lines.append(
            "DKIM indicates the message was signed by a key linked to the signing domain."
        )
    if spf == "pass":
        auth_results_lines.append(
            "SPF indicates the sending server was authorized for the envelope sender domain."
        )
    if dkim != "pass" and spf != "pass" and dmarc != "pass":
        auth_results_lines.append(
            "Combined failures or missing values across these checks should be treated as "
            "high risk."
        )
    interpretation["auth_results"] = auth_results_lines

    sig_count = len(dkim_signatures)
    dkim_signature_lines: list[str] = []
    if sig_count > 1:
        dkim_signature_lines.append(
            "Multiple DKIM signatures may reflect forwarding/list handling or layered signing."
        )
    elif sig_count == 1:
        dkim_signature_lines.append(
            "A single DKIM signature provides one cryptographic signing path to evaluate."
        )
    if dkim_signatures:
        dkim_signature_lines.append(
            "A DKIM signature shows a signer took responsibility for selected headers at "
            "send time, but it does not by itself prove ownership of the visible From "
            "address."
        )
    else:
        dkim_signature_lines.append(
            "Without a DKIM-Signature header, there is no cryptographic DKIM evidence to evaluate."
        )
    if alignment["from_matches_any_dkim_domain"]:
        dkim_signature_lines.append(
            "From/DKIM domain alignment improves confidence that the visible sender matches "
            "the signer."
        )
    elif dkim_signatures:
        dkim_signature_lines.append(
            "From/DKIM misalignment weakens sender-identity confidence even when signatures exist."
        )
    interpretation["dkim_signatures"] = dkim_signature_lines

    lookup_count = len(dkim_key_lookups)
    dkim_key_lines: list[str] = []
    if (
        lookup_count > 0
        and dkim_overview["key_advertised_in_dns"]
        and dkim_overview["dnssec_validated"]
    ):
        dkim_key_lines.append("Key lookup corroboration is strong for current DNS state.")
    elif lookup_count > 0 and dkim_overview["key_advertised_in_dns"]:
        dkim_key_lines.append(
            "Key lookup corroboration is partial: key present, but without DNSSEC validation."
        )
    elif lookup_count > 0:
        dkim_key_lines.append("Key lookup corroboration is weak for current DNS state.")
    else:
        dkim_key_lines.append("No lookup corroboration is available from the provided DKIM fields.")
    if dkim_key_lookups and dkim_overview["key_advertised_in_dns"]:
        dkim_key_lines.append(
            "Current DNS corroborates that at least one DKIM public key is published for a "
            "detected signer."
        )
    elif dkim_key_lookups:
        dkim_key_lines.append(
            "Key lookups did not corroborate a usable DKIM key, which weakens present-day "
            "verification."
        )
    else:
        dkim_key_lines.append(
            "No key lookup means DNS evidence could not be checked from the provided signatures."
        )
    interpretation["dkim_keys"] = dkim_key_lines

    warning_lines: list[str] = []
    medium_warning_threshold = 2
    high_warning_threshold = 3
    if len(warnings) >= high_warning_threshold:
        warning_lines.append(
            "Multiple warning conditions are present, so treat authentication conclusions "
            "as low confidence."
        )
    elif len(warnings) == medium_warning_threshold:
        warning_lines.append(
            "Two warning conditions are present, so conclusions should be treated cautiously."
        )
    elif len(warnings) == 1:
        warning_lines.append(
            "One warning condition is present and should be reviewed before relying on the result."
        )
    if warnings:
        warning_lines.append(
            "These warnings indicate ambiguity or conflicting signals, so conclusions "
            "should be treated conservatively."
        )
    interpretation["warnings"] = warning_lines

    return interpretation


def analyze_raw_email_headers(raw_headers: str) -> dict[str, Any]:
    message = HeaderParser().parsestr(raw_headers or "")
    if not message.keys():
        raise ValueError("No email headers detected. Paste the raw headers and try again.")

    from_header = message.get("From", "")
    return_path_header = message.get("Return-Path", "")
    reply_to_header = message.get("Reply-To", "")

    from_domain = _domain_from_address(from_header)
    return_path_domain = _domain_from_address(return_path_header)
    reply_to_domain = _domain_from_address(reply_to_header)

    auth_results = _extract_authentication_results(message.get_all("Authentication-Results", []))
    dkim_headers = message.get_all("DKIM-Signature", [])

    dkim_signatures: list[dict[str, Any]] = []
    dkim_key_lookups: list[dict[str, Any]] = []
    for dkim_header in dkim_headers:
        tags = _parse_tag_value_pairs(dkim_header)
        selector = tags.get("s", "")
        domain = tags.get("d", "")
        signature = {
            "algorithm": tags.get("a", ""),
            "canonicalization": tags.get("c", ""),
            "selector": selector,
            "domain": domain,
            "query_name": f"{selector}._domainkey.{domain}" if selector and domain else None,
            "body_hash_present": bool(tags.get("bh")),
            "signature_present": bool(tags.get("b")),
            "signed_headers": [
                header.strip().lower() for header in tags.get("h", "").split(":") if header.strip()
            ],
        }
        dkim_signatures.append(signature)
        if selector and domain:
            dkim_key_lookups.append(_lookup_dkim_key(selector=selector, domain=domain))

    alignment = {
        "from_matches_return_path": bool(
            from_domain and return_path_domain and from_domain == return_path_domain
        ),
        "from_matches_any_dkim_domain": bool(
            from_domain
            and any(sig.get("domain", "").lower() == from_domain for sig in dkim_signatures)
        ),
    }

    warnings: list[str] = []
    if not from_domain:
        warnings.append("From header does not contain a parseable email domain.")
    if dkim_headers and not dkim_key_lookups:
        warnings.append("DKIM signature found, but selector/domain tags were incomplete.")
    if auth_results.get("dkim") not in {"pass", "bestguesspass"} and dkim_headers:
        warnings.append("DKIM did not show a pass result in Authentication-Results.")
    if auth_results.get("spf") and auth_results["spf"] != "pass":
        warnings.append(f"SPF result is {auth_results['spf']}.")
    if auth_results.get("dmarc") and auth_results["dmarc"] != "pass":
        warnings.append(f"DMARC result is {auth_results['dmarc']}.")

    executive_summary = _build_executive_summary(
        auth_results=auth_results,
        alignment=alignment,
        dkim_signatures=dkim_signatures,
        warnings=warnings,
        from_domain=from_domain,
    )

    found_key_lookups = [lookup for lookup in dkim_key_lookups if lookup["status"] == "found"]
    dkim_overview = {
        "key_advertised_in_dns": any(lookup["has_public_key"] for lookup in dkim_key_lookups),
        "dnssec_validated": bool(found_key_lookups)
        and all(lookup["dnssec_validated"] for lookup in found_key_lookups),
    }
    interpretation = _build_interpretation(
        {
            "auth_results": auth_results,
            "alignment": alignment,
            "dkim_signatures": dkim_signatures,
            "dkim_key_lookups": dkim_key_lookups,
            "dkim_overview": dkim_overview,
            "from_domain": from_domain,
            "warnings": warnings,
        }
    )

    return {
        "from_header": from_header,
        "return_path_header": return_path_header,
        "reply_to_header": reply_to_header,
        "from_domain": from_domain,
        "return_path_domain": return_path_domain,
        "reply_to_domain": reply_to_domain,
        "auth_results": auth_results,
        "dkim_signatures": dkim_signatures,
        "dkim_key_lookups": dkim_key_lookups,
        "dkim_overview": dkim_overview,
        "interpretation": interpretation,
        "alignment": alignment,
        "executive_summary": executive_summary,
        "warnings": warnings,
        "note": (
            "Header analysis improves confidence but cannot prove authenticity on its own. "
            "The visible From header is not the SMTP envelope sender (MAIL FROM), and that "
            "envelope value is often unavailable in pasted headers. "
            "Some providers can DKIM-sign the visible From header without proving mailbox "
            "ownership. "
            "Forwarding, mailing lists, and partial headers can alter results. "
            "For older email, DKIM keys may have rotated or been removed, so present-day DNS "
            "may not reflect the original signing state."
        ),
    }


def _safe_artifact_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return safe or "unknown"


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _render_minimal_pdf(lines: list[str]) -> bytes:
    page_height = 792
    top_margin = 50
    bottom_margin = 50
    line_height = 14
    max_lines = (page_height - top_margin - bottom_margin) // line_height

    pages: list[list[str]] = []
    current_page: list[str] = []
    for line in lines:
        wrapped = textwrap.wrap(str(line), width=95) or [""]
        for wrapped_line in wrapped:
            if len(current_page) >= max_lines:
                pages.append(current_page)
                current_page = []
            current_page.append(wrapped_line)
    if current_page:
        pages.append(current_page)
    if not pages:
        pages = [[""]]

    objects: list[bytes] = []
    page_object_numbers: list[int] = []

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [] /Count 0 >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_lines in pages:
        content_lines = ["BT", "/F1 11 Tf", f"40 {page_height - top_margin} Td"]
        for index, line in enumerate(page_lines):
            escaped = _pdf_escape(line)
            if index == 0:
                content_lines.append(f"({escaped}) Tj")
            else:
                content_lines.append(f"0 -{line_height} Td ({escaped}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("utf-8")

        content_obj_no = len(objects) + 1
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

        page_obj_no = len(objects) + 1
        page_object_numbers.append(page_obj_no)
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 {page_height}] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_no} 0 R >>"
            ).encode()
        )

    kids = " ".join(f"{obj_no} 0 R" for obj_no in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode()

    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(pdf.tell())
        pdf.write(f"{index} 0 obj\n".encode())
        pdf.write(obj)
        pdf.write(b"\nendobj\n")

    xref_start = pdf.tell()
    pdf.write(f"xref\n0 {len(offsets)}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.write(f"{offset:010d} 00000 n \n".encode())

    pdf.write(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n" f"startxref\n{xref_start}\n%%EOF\n"
        ).encode()
    )
    return pdf.getvalue()


def _render_report_pdf(report: dict[str, Any], created_at: datetime) -> bytes:
    lines = [
        "Hush Line - Email Header Validation Report",
        f"Generated (UTC): {created_at.isoformat()}",
        "",
        "Validation Summary:",
        f"  {report['executive_summary']['headline']}",
    ]
    for reason in report["executive_summary"]["reasons"]:
        lines.append(f"  - {reason}")

    lines.extend(
        [
            "",
            "Trust Chain:",
            (
                "  DKIM key advertised in DNS: "
                f"{'yes' if report['dkim_overview']['key_advertised_in_dns'] else 'no'}"
            ),
            (
                "  DKIM key validated via DNSSEC: "
                f"{'yes' if report['dkim_overview']['dnssec_validated'] else 'no'}"
            ),
            "  Summary:",
        ]
    )
    for line in report.get("interpretation", {}).get("auth_chain", []):
        lines.append(f"    - {line}")

    lines.extend(
        [
            "",
            "Header Context:",
            f"  From: {report.get('from_header', '')}",
            f"  Return-Path: {report.get('return_path_header', '')}",
            f"  Reply-To: {report.get('reply_to_header', '')}",
            f"  From domain: {report.get('from_domain') or 'not found'}",
            f"  Return-Path domain: {report.get('return_path_domain') or 'not found'}",
            f"  Reply-To domain: {report.get('reply_to_domain') or 'not found'}",
            (
                "  From/Return-Path alignment: "
                f"{'yes' if report['alignment']['from_matches_return_path'] else 'no'}"
            ),
            (
                "  From/DKIM alignment: "
                f"{'yes' if report['alignment']['from_matches_any_dkim_domain'] else 'no'}"
            ),
            "  Summary:",
        ]
    )
    for line in report.get("interpretation", {}).get("header_context", []):
        lines.append(f"    - {line}")

    lines.extend(
        [
            "",
            "Authentication-Results:",
            f"  DKIM: {report['auth_results'].get('dkim', 'not present')}",
            f"  SPF: {report['auth_results'].get('spf', 'not present')}",
            f"  DMARC: {report['auth_results'].get('dmarc', 'not present')}",
            "  Summary:",
        ]
    )
    for line in report.get("interpretation", {}).get("auth_results", []):
        lines.append(f"    - {line}")

    lines.extend(["", "DKIM Signatures:"])
    if report["dkim_signatures"]:
        for signature in report["dkim_signatures"]:
            signed_headers = signature.get("signed_headers") or []
            signed_headers_str = ", ".join(signed_headers) if signed_headers else "not present"
            lines.append(
                f"  domain={signature.get('domain') or 'missing'} "
                f"selector={signature.get('selector') or 'missing'} "
                f"algorithm={signature.get('algorithm') or 'missing'} "
                f"signed_headers={signed_headers_str}"
            )
    else:
        lines.append("  None")
    lines.append("  Summary:")
    for line in report.get("interpretation", {}).get("dkim_signatures", []):
        lines.append(f"    - {line}")

    lines.extend(["", "DKIM Key Lookups:"])
    if report["dkim_key_lookups"]:
        for lookup in report["dkim_key_lookups"]:
            lines.append(
                f"  {lookup['query_name']} status={lookup['status']} "
                f"has_public_key={lookup['has_public_key']} "
                f"dnssec_validated={lookup['dnssec_validated']}"
            )
    else:
        lines.append("  None")
    lines.append("  Summary:")
    for line in report.get("interpretation", {}).get("dkim_keys", []):
        lines.append(f"    - {line}")

    if report["warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend([f"  - {warning}" for warning in report["warnings"]])
        lines.append("  Summary:")
        for line in report.get("interpretation", {}).get("warnings", []):
            lines.append(f"    - {line}")

    lines.extend(["", report["note"]])

    return _render_minimal_pdf(lines)


def create_evidence_zip(raw_headers: str) -> bytes:
    report = analyze_raw_email_headers(raw_headers)
    created_at = datetime.now(UTC)

    artifacts: dict[str, bytes] = {
        "raw-headers.txt": raw_headers.encode("utf-8"),
        "report.json": json.dumps(report, indent=2, sort_keys=True).encode("utf-8"),
        "report.pdf": _render_report_pdf(report, created_at),
    }

    for lookup in report["dkim_key_lookups"]:
        filename = f"dkim-keys/{_safe_artifact_name(lookup['query_name'])}.txt"
        lines = [
            f"query_name: {lookup['query_name']}",
            f"status: {lookup['status']}",
            f"has_public_key: {lookup['has_public_key']}",
        ]
        if lookup.get("error"):
            lines.append(f"error: {lookup['error']}")
        if lookup["txt_records"]:
            lines.append("")
            lines.append("txt_records:")
            lines.extend([f"- {record}" for record in lookup["txt_records"]])
        artifacts[filename] = "\n".join(lines).encode("utf-8")

    checksums: list[str] = []
    for filename in sorted(artifacts):
        digest = hashlib.sha256(artifacts[filename]).hexdigest()
        checksums.append(f"{digest}  {filename}")
    artifacts["checksums.sha256"] = ("\n".join(checksums) + "\n").encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in artifacts.items():
            archive.writestr(filename, content)
    return output.getvalue()
