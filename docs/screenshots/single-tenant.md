# Single Tenant screenshots

The release screenshot workflow captures the real application pages using synthetic
accounts and read-only local service responses. No payment, DNS change, provisioning,
or deletion occurs. The claim invitation is an invalid example and is masked.

These references keep every scene in the workflow’s documentation allowlist.
Each scene is captured at desktop and mobile sizes in light and dark themes.
Full-page captures include the entire form and its confirmation text.

For local capture, seed the disposable development stack with `docker compose run
--rm dev_data`, then start the fixture app with:

```sh
docker compose -f docker-compose.yaml -f docker-compose.screenshots.yaml up -d app
```

Resolve the capture manifest with `scripts/resolve-doc-screenshot-allowlist.py`, then
pass it to `scripts/capture-doc-screenshots.mjs` as in the release workflow.
Do not use the fixture entrypoint against a production database.

## Choose a plan

| Desktop light                                                                                     | Mobile light                                                                                    | Desktop dark                                                                                    | Mobile dark                                                                                   |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-plans/single-tenant-plans-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-plans/single-tenant-plans-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-plans/single-tenant-plans-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-plans/single-tenant-plans-mobile-dark-full.png) |

## License selection

| Desktop light                                                                                           | Mobile light                                                                                          | Desktop dark                                                                                          | Mobile dark                                                                                         |
| ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-licenses/single-tenant-licenses-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-licenses/single-tenant-licenses-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-licenses/single-tenant-licenses-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-licenses/single-tenant-licenses-mobile-dark-full.png) |

## Annual checkout

| Desktop light                                                                                         | Mobile light                                                                                        | Desktop dark                                                                                        | Mobile dark                                                                                       |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-payment/single-tenant-payment-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-payment/single-tenant-payment-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-payment/single-tenant-payment-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-payment/single-tenant-payment-mobile-dark-full.png) |

## Choose a domain

| Desktop light                                                                                       | Mobile light                                                                                      | Desktop dark                                                                                      | Mobile dark                                                                                     |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-domain/single-tenant-domain-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-domain/single-tenant-domain-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-domain/single-tenant-domain-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-domain/single-tenant-domain-mobile-dark-full.png) |

## DNS records

| Desktop light                                                                                 | Mobile light                                                                                | Desktop dark                                                                                | Mobile dark                                                                               |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-dns/single-tenant-dns-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-dns/single-tenant-dns-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-dns/single-tenant-dns-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-dns/single-tenant-dns-mobile-dark-full.png) |

## Deployment checks

| Desktop light                                                                                             | Mobile light                                                                                            | Desktop dark                                                                                            | Mobile dark                                                                                           |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-provision/single-tenant-provision-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-provision/single-tenant-provision-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-provision/single-tenant-provision-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-provision/single-tenant-provision-mobile-dark-full.png) |

## Instance ready

| Desktop light                                                                                     | Mobile light                                                                                    | Desktop dark                                                                                    | Mobile dark                                                                                   |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-ready/single-tenant-ready-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-ready/single-tenant-ready-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-ready/single-tenant-ready-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-ready/single-tenant-ready-mobile-dark-full.png) |

## Claim administrator

| Desktop light                                                                                     | Mobile light                                                                                    | Desktop dark                                                                                    | Mobile dark                                                                                   |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-claim/single-tenant-claim-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-claim/single-tenant-claim-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-claim/single-tenant-claim-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-claim/single-tenant-claim-mobile-dark-full.png) |

## Subscription management

| Desktop light                                                                                                   | Mobile light                                                                                                  | Desktop dark                                                                                                  | Mobile dark                                                                                                 |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-subscription/single-tenant-subscription-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-subscription/single-tenant-subscription-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-subscription/single-tenant-subscription-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-subscription/single-tenant-subscription-mobile-dark-full.png) |

## Renewal cancelled

| Desktop light                                                                                             | Mobile light                                                                                            | Desktop dark                                                                                            | Mobile dark                                                                                           |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-cancelled/single-tenant-cancelled-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-cancelled/single-tenant-cancelled-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-cancelled/single-tenant-cancelled-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-cancelled/single-tenant-cancelled-mobile-dark-full.png) |

## Deletion in progress

| Desktop light                                                                                           | Mobile light                                                                                          | Desktop dark                                                                                          | Mobile dark                                                                                         |
| ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-retiring/single-tenant-retiring-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-retiring/single-tenant-retiring-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-retiring/single-tenant-retiring-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-retiring/single-tenant-retiring-mobile-dark-full.png) |

## Instance deleted

| Desktop light                                                                                         | Mobile light                                                                                        | Desktop dark                                                                                        | Mobile dark                                                                                       |
| ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| [desktop light](./releases/latest/single-tenant-retired/single-tenant-retired-desktop-light-full.png) | [mobile light](./releases/latest/single-tenant-retired/single-tenant-retired-mobile-light-full.png) | [desktop dark](./releases/latest/single-tenant-retired/single-tenant-retired-desktop-dark-full.png) | [mobile dark](./releases/latest/single-tenant-retired/single-tenant-retired-mobile-dark-full.png) |
