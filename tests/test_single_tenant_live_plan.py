"""New customer plan guards preserve production, existing instances and allowances."""

from copy import deepcopy

import pytest

from scripts.single_tenant_live_plan import RESOURCES, guard_create, guard_delete, identity

ORDER = "a" * 32


def credentials() -> dict[str, str]:
    return {
        "DO_TOKEN": "approved-unit-test-only-token",
        "SECRET_KEY": "fresh-unit-secret",
        "ENCRYPTION_KEY": "fresh-unit-fernet",
        "SESSION_FERNET_KEY": "fresh-unit-session",
    }


def create(plan: dict, order: str, limit: int | None) -> None:
    secrets = credentials()
    token = secrets.pop("DO_TOKEN")
    guard_create(plan, order, limit, automation_token=token, app_secrets=secrets)


def deletion(plan: dict, order: str, ids: dict, *, phase: str) -> None:
    scope = creation()
    scope["resource_changes"] = plan["resource_changes"]
    guard_delete(scope, order, ids, phase=phase, automation_token=credentials()["DO_TOKEN"])


def creation(limit: int | None = 25) -> dict:
    name, app = identity(ORDER)
    resources = []
    for address in sorted(RESOURCES):
        after = {"name": name}
        unknown = {}
        if address == "digitalocean_app.tenant":
            services = []
            for kind in ["app", "app-onion"]:
                env = [
                    {
                        "key": "SINGLE_TENANT_INSTANCE_ORDER",
                        "value": ORDER,
                        "type": "GENERAL",
                        "scope": "RUN_TIME",
                    }
                ]
                env.extend(
                    {
                        "key": key,
                        "value": value,
                        "type": "SECRET",
                        "scope": "RUN_TIME",
                    }
                    for key, value in credentials().items()
                    if key != "DO_TOKEN"
                )
                if limit is not None:
                    env.append(
                        {
                            "key": "SINGLE_TENANT_LICENSE_LIMIT",
                            "value": str(limit),
                            "type": "GENERAL",
                            "scope": "RUN_TIME",
                        }
                    )
                services.append(
                    {
                        "name": kind,
                        "env": env,
                        "git": [
                            {
                                "branch": "single-tenant/" + ORDER,
                                "repo_clone_url": "https://github.com/scidsg/hushline.git",
                            }
                        ],
                        "dockerfile_path": "Dockerfile.prod",
                    }
                )
            after = {"spec": [{"name": app, "service": services}], "project_id": None}
        if address in {"digitalocean_app.tenant", "digitalocean_database_cluster.tenant"}:
            unknown["project_id"] = True
        if address == "digitalocean_database_firewall.tenant":
            after = {"cluster_id": None}
            unknown["cluster_id"] = True
        resources.append(
            {
                "address": address,
                "change": {
                    "actions": ["create"],
                    "before": None,
                    "after": after,
                    "after_unknown": unknown,
                },
            }
        )
    return {
        "resource_changes": resources,
        "variables": {key: {"value": value} for key, value in credentials().items()},
        "configuration": {
            "provider_config": {
                "digitalocean": {
                    "full_name": "registry.terraform.io/digitalocean/digitalocean",
                    "expressions": {"token": {"references": ["var.DO_TOKEN"]}},
                }
            }
        },
    }


def test_numbered_and_unlimited_entitlements_require_exact_new_resources() -> None:
    create(creation(25), ORDER, 25)
    create(creation(None), ORDER, None)


@pytest.mark.parametrize("actions", [["update"], ["delete", "create"], ["delete"], ["no-op"]])
def test_creation_cannot_mutate_or_adopt_existing_resources(actions: list[str]) -> None:
    plan = creation()
    plan["resource_changes"][0]["change"]["actions"] = actions
    with pytest.raises(ValueError, match="cannot update"):
        create(plan, ORDER, 25)


def test_new_instance_cannot_join_production_project() -> None:
    plan = creation()
    app = next(r for r in plan["resource_changes"] if r["address"] == "digitalocean_app.tenant")
    app["change"]["after"]["project_id"] = "existing-production-project"
    with pytest.raises(ValueError, match="existing project"):
        create(plan, ORDER, 25)


def test_unlimited_cannot_silently_receive_finite_licenses() -> None:
    with pytest.raises(ValueError, match="Unlimited"):
        create(creation(25), ORDER, None)


def test_paid_license_count_must_reach_both_app_services() -> None:
    with pytest.raises(ValueError, match="paid order"):
        create(creation(24), ORDER, 25)


def test_legacy_test_order_is_never_adopted_into_live_namespace() -> None:
    with pytest.raises(ValueError, match="new customer"):
        identity("d9096a7ac4a4a90198550588df08fdcd")


def test_deletion_keeps_project_until_services_are_absent() -> None:
    ids = {address: "owned-" + address for address in RESOURCES}
    service_plan = {
        "resource_changes": [
            {
                "address": address,
                "change": {"actions": ["delete"], "before": {"id": ids[address]}, "after": None},
            }
            for address in RESOURCES - {"digitalocean_project.tenant"}
        ]
    }
    deletion(service_plan, ORDER, ids, phase="services")
    with pytest.raises(ValueError, match="two-phase"):
        deletion(service_plan, ORDER, ids, phase="project")
    foreign = deepcopy(service_plan)
    foreign["resource_changes"][0]["change"]["before"]["id"] = "another-customer-id"
    with pytest.raises(ValueError, match="another instance"):
        deletion(foreign, ORDER, ids, phase="services")
    project = {
        "resource_changes": [
            {
                "address": "digitalocean_project.tenant",
                "change": {
                    "actions": ["delete"],
                    "before": {"id": ids["digitalocean_project.tenant"]},
                    "after": None,
                },
            }
        ]
    }
    deletion(project, ORDER, ids, phase="project")


def test_inherited_production_credential_and_shared_secret_fail_closed() -> None:
    plan = creation()
    plan["variables"]["DO_TOKEN"]["value"] = "unapproved-other-account-token"
    with pytest.raises(ValueError, match="dedicated cloud credential"):
        create(plan, ORDER, 25)
    plan = creation()
    plan["variables"]["ENCRYPTION_KEY"]["value"] = "inherited-other-instance-key"
    with pytest.raises(ValueError, match="inherited secrets"):
        create(plan, ORDER, 25)


def test_runtime_cannot_ignore_the_new_instance_secret_variables() -> None:
    plan = creation()
    app = next(r for r in plan["resource_changes"] if r["address"] == "digitalocean_app.tenant")
    env = app["change"]["after"]["spec"][0]["service"][0]["env"]
    next(entry for entry in env if entry["key"] == "ENCRYPTION_KEY")["value"] = "other-instance-key"
    with pytest.raises(ValueError, match="Runtime inherited"):
        create(plan, ORDER, 25)
