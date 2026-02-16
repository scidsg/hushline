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

    return {
        "selector": selector,
        "domain": domain,
        "query_name": query_name,
        "status": "found",
        "txt_records": txt_records,
        "has_public_key": has_public_key,
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
            "headline": "🚨 This email is likely forged.",
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
            "headline": "✅ This email looks valid.",
            "reasons": reasons or ["Key authentication checks passed and domains are aligned."],
        }

    return {
        "verdict": "appears inauthentic",
        "headline": "⚠️ This email appears inauthentic.",
        "reasons": reasons or ["Authentication checks are incomplete, conflicting, or weak."],
    }


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
            "body_hash_present": bool(tags.get("bh")),
            "signature_present": bool(tags.get("b")),
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
        "alignment": alignment,
        "executive_summary": executive_summary,
        "warnings": warnings,
        "note": (
            "Header analysis improves confidence but cannot prove authenticity on its own. "
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
        "Email Summary:",
        f"  {report['executive_summary']['headline']}",
    ]
    for reason in report["executive_summary"]["reasons"]:
        lines.append(f"  - {reason}")
    lines.extend(
        [
            "",
            f"From: {report.get('from_header', '')}",
            f"Return-Path: {report.get('return_path_header', '')}",
            f"Reply-To: {report.get('reply_to_header', '')}",
            "",
            "Authentication-Results:",
            f"  DKIM: {report['auth_results'].get('dkim', 'not present')}",
            f"  SPF: {report['auth_results'].get('spf', 'not present')}",
            f"  DMARC: {report['auth_results'].get('dmarc', 'not present')}",
            "",
            "DKIM Key Lookups:",
        ]
    )
    if report["dkim_key_lookups"]:
        for lookup in report["dkim_key_lookups"]:
            lines.append(
                f"  {lookup['query_name']} status={lookup['status']} "
                f"has_public_key={lookup['has_public_key']}"
            )
    else:
        lines.append("  None")

    if report["warnings"]:
        lines.extend(["", "Warnings:"])
        lines.extend([f"  - {warning}" for warning in report["warnings"]])

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
