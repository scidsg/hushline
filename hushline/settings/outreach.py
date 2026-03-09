from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import generate_csrf
from werkzeug.wrappers.response import Response

from hushline.auth import admin_authentication_required
from hushline.db import db
from hushline.model import User
from hushline.outreach import (
    annotate_outreach_leads,
    count_open_outreach_leads,
    filter_outreach_leads,
    get_outreach_leads,
    outreach_lead_counts,
    outreach_open_counts,
    refresh_outreach_leads,
    set_outreach_lead_completion,
    set_outreach_lead_conversion,
)

_SOURCE_OPTIONS = {"all", "public_record", "globaleaks", "securedrop"}


def register_outreach_routes(bp: Blueprint) -> None:
    @bp.route("/outreach")
    @admin_authentication_required
    def outreach() -> str:
        user = db.session.scalars(db.select(User).filter_by(id=session["user_id"])).one()
        source_filter = request.args.get("source", "all").strip().lower()
        if source_filter not in _SOURCE_OPTIONS:
            source_filter = "all"

        leads = annotate_outreach_leads(get_outreach_leads())

        return render_template(
            "settings/outreach.html",
            user=user,
            source_filter=source_filter,
            open_lead_counts=outreach_open_counts(leads),
            lead_counts=outreach_lead_counts(leads),
            open_lead_count=count_open_outreach_leads(leads),
            all_leads=filter_outreach_leads(leads, "all"),
            public_record_leads=filter_outreach_leads(leads, "public_record"),
            globaleaks_leads=filter_outreach_leads(leads, "globaleaks"),
            securedrop_leads=filter_outreach_leads(leads, "securedrop"),
            csrf_token=generate_csrf(),
        )

    @bp.route("/outreach/complete", methods=["POST"])
    @admin_authentication_required
    def outreach_complete() -> Response:
        lead_id = (request.form.get("lead_id") or "").strip()
        source_filter = (request.form.get("source") or "all").strip().lower()
        if source_filter not in _SOURCE_OPTIONS:
            source_filter = "all"

        set_outreach_lead_completion(
            lead_id,
            is_complete=(request.form.get("is_complete") == "true"),
        )
        db.session.commit()
        flash("👍 Outreach lead status updated.")
        return redirect(url_for("settings.outreach", source=source_filter))

    @bp.route("/outreach/refresh", methods=["POST"])
    @admin_authentication_required
    def outreach_refresh() -> Response:
        source_filter = (request.form.get("source") or "all").strip().lower()
        if source_filter not in _SOURCE_OPTIONS:
            source_filter = "all"

        refresh_outreach_leads()
        db.session.commit()
        flash("🔄 Outreach queue refreshed.")
        return redirect(url_for("settings.outreach", source=source_filter))

    @bp.route("/outreach/convert", methods=["POST"])
    @admin_authentication_required
    def outreach_convert() -> Response:
        lead_id = (request.form.get("lead_id") or "").strip()
        source_filter = (request.form.get("source") or "all").strip().lower()
        if source_filter not in _SOURCE_OPTIONS:
            source_filter = "all"

        set_outreach_lead_conversion(
            lead_id,
            is_converted=(request.form.get("is_converted") == "true"),
        )
        db.session.commit()
        flash("🎉 Outreach lead marked converted.")
        return redirect(url_for("settings.outreach", source=source_filter))
