import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from hushline.model import OrganizationSetting
from hushline.outreach import (
    OutreachLead,
    annotate_outreach_leads,
    filter_outreach_leads,
    outreach_lead_counts,
    refresh_outreach_leads,
)


def _lead(
    *,
    lead_id: str,
    name: str,
    source_kind: str,
    fit_score: int = 90,
) -> OutreachLead:
    return OutreachLead(
        lead_id=lead_id,
        name=name,
        source_kind=source_kind,
        source_label="Sample source",
        contact_method="Public website/contact page",
        website="https://example.org",
        contact_host="example.org",
        contact_url="https://example.org",
        listing_url="/directory/example",
        location="Example City",
        fit_score=fit_score,
        fit_summary="existing secure intake workflow",
        subject="Hush Line for secure disclosures",
        body="Hello from Hush Line.",
    )


def test_outreach_helpers_filter_and_count() -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="gl-1", name="Beta Intake", source_kind="globaleaks"),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop"),
    )

    assert outreach_lead_counts(leads) == {
        "all": 3,
        "public_record": 1,
        "globaleaks": 1,
        "securedrop": 1,
    }
    assert filter_outreach_leads(leads, "all") == leads
    assert filter_outreach_leads(leads, "securedrop") == (leads[2],)


def test_refresh_outreach_leads_reopens_current_queue_and_preserves_history(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop"),
    )
    monkeypatch.setattr("hushline.outreach.get_outreach_leads", lambda: leads)

    with app.app_context():
        OrganizationSetting.upsert(
            OrganizationSetting.OUTREACH_COMPLETED_LEADS,
            {
                "pr-1": {"is_complete": True, "was_completed": True, "is_converted": False},
                "sd-1": {"is_complete": True, "was_completed": True, "is_converted": True},
            },
        )
        refresh_outreach_leads()
        assert OrganizationSetting.fetch_one(OrganizationSetting.OUTREACH_COMPLETED_LEADS) == {
            "pr-1": {"is_complete": False, "was_completed": True, "is_converted": False},
            "sd-1": {"is_complete": True, "was_completed": True, "is_converted": True},
        }


def test_annotate_outreach_leads_preserves_history_after_refresh(app: Flask) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop"),
    )
    with app.app_context():
        OrganizationSetting.upsert(
            OrganizationSetting.OUTREACH_COMPLETED_LEADS,
            {
                "pr-1": {"is_complete": False, "was_completed": True, "is_converted": False},
                "sd-1": {"is_complete": True, "was_completed": True, "is_converted": True},
            },
        )

        annotated = annotate_outreach_leads(leads)

        assert annotated[0].lead_id == "pr-1"
        assert annotated[0].is_complete is False
        assert annotated[0].was_completed is True
        assert annotated[0].is_converted is False
        assert annotated[1].lead_id == "sd-1"
        assert annotated[1].is_complete is True
        assert annotated[1].was_completed is True
        assert annotated[1].is_converted is True


@pytest.mark.usefixtures("_authenticated_user")
def test_outreach_page_forbidden_for_non_admin(client: FlaskClient) -> None:
    response = client.get(url_for("settings.outreach"), follow_redirects=False)
    assert response.status_code == 403


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_outreach_page_shows_human_reviewed_leads_for_admin(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record", fit_score=96),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop", fit_score=94),
    )

    monkeypatch.setattr("hushline.settings.outreach.get_outreach_leads", lambda: leads)
    monkeypatch.setattr("hushline.outreach.get_outreach_leads", lambda: leads)

    response = client.get(url_for("settings.outreach"), follow_redirects=True)
    assert response.status_code == 200
    assert (
        "Human-reviewed outreach drafts built from automated directory listings." in response.text
    )
    assert "Alpha Counsel" in response.text
    assert "Gamma Newsroom" in response.text
    assert "Suggested Subject" in response.text
    assert "Hello from Hush Line." in response.text
    assert 'aria-label="Outreach open lead count"' in response.text
    assert 'aria-label="All open lead count"' in response.text
    assert "Contact method: Public website/contact page" in response.text
    assert "Visit Website" in response.text
    assert "Refresh Queue" in response.text
    assert "Mark Converted" in response.text
    assert 'id="outreach-tabs"' in response.text
    assert 'class="directory-tabs outreach-subtabs"' in response.text
    assert "/static/js/settings_outreach.js" in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_outreach_page_filters_by_source_for_admin(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="gl-1", name="Beta Intake", source_kind="globaleaks"),
    )

    monkeypatch.setattr("hushline.settings.outreach.get_outreach_leads", lambda: leads)
    monkeypatch.setattr("hushline.outreach.get_outreach_leads", lambda: leads)

    response = client.get(url_for("settings.outreach", source="globaleaks"))
    assert response.status_code == 200
    assert 'id="outreach-globaleaks-tab"' in response.text
    assert 'aria-selected="true"' in response.text
    assert 'id="outreach-globaleaks"' in response.text


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_outreach_page_can_mark_lead_complete(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop"),
    )

    monkeypatch.setattr("hushline.settings.outreach.get_outreach_leads", lambda: leads)
    monkeypatch.setattr("hushline.outreach.get_outreach_leads", lambda: leads)

    response = client.post(
        url_for("settings.outreach_complete"),
        data={"lead_id": "pr-1", "is_complete": "true", "source": "all"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Outreach lead status updated." in response.text
    assert "Completed outreach lead" in response.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.OUTREACH_COMPLETED_LEADS) == {
        "pr-1": {"is_complete": True, "was_completed": True, "is_converted": False}
    }


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_outreach_page_can_refresh_queue(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop"),
    )

    monkeypatch.setattr("hushline.settings.outreach.get_outreach_leads", lambda: leads)
    monkeypatch.setattr("hushline.outreach.get_outreach_leads", lambda: leads)

    OrganizationSetting.upsert(
        OrganizationSetting.OUTREACH_COMPLETED_LEADS,
        {
            "pr-1": {"is_complete": True, "was_completed": True, "is_converted": False},
            "sd-1": {"is_complete": True, "was_completed": True, "is_converted": True},
        },
    )

    response = client.post(
        url_for("settings.outreach_refresh"),
        data={"source": "securedrop"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Outreach queue refreshed." in response.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.OUTREACH_COMPLETED_LEADS) == {
        "pr-1": {"is_complete": False, "was_completed": True, "is_converted": False},
        "sd-1": {"is_complete": True, "was_completed": True, "is_converted": True},
    }


@pytest.mark.usefixtures("_authenticated_admin_user")
def test_outreach_page_can_mark_lead_converted(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    leads = (
        _lead(lead_id="pr-1", name="Alpha Counsel", source_kind="public_record"),
        _lead(lead_id="sd-1", name="Gamma Newsroom", source_kind="securedrop"),
    )

    monkeypatch.setattr("hushline.settings.outreach.get_outreach_leads", lambda: leads)
    monkeypatch.setattr("hushline.outreach.get_outreach_leads", lambda: leads)

    response = client.post(
        url_for("settings.outreach_convert"),
        data={"lead_id": "sd-1", "is_converted": "true", "source": "securedrop"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Outreach lead marked converted." in response.text
    assert "Converted outreach lead" in response.text
    assert OrganizationSetting.fetch_one(OrganizationSetting.OUTREACH_COMPLETED_LEADS) == {
        "sd-1": {"is_complete": True, "was_completed": True, "is_converted": True}
    }
