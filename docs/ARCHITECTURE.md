# Runtime Architecture (ASCII)

Human-owned only (non-agentic): release and infrastructure control plane.

```text
                                                 +-----------------------------------------+
                                                 | scidsg/hushline                         |
                                                 | 1) bump hushline/version.py             |
                                                 | 2) create release tag (vX.Y.Z)          |
                                                 +-------------------+---------------------+
                                                                     |
                                                                     v
                                                 +-----------------------------------------+
                                                 | build-release.yml                       |
                                                 | publish hushline/hushline:vX.Y.Z image  |
                                                 +-------------------+---------------------+
                                                                     |
                      +-----------------------+----------------------+-------------------------------------------------+
                      |                                              |                                                 |
                      v                                              v                                                 v
  +-----------------------------------------+   +------------------------------------------+   +--------------------------------------------+
  | STAGING                                 |   | PRODUCTION                               |   | SINGLE TENANT INSTANCES                    |
  | trigger path                            |   | trigger path                             |   | trigger path                               |
  | scidsg/hushline-infra                   |   | Terraform Cloud workspace: prod          |   | Terraform Cloud workspace:                 |
  | - edit hushline-env/hushline.tf tag     |   | - manually set VCS branch to vX.Y.Z      |   | - hushline-infra-ENV_NAME                  |
  | - merge to main (workspace: staging)    |   | - manually start/confirm apply run       |   | - manually set VCS branch to vX.Y.Z        |
  |                                         |   |                                          |   | - manually start/confirm apply run         |
  +-------------------+---------------------+   +-------------------+----------------------+   +-------------------+------------------------+
                      |                                             |                                              |
                      v                                             v                                              v
      +-----------------------------------+         +-----------------------------------+          +-----------------------------------+
      | Terraform apply (staging)         |         | Terraform apply (prod)            |          | Terraform apply (tenant env)      |
      | - DO App Platform app             |         | - DO App Platform app             |          | - DO App Platform app             |
      | - managed Postgres (pg16)         |         | - managed Postgres (pg16)         |          | - managed Postgres (pg16)         |
      | - Spaces bucket + CORS            |         | - Spaces bucket + CORS            |          | - Spaces bucket + CORS            |
      +-----------------------------------+         +-----------------------------------+          +-----------------------------------+
```
