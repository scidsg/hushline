from __future__ import annotations

import re
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from flask import url_for

from hushline.model import (
    GlobaLeaksDirectoryListing,
    OrganizationSetting,
    PublicRecordListing,
    SecureDropDirectoryListing,
    get_globaleaks_directory_listings,
    get_public_record_listings,
    get_securedrop_directory_listings,
)


@dataclass(frozen=True)
class OutreachLead:
    lead_id: str
    name: str
    source_kind: str
    source_label: str
    contact_method: str
    website: str
    contact_host: str
    contact_url: str
    listing_url: str
    location: str
    fit_score: int
    fit_summary: str
    subject: str
    body: str
    is_complete: bool = False
    was_completed: bool = False
    is_converted: bool = False


def _plain_brand_name(raw_value: object) -> str:
    value = str(raw_value or "Hush Line").strip()
    value = re.sub(r"^[^\w]+", "", value).strip()
    return value or "Hush Line"


def _brand_name() -> str:
    return _plain_brand_name(OrganizationSetting.fetch_one(OrganizationSetting.BRAND_NAME))


def _host_from_url(url: str) -> str:
    return urlparse(url).hostname or url


def _contact_path_label(host: str) -> str:
    return f"Public contact path via {host}"


def _lead_progress() -> dict[str, dict[str, bool]]:
    raw_value = OrganizationSetting.fetch_one(OrganizationSetting.OUTREACH_COMPLETED_LEADS)
    if isinstance(raw_value, list):
        return {
            str(value): {
                "is_complete": True,
                "was_completed": True,
                "is_converted": False,
            }
            for value in raw_value
            if isinstance(value, str)
        }
    if not isinstance(raw_value, dict):
        return {}

    normalized: dict[str, dict[str, bool]] = {}
    for lead_id, value in raw_value.items():
        if not isinstance(lead_id, str) or not isinstance(value, dict):
            continue
        is_complete = bool(value.get("is_complete", False))
        was_completed = bool(value.get("was_completed", is_complete))
        is_converted = bool(value.get("is_converted", False))
        normalized[lead_id] = {
            "is_complete": is_complete or is_converted,
            "was_completed": was_completed or is_complete or is_converted,
            "is_converted": is_converted,
        }
    return normalized


def _public_record_fit_summary(listing: PublicRecordListing) -> tuple[int, str]:
    tags = {tag.casefold() for tag in listing.practice_tags}
    score = 82
    reasons: list[str] = ["public whistleblower-facing legal listing"]
    if "whistleblowing" in tags:
        score += 10
        reasons.insert(0, "explicit whistleblowing practice")
    if "investigations" in tags:
        score += 4
        reasons.append("investigations fit")
    if "employment" in tags or "civil rights" in tags or "consumer" in tags:
        score += 2
        reasons.append("public-interest intake fit")
    return min(score, 99), ", ".join(reasons)


def _securedrop_fit_summary(listing: SecureDropDirectoryListing) -> tuple[int, str]:
    score = 92
    reasons = ["existing secure intake workflow", "newsroom/source-protection fit"]
    if listing.topics:
        score += min(4, len(listing.topics))
        reasons.append("clear reporting beats")
    return min(score, 99), ", ".join(reasons)


def _globaleaks_fit_summary(listing: GlobaLeaksDirectoryListing) -> tuple[int, str]:
    score = 89
    reasons = ["existing secure reporting workflow", "organization-level intake fit"]
    if listing.has_onion_submission:
        score += 4
        reasons.append("Tor-accessible submission flow")
    if len(listing.languages) > 1:
        score += 2
        reasons.append("multilingual reach")
    return min(score, 99), ", ".join(reasons)


def _public_record_body(listing: PublicRecordListing, brand_name: str) -> str:
    return (
        f"Hi {listing.name},\n\n"
        f"I’m reaching out from {brand_name}. We came across your public listing in "
        f"{listing.source_label} and thought your whistleblower-facing practice "
        f"looked like a strong fit for Hush Line.\n\n"
        f"Hush Line is an open-source secure reporting platform for lawyers, journalists, and "
        f"organizations that need a branded intake channel for sensitive disclosures. "
        f"We’d love to share what we’re building, who we are, and invite you to join "
        f"the network if it looks useful for your practice.\n\n"
        f"If you’re open to it, I can send a short overview or walk you through how "
        f"teams are using Hush Line today.\n\n"
        f"Best,\nThe {brand_name} team"
    )


def _automated_listing_body(
    listing_name: str,
    source_label: str,
    brand_name: str,
) -> str:
    return (
        f"Hi {listing_name} team,\n\n"
        f"I’m reaching out from {brand_name}. We saw your organization in "
        f"{source_label} and thought you might be a strong fit for Hush Line as "
        f"an additional secure intake option.\n\n"
        f"Hush Line is an open-source secure reporting platform for organizations "
        f"that need a branded channel for sensitive disclosures. We’d love to "
        f"share what we’re building, who we are, and invite you to join if it "
        f"looks useful alongside your current workflow.\n\n"
        f"If helpful, I can send a short overview or set up a quick walkthrough.\n\n"
        f"Best,\nThe {brand_name} team"
    )


def _public_record_lead(listing: PublicRecordListing, brand_name: str) -> OutreachLead:
    fit_score, fit_summary = _public_record_fit_summary(listing)
    contact_host = _host_from_url(listing.website)
    return OutreachLead(
        lead_id=listing.id,
        name=listing.name,
        source_kind="public_record",
        source_label=listing.source_label,
        contact_method="Public website/contact page",
        website=listing.website,
        contact_host=contact_host,
        contact_url=listing.website,
        listing_url=url_for("public_record_listing", slug=listing.slug),
        location=listing.location,
        fit_score=fit_score,
        fit_summary=fit_summary,
        subject=f"{brand_name} for whistleblower intake",
        body=_public_record_body(listing, brand_name),
    )


def _securedrop_lead(listing: SecureDropDirectoryListing, brand_name: str) -> OutreachLead:
    fit_score, fit_summary = _securedrop_fit_summary(listing)
    contact_host = _host_from_url(listing.website)
    return OutreachLead(
        lead_id=listing.id,
        name=listing.name,
        source_kind="securedrop",
        source_label=listing.source_label,
        contact_method="Public website/contact page",
        website=listing.website,
        contact_host=contact_host,
        contact_url=listing.website,
        listing_url=url_for("securedrop_listing", slug=listing.slug),
        location=listing.location,
        fit_score=fit_score,
        fit_summary=fit_summary,
        subject=f"{brand_name} as an additional secure intake option",
        body=_automated_listing_body(listing.name, listing.source_label, brand_name),
    )


def _globaleaks_lead(listing: GlobaLeaksDirectoryListing, brand_name: str) -> OutreachLead:
    fit_score, fit_summary = _globaleaks_fit_summary(listing)
    contact_host = _host_from_url(listing.website)
    return OutreachLead(
        lead_id=listing.id,
        name=listing.name,
        source_kind="globaleaks",
        source_label=listing.source_label,
        contact_method="Public website/contact page",
        website=listing.website,
        contact_host=contact_host,
        contact_url=listing.website,
        listing_url=url_for("globaleaks_listing", slug=listing.slug),
        location=listing.location,
        fit_score=fit_score,
        fit_summary=fit_summary,
        subject=f"{brand_name} for secure disclosures",
        body=_automated_listing_body(listing.name, listing.source_label, brand_name),
    )


def get_outreach_leads() -> tuple[OutreachLead, ...]:
    brand_name = _brand_name()
    leads = [
        *(
            _public_record_lead(listing, brand_name)
            for listing in get_public_record_listings()
            if listing.directory_section == "public_record"
        ),
        *(_globaleaks_lead(listing, brand_name) for listing in get_globaleaks_directory_listings()),
        *(_securedrop_lead(listing, brand_name) for listing in get_securedrop_directory_listings()),
    ]
    return tuple(
        sorted(
            leads,
            key=lambda lead: (-lead.fit_score, lead.source_kind, lead.name.casefold()),
        )
    )


def filter_outreach_leads(
    leads: tuple[OutreachLead, ...], source_kind: str
) -> tuple[OutreachLead, ...]:
    if source_kind == "all":
        return leads
    return tuple(lead for lead in leads if lead.source_kind == source_kind)


def outreach_lead_counts(leads: tuple[OutreachLead, ...]) -> dict[str, int]:
    return {
        "all": len(leads),
        "public_record": sum(1 for lead in leads if lead.source_kind == "public_record"),
        "globaleaks": sum(1 for lead in leads if lead.source_kind == "globaleaks"),
        "securedrop": sum(1 for lead in leads if lead.source_kind == "securedrop"),
    }


def outreach_contact_path_label(lead: OutreachLead) -> str:
    return _contact_path_label(lead.contact_host)


def annotate_outreach_leads(leads: tuple[OutreachLead, ...]) -> tuple[OutreachLead, ...]:
    progress = _lead_progress()
    annotated = tuple(
        replace(
            lead,
            is_complete=progress.get(lead.lead_id, {}).get("is_complete", False),
            was_completed=progress.get(lead.lead_id, {}).get("was_completed", False),
            is_converted=progress.get(lead.lead_id, {}).get("is_converted", False),
        )
        for lead in leads
    )
    return tuple(
        sorted(
            annotated,
            key=lambda lead: (
                lead.is_converted,
                lead.is_complete,
                -lead.fit_score,
                lead.source_kind,
                lead.name.casefold(),
            ),
        )
    )


def count_open_outreach_leads(leads: tuple[OutreachLead, ...]) -> int:
    return sum(1 for lead in leads if not lead.is_complete)


def outreach_open_counts(leads: tuple[OutreachLead, ...]) -> dict[str, int]:
    return {
        "all": count_open_outreach_leads(leads),
        "public_record": sum(
            1 for lead in leads if lead.source_kind == "public_record" and not lead.is_complete
        ),
        "globaleaks": sum(
            1 for lead in leads if lead.source_kind == "globaleaks" and not lead.is_complete
        ),
        "securedrop": sum(
            1 for lead in leads if lead.source_kind == "securedrop" and not lead.is_complete
        ),
    }


def set_outreach_lead_completion(lead_id: str, *, is_complete: bool) -> None:
    valid_ids = {lead.lead_id for lead in get_outreach_leads()}
    if lead_id not in valid_ids:
        return

    progress = _lead_progress()
    current = progress.get(
        lead_id,
        {"is_complete": False, "was_completed": False, "is_converted": False},
    )

    if current["is_converted"] and not is_complete:
        current["is_converted"] = False

    current["is_complete"] = is_complete
    current["was_completed"] = current["was_completed"] or is_complete

    if current["is_complete"] or current["was_completed"] or current["is_converted"]:
        progress[lead_id] = current
    else:
        progress.pop(lead_id, None)

    OrganizationSetting.upsert(
        OrganizationSetting.OUTREACH_COMPLETED_LEADS,
        progress,
    )


def set_outreach_lead_conversion(lead_id: str, *, is_converted: bool) -> None:
    valid_ids = {lead.lead_id for lead in get_outreach_leads()}
    if lead_id not in valid_ids:
        return

    progress = _lead_progress()
    current = progress.get(
        lead_id,
        {"is_complete": False, "was_completed": False, "is_converted": False},
    )

    current["is_converted"] = is_converted
    current["is_complete"] = is_converted or current["is_complete"]
    current["was_completed"] = current["was_completed"] or is_converted

    progress[lead_id] = current

    OrganizationSetting.upsert(
        OrganizationSetting.OUTREACH_COMPLETED_LEADS,
        progress,
    )


def refresh_outreach_leads() -> None:
    progress = _lead_progress()
    refreshed = {}
    valid_ids = {lead.lead_id for lead in get_outreach_leads()}
    for lead_id, current in progress.items():
        if lead_id not in valid_ids:
            continue
        refreshed[lead_id] = {
            "is_complete": bool(current.get("is_converted", False)),
            "was_completed": bool(
                current.get("was_completed", False)
                or current.get("is_complete", False)
                or current.get("is_converted", False)
            ),
            "is_converted": bool(current.get("is_converted", False)),
        }

    OrganizationSetting.upsert(
        OrganizationSetting.OUTREACH_COMPLETED_LEADS,
        refreshed,
    )
