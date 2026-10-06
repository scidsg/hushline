"""Private durable customer ledger and immutable Git publication checkpoints.

This module cannot provision or delete resources. Workflow ownership and fresh
payment authority remain required. Never use an existing fixture database.
"""

from __future__ import annotations

import calendar
import contextlib
import hashlib
import hmac
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from scripts.single_tenant_live_plan import identity

NAMESPACE = "hushline-single-tenant"
SCHEMA_VERSION = 1
MAX_PRIVATE_BYTES = 65536
HEARTBEAT_SECONDS = 90


class Ledger:
    def __init__(self, path: Path, key: bytes) -> None:
        self.path = path
        self.cipher = Fernet(key)
        self.index_key = hashlib.sha256(key + b"ledger-index-v1").digest()
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("An existing private Single Tenant ledger is required")
        with self.transaction() as connection:
            row = connection.execute("SELECT namespace, version, seal FROM identity").fetchall()
            if len(row) != 1 or row[0][:2] != (NAMESPACE, SCHEMA_VERSION):
                raise ValueError("Ledger namespace or version is not owned")
            if self.open(row[0][2]) != {"namespace": NAMESPACE, "version": SCHEMA_VERSION}:
                raise ValueError("Ledger encryption identity is not owned")

    @classmethod
    def create(cls, path: Path, key: bytes) -> Ledger:
        # Exclusive creation prevents adopting another instance or a retired ledger.
        cipher = Fernet(key)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        seal = cipher.encrypt(
            json.dumps({"namespace": NAMESPACE, "version": SCHEMA_VERSION}).encode()
        )
        with contextlib.closing(sqlite3.connect(path)) as connection, connection:
            connection.executescript("""
                PRAGMA journal_mode=DELETE;
                CREATE TABLE identity (
                    namespace TEXT NOT NULL, version INTEGER NOT NULL, seal BLOB NOT NULL
                );
                CREATE TABLE orders (
                    id TEXT PRIMARY KEY, owner_tag TEXT NOT NULL, receipt_tag TEXT UNIQUE NOT NULL,
                    subscription_tag TEXT UNIQUE NOT NULL, domain_tag TEXT UNIQUE NOT NULL,
                    payload BLOB NOT NULL, revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE requests (
                    order_id TEXT NOT NULL REFERENCES orders(id), purpose TEXT NOT NULL,
                    revision INTEGER NOT NULL, payload BLOB NOT NULL,
                    private_sha TEXT, public_sha TEXT, published INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (order_id, purpose, revision)
                );
                CREATE TABLE nonces (nonce TEXT PRIMARY KEY, expires INTEGER NOT NULL);
                CREATE TABLE artifacts (id TEXT PRIMARY KEY);
                CREATE TABLE workflow_runs (
                    id TEXT PRIMARY KEY, finished INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE collection_cursor (
                    id INTEGER PRIMARY KEY CHECK(id=1), run_id TEXT NOT NULL
                );
                CREATE TABLE heartbeat (
                    id INTEGER PRIMARY KEY CHECK(id=1), checked INTEGER NOT NULL
                );
            """)
            connection.execute(
                "INSERT INTO identity VALUES (?, ?, ?)", (NAMESPACE, SCHEMA_VERSION, seal)
            )
        return cls(path, key)

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with (
            contextlib.closing(
                sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=30)
            ) as connection,
            connection,
        ):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def tag(self, value: str) -> str:
        return hmac.new(self.index_key, value.encode(), hashlib.sha256).hexdigest()

    def seal(self, payload: dict[str, Any]) -> bytes:
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        if len(data) > MAX_PRIVATE_BYTES:
            raise ValueError("Private ledger entry exceeded its safety limit")
        return self.cipher.encrypt(data)

    def open(self, payload: bytes) -> dict[str, Any]:
        try:
            result = json.loads(self.cipher.decrypt(payload))
        except (InvalidToken, ValueError):
            raise ValueError("Private ledger authentication failed") from None
        if not isinstance(result, dict):
            raise ValueError("Private ledger entry is invalid")
        return result

    @staticmethod
    def owner(order: str, owner: str) -> None:
        identity(order)
        if not re.fullmatch(r"[a-f0-9]{64}", owner):
            raise ValueError("An opaque account owner is required")

    def reserve(self, order: str, owner: str, payload: dict[str, Any]) -> None:
        self.owner(order, owner)
        if payload.get("order_id") != order or payload.get("owner") != owner:
            raise ValueError("Order identity does not match its private record")
        payment = payload.get("payment", {})
        if not all(
            isinstance(payment.get(field), str) and payment[field]
            for field in ("receipt", "subscription_id")
        ):
            raise ValueError("Paid receipt and subscription identities are required")
        domain = payload.get("domain")
        if not isinstance(domain, str) or not domain:
            raise ValueError("A customer domain is required")
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT owner_tag, payload FROM orders WHERE id=?", (order,)
            ).fetchone()
            if existing:
                if existing[0] != self.tag(owner) or self.open(existing[1]) != payload:
                    raise ValueError("An existing order cannot be adopted or replaced")
                return
            try:
                connection.execute(
                    "INSERT INTO orders(id, owner_tag, receipt_tag, subscription_tag, domain_tag, "
                    "payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        order,
                        self.tag(owner),
                        self.tag(payment["receipt"]),
                        self.tag(payment["subscription_id"]),
                        self.tag(domain),
                        self.seal(payload),
                    ),
                )
                self._queue(connection, order, "provision", 1, payload)
            except sqlite3.IntegrityError:
                raise ValueError("A payment or domain already belongs to another order") from None

    def get(self, order: str, owner: str) -> dict[str, Any]:
        self.owner(order, owner)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT owner_tag, payload FROM orders WHERE id=?", (order,)
            ).fetchone()
            if not row or not hmac.compare_digest(row[0], self.tag(owner)):
                raise ValueError("Order ownership is unverified")
            return self.open(row[1])

    def _queue(  # noqa: PLR0913 — exact immutable request coordinates and private payload
        self,
        connection: sqlite3.Connection,
        order: str,
        purpose: str,
        revision: int,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO requests(order_id, purpose, revision, payload) VALUES (?, ?, ?, ?)",
            (order, purpose, revision, self.seal(payload)),
        )

    def checkpoint(  # noqa: PLR0913 — exact request and both signed commit identities
        self, order: str, purpose: str, revision: int, *, private_sha: str, public_sha: str
    ) -> None:
        if any(not re.fullmatch(r"[a-f0-9]{40}", sha) for sha in (private_sha, public_sha)):
            raise ValueError("Signed Git commit identities are required")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT private_sha, public_sha FROM requests "
                "WHERE order_id=? AND purpose=? AND revision=?",
                (order, purpose, revision),
            ).fetchone()
            if row is None or (row[0] is not None and row != (private_sha, public_sha)):
                raise ValueError("Publication cannot replace a checkpointed request")
            connection.execute(
                "UPDATE requests SET private_sha=?, public_sha=? "
                "WHERE order_id=? AND purpose=? AND revision=?",
                (private_sha, public_sha, order, purpose, revision),
            )

    def published(  # noqa: PLR0913 — publication must match both immutable commit identities
        self, order: str, purpose: str, revision: int, *, private_sha: str, public_sha: str
    ) -> None:
        self.checkpoint(order, purpose, revision, private_sha=private_sha, public_sha=public_sha)
        with self.transaction() as connection:
            connection.execute(
                "UPDATE requests SET published=1 WHERE order_id=? AND purpose=? AND revision=? "
                "AND private_sha=? AND public_sha=?",
                (order, purpose, revision, private_sha, public_sha),
            )

    def pending(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            return [
                {
                    "order_id": row[0],
                    "purpose": row[1],
                    "revision": row[2],
                    "payload": self.open(row[3]),
                    "private_sha": row[4],
                    "public_sha": row[5],
                }
                for row in connection.execute(
                    "SELECT order_id, purpose, revision, payload, private_sha, public_sha "
                    "FROM requests WHERE published=0 ORDER BY order_id, revision LIMIT 100"
                )
            ]

    def published_request(self, order: str, purpose: str, revision: int) -> str | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT public_sha FROM requests WHERE order_id=? AND purpose=? "
                "AND revision=? AND published=1",
                (order, purpose, revision),
            ).fetchone()
            return row[0] if row else None

    def nonce(self, nonce: str, *, now: int, ttl: int = 600) -> bool:
        if not re.fullmatch(r"[a-f0-9]{32}", nonce):
            return False
        with self.transaction() as connection:
            connection.execute("DELETE FROM nonces WHERE expires < ?", (now,))
            try:
                connection.execute("INSERT INTO nonces VALUES (?, ?)", (nonce, now + ttl))
            except sqlite3.IntegrityError:
                return False
            return True

    def billing(self, order: str, owner: str, payment: dict[str, Any]) -> None:
        """Persist a signed portal update; workflow still rechecks Stripe authority."""
        self.owner(order, owner)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT owner_tag, payload, revision FROM orders WHERE id=?", (order,)
            ).fetchone()
            if not row or not hmac.compare_digest(row[0], self.tag(owner)):
                raise ValueError("Order ownership is unverified")
            payload = self.open(row[1])
            prior = payload["payment"]
            fixed = {
                "payment_mode",
                "license_limit",
                "receipt",
                "session_id",
                "subscription_id",
                "customer_id",
            }
            if set(payment) != set(prior) or any(
                payment.get(field) != prior.get(field) for field in fixed
            ):
                raise ValueError("Billing update changed the owned payment identity")
            start, end = (
                datetime.fromisoformat(payment[field]) for field in ("period_start", "period_end")
            )
            old_start, old_end = (
                datetime.fromisoformat(prior[field]) for field in ("period_start", "period_end")
            )
            day = min(start.day, calendar.monthrange(start.year + 1, start.month)[1])
            if (
                any(value.tzinfo != UTC for value in (start, end, old_start, old_end))
                or end != start.replace(year=start.year + 1, day=day)
                or start < old_start
                or end < old_end
            ):
                raise ValueError("Billing update shortened or changed the paid year")
            if start == old_start and (
                end != old_end or payment.get("invoice_id") != prior.get("invoice_id")
            ):
                raise ValueError("An existing paid year cannot change its invoice")
            if start > old_start and start < old_end:
                raise ValueError("Renewal cannot overlap the existing paid year")
            if payload.get("retirement_started") or payload.get("state") in {"retiring", "retired"}:
                raise ValueError("A retiring order cannot be renewed")
            if payment == prior:
                return
            payload["payment"] = payment
            connection.execute(
                "UPDATE orders SET payload=?, revision=revision+1 WHERE id=?",
                (self.seal(payload), order),
            )

    def expiry(self, *, now: datetime) -> int:
        if now.tzinfo != UTC:
            raise ValueError("Expiry worker requires UTC")
        count = 0
        with self.transaction() as connection:
            for order, sealed, revision in connection.execute(
                "SELECT id, payload, revision FROM orders"
            ):
                payload = self.open(sealed)
                payment = payload["payment"]
                if (
                    not payment.get("cancelled_at")
                    or now < datetime.fromisoformat(payment["period_end"])
                    or payload.get("state") in {"retiring", "retired"}
                ):
                    continue
                if connection.execute(
                    "SELECT 1 FROM requests WHERE order_id=? AND purpose='retire' AND revision=?",
                    (order, revision),
                ).fetchone():
                    continue
                self._queue(connection, order, "retire", revision, payload)
                count += 1
        return count

    def event(  # noqa: PLR0913 — result bound to exact immutable request
        self,
        order: str,
        owner: str,
        *,
        purpose: str,
        revision: int,
        public_sha: str,
        result: dict[str, Any],
    ) -> None:
        self.owner(order, owner)
        allowed = {"state", "ingress", "checks", "workflow_url", "failure_stage", "claim"}
        states = {
            "queued",
            "provisioning",
            "awaiting_dns",
            "failed",
            "retiring",
            "retired",
        }
        if set(result) - allowed or result.get("state") not in states:
            raise ValueError("Invalid lifecycle result")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT owner_tag, payload FROM orders WHERE id=?", (order,)
            ).fetchone()
            request = connection.execute(
                "SELECT public_sha FROM requests " "WHERE order_id=? AND purpose=? AND revision=?",
                (order, purpose, revision),
            ).fetchone()
            if not row or row[0] != self.tag(owner) or not request or request[0] != public_sha:
                raise ValueError("Lifecycle result does not own this published request")
            payload = self.open(row[1])
            tag = {
                "purpose": purpose,
                "revision": revision,
                "public_sha": public_sha,
                "digest": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
            }
            if payload.get("last_workflow_event") == tag:
                return
            prior = payload.get("state")
            if prior == "retired" or (
                (prior == "retiring" or payload.get("retirement_started")) and purpose != "retire"
            ):
                raise ValueError("A retiring order cannot be recreated")
            if (purpose == "provision" and result["state"] in {"retiring", "retired"}) or (
                purpose == "retire" and result["state"] not in {"retiring", "retired", "failed"}
            ):
                raise ValueError("Lifecycle purpose does not match the result")
            if "workflow_url" in result and not re.fullmatch(
                r"https://github\.com/scidsg/hushline/actions/runs/[1-9][0-9]{0,19}",
                result["workflow_url"],
            ):
                raise ValueError("Workflow URL escaped the owned repository")
            if "failure_stage" in result and not re.fullmatch(
                r"[a-z-]{1,40}", result["failure_stage"]
            ):
                raise ValueError("Invalid sanitized failure stage")
            if "claim" in result and not re.fullmatch(r"[A-Za-z0-9_-]{22}", result["claim"]):
                raise ValueError("Invalid private administrator claim")
            if "ingress" in result and not re.fullmatch(
                re.escape("hls-" + order[:28]) + r"-[a-z0-9-]+\.ondigitalocean\.app",
                result["ingress"],
            ):
                raise ValueError("Provider ingress escaped the owned app")
            checks = result.get("checks", {})
            if result["state"] == "awaiting_dns" and not (
                all(checks.get(field) is True for field in ("infrastructure", "configuration"))
                and result.get("ingress")
                and result.get("claim")
            ):
                raise ValueError("Owned infrastructure and initializer must pass before DNS")
            if set(checks) - {"infrastructure", "configuration", "tls", "health"} or any(
                not isinstance(value, bool) for value in checks.values()
            ):
                raise ValueError("Invalid lifecycle checks")
            if purpose == "retire" and result["state"] in {"retiring", "retired"}:
                payload["retirement_started"] = True
            payload["last_workflow_event"] = tag
            payload.update({key: value for key, value in result.items() if key != "checks"})
            payload["checks"] = {**payload.get("checks", {}), **checks}
            if purpose == "provision" and result["state"] == "failed":
                # A later check failure never paints earlier successes as failed.
                payload["checks"] = {**checks, **self.open(row[1]).get("checks", {})}
            connection.execute(
                "UPDATE orders SET payload=? WHERE id=?", (self.seal(payload), order)
            )

    def observation(self, order: str, owner: str, *, dns: bool, https_ok: bool) -> None:
        self.owner(order, owner)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT owner_tag, payload FROM orders WHERE id=?", (order,)
            ).fetchone()
            if not row or row[0] != self.tag(owner):
                raise ValueError("Order ownership is unverified")
            payload = self.open(row[1])
            if payload.get("retirement_started") or payload.get("state") not in {
                "awaiting_dns",
                "ready",
            }:
                return
            payload["dns_verified"] = dns
            payload["checks"] = {**payload.get("checks", {}), "tls": https_ok, "health": https_ok}
            if (
                dns
                and https_ok
                and all(
                    payload["checks"].get(field) is True
                    for field in ("infrastructure", "configuration")
                )
                and payload.get("claim")
            ):
                payload["state"] = "ready"
            elif payload.get("state") == "ready":
                payload["state"] = "awaiting_dns"
            connection.execute(
                "UPDATE orders SET payload=? WHERE id=?", (self.seal(payload), order)
            )

    def heartbeat(self, *, now: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO heartbeat(id, checked) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET checked=excluded.checked",
                (now,),
            )

    def unhealthy(self) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM heartbeat")

    def healthy(self, *, now: int) -> bool:
        with self.transaction() as connection:
            row = connection.execute("SELECT checked FROM heartbeat WHERE id=1").fetchone()
            return row is not None and 0 <= now - row[0] <= HEARTBEAT_SECONDS

    def publication_notice(self, order: str, *, failed: bool) -> None:
        with self.transaction() as connection:
            row = connection.execute("SELECT payload FROM orders WHERE id=?", (order,)).fetchone()
            if row is None:
                raise ValueError("Unknown publication order")
            payload = self.open(row[0])
            payload["publication_error"] = failed
            connection.execute(
                "UPDATE orders SET payload=? WHERE id=?", (self.seal(payload), order)
            )

    def result_keys(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            return [self.open(row[0]) for row in connection.execute("SELECT payload FROM orders")]

    def artifact_seen(self, identifier: str) -> bool:
        with self.transaction() as connection:
            return (
                connection.execute("SELECT 1 FROM artifacts WHERE id=?", (identifier,)).fetchone()
                is not None
            )

    def artifact_record(self, identifier: str) -> None:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", identifier):
            raise ValueError("Invalid verified artifact identity")
        with self.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO artifacts(id) VALUES (?)", (identifier,))

    def collection_cursor(self) -> int:
        with self.transaction() as connection:
            row = connection.execute("SELECT run_id FROM collection_cursor WHERE id=1").fetchone()
            return int(row[0]) if row else 0

    def track_run(self, identifier: str) -> None:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", identifier):
            raise ValueError("Invalid workflow identity")
        with self.transaction() as connection:
            connection.execute("INSERT OR IGNORE INTO workflow_runs(id) VALUES (?)", (identifier,))

    def collection_checkpoint(self, identifier: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO collection_cursor(id, run_id) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET run_id=excluded.run_id",
                (str(identifier),),
            )

    def unfinished_runs(self) -> list[str]:
        with self.transaction() as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM workflow_runs WHERE finished=0 LIMIT 1000"
                )
            ]

    def finish_run(self, identifier: str) -> None:
        with self.transaction() as connection:
            connection.execute("UPDATE workflow_runs SET finished=1 WHERE id=?", (identifier,))
