import io
from datetime import UTC, datetime

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.wrappers.response import Response

from hushline.auth import authentication_required
from hushline.email_headers import analyze_raw_email_headers, create_evidence_zip
from hushline.routes.forms import RawEmailHeadersExportForm, RawEmailHeadersForm
from hushline.routes.tools import TOOL_TABS, TOOLS_SIDEBAR_THRESHOLD


def register_email_headers_routes(app: Flask) -> None:
    @app.route("/email-headers", methods=["GET", "POST"])
    @authentication_required
    def email_headers() -> str:
        form = RawEmailHeadersForm()
        export_form = RawEmailHeadersExportForm()
        report = None

        if request.method == "POST":
            if form.validate_on_submit():
                try:
                    report = analyze_raw_email_headers(form.raw_headers.data)
                    export_form.raw_headers.data = form.raw_headers.data
                except ValueError as e:
                    flash(f"⛔️ {str(e)}")
            else:
                flash("⛔️ Please paste valid raw headers before submitting.")

        return render_template(
            "email_headers.html",
            form=form,
            export_form=export_form,
            report=report,
            tool_tabs=TOOL_TABS,
            tools_sidebar=len(TOOL_TABS) >= TOOLS_SIDEBAR_THRESHOLD,
        )

    @app.route("/email-headers/evidence.zip", methods=["POST"])
    @authentication_required
    def email_headers_evidence_zip() -> Response:
        form = RawEmailHeadersExportForm()
        if not form.validate_on_submit():
            flash("⛔️ Could not generate report. Re-run validation first.")
            return redirect(url_for("email_headers"))

        archive = create_evidence_zip(form.raw_headers.data)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%SZ")
        return send_file(
            io.BytesIO(archive),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"email-header-report-{stamp}.zip",
        )
