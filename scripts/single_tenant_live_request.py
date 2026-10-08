"""Exact signed request coordinates and private configuration validation."""

import re
from typing import Any

from hushline.single_tenant import valid_customer_domain
from scripts.single_tenant_live_envelope import encrypt
from scripts.single_tenant_live_payment import PAYMENT_FIELDS
from scripts.single_tenant_live_plan import identity
from scripts.single_tenant_live_release import validate_target

MAX_REVISION = 1000000


class Request:
    def __init__(self, data: dict[str, Any], *, branch: str, source: str, infra: str) -> None:
        if set(data) != {
            "order_id",
            "purpose",
            "revision",
            "config_ref",
            "source_ref",
            "infra_ref",
        }:
            raise ValueError("Unexpected public request fields")
        identity(data["order_id"])
        if (
            data["purpose"] not in {"provision", "retire", "upgrade"}
            or not isinstance(data["revision"], int)
            or isinstance(data["revision"], bool)
            or not 1 <= data["revision"] <= MAX_REVISION
        ):
            raise ValueError("Invalid request purpose or revision")
        if (
            data["source_ref"] != source
            or data["infra_ref"] != infra
            or any(
                not re.fullmatch(r"[a-f0-9]{40}", data[field])
                for field in ("config_ref", "source_ref", "infra_ref")
            )
        ):
            raise ValueError("Request source escaped the reviewed release")
        self.order, self.purpose, self.revision = (
            data["order_id"],
            data["purpose"],
            data["revision"],
        )
        self.config_ref = data["config_ref"]
        self.suffix = f"{self.order}/{self.purpose}-{self.revision}"
        if branch != "single-tenant-request/" + self.suffix:
            raise ValueError("Request branch belongs to another order")
        self.filename = "single-tenant/orders/" + self.suffix + ".json"

    def private(self, data: dict[str, Any]) -> dict[str, Any]:
        expected = {"order_id", "owner", "domain", "payment", "verification", "claim_public_key"}
        if self.purpose == "upgrade":
            expected.add("release")
            validate_target(data.get("release"))
        if (
            set(data) != expected
            or data["order_id"] != self.order
            or not re.fullmatch(r"[a-f0-9]{64}", data["owner"])
            or not valid_customer_domain(data["domain"])
            or not re.fullmatch(r"[a-f0-9]{64}", data["verification"])
        ):
            raise ValueError("Private request identity or domain is invalid")
        payment = data["payment"]
        if (
            not isinstance(payment, dict)
            or set(payment) != PAYMENT_FIELDS
            or payment["payment_mode"] != "stripe_live"
        ):
            raise ValueError("Only owned live annual payments may use this workflow")
        encrypt(data["claim_public_key"], {})
        return data


def commit(data: dict[str, Any], *, expected_parent: str, path: str) -> None:
    if (
        data.get("commit", {}).get("verification", {}).get("verified") is not True
        or data.get("committer", {}).get("login") != "hushline-dev"
        or [parent.get("sha") for parent in data.get("parents", [])] != [expected_parent]
        or len(data.get("files", [])) != 1
        or data["files"][0].get("filename") != path
        or data["files"][0].get("status") != "added"
    ):
        raise ValueError("Request commit is not the signed create-only reviewed source")
