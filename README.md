# ci-workflows

Mavenor's public reusable CI component. Projects built by the Mavenor engine call these workflows from
a three-line stub, so the governance logic lives in one place rather than being copied into every
project.

## What is here

| Path | What it does |
|---|---|
| `.github/workflows/pr-title.yml` | checks a pull-request title against the standard shape |
| `.github/workflows/ticket-template.yml` | checks ticket pages and the project state |
| `.github/workflows/secret-scan.yml` | scans the full history for credentials, using gitleaks |
| `lib/ci_policy.py` | the validator the ticket/project-state workflow runs |
| `lib/project_state_conformance.py` | derives the project-state contract from the calling project's own template |

## How a project calls them

```yaml
# .github/workflows/ticket-template.yml in the project repository
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]
permissions:
  contents: read
jobs:
  ticket-template:
    uses: Journeys-and-Rewards/ci-workflows/.github/workflows/ticket-template.yml@v1.0.0
```

Callers pin an **immutable version tag**. There is no movable major alias, so the checks a project runs
cannot change underneath it.

## The contract comes from your project

`ticket-template.yml` reads the canonical project-state template from **your** repository, at
`docs/templates/project-state.template.md`. The engine scaffolds it into every project it creates. If
it is missing the check fails and says how to restore it; it is never substituted, because a project
judged against somebody else's contract has not been judged at all.

## Notes

- No workflow here requires a secret, and no caller passes one.
- Secret scanning uses [gitleaks](https://github.com/gitleaks/gitleaks) — free and self-hosted. No paid
  GitHub plan is required.
- Releases are immutable tags (`v1.0.0`, `v1.0.1`, …) at an exact commit; tags are never moved.
