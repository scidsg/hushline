# Deploying Development Instances
PRs opened against the `scisdg/hushline` repo can be deployed to isolated development instances.

## Pre-requisites
In order to create and destroy development instances, you will need the ability to tag pull requests. This requires "triage" permissions on the `scisdg/hushline` repo at minimum.

## Requirements
In order to successfully deploy a development instance, a PR must successfully build the docker image. If the docker image fails to build (which includes tests passing) it will fail to deploy.

## Deploying a Development Instance
To create a development instance from a pull request, add the `deploy` label to the PR, triggering the `Deploy/Destroy Branch Dev Environment` GitHub Actions workflow. This workflow will create a new Terraform workspace for the staged changes, plan, and apply the changes. Once this workflow completes, a comment with the url for the development instance will be added to the pull request.

## Redeploying after pushing changes to the PR
When changes are pushed to a PR which has been deployed to a development instance, the development instance will automatically be redeployed. You do not need to re-run the `deploy` workflow.

## Destroying dev instances
Dev instances are automatically destroyed when a PR is closed or merged. Additionally, dev instances can be explicitly destroyed by applying the `destroy` label.

## Caveats
The destroy workflow will only attempt to destroy development instances if the PR has the `deploy` label. This is to avoid failed destroy workflow runs on PRs which were never deployed.
