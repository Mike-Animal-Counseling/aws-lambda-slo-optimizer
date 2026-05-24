# PyPI Release

LambdaOpt publishes with PyPI Trusted Publishing. The GitHub Actions workflow does not store long-lived PyPI API tokens.

## One-Time PyPI Setup

Create the project on PyPI or configure a pending trusted publisher for the package name:

```text
aws-lambda-slo-optimizer
```

In PyPI, configure Trusted Publishing with:

- Repository owner: `Mike-Animal-Counseling`
- Repository name: `aws-lambda-slo-optimizer`
- Workflow filename: `publish.yml`
- Environment: leave empty unless you add a GitHub environment to the workflow later

The workflow file is:

```text
.github/workflows/publish.yml
```

## Release Flow

1. Ensure local checks pass:

```bash
make check
python -m build
```

2. Commit all release changes.

3. Create and push the tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Alternatively, publish a GitHub Release for the tag. The publish workflow runs on both `v*` tag pushes and published GitHub releases.

## Verify the Publish

After the workflow succeeds, install from PyPI in a fresh environment:

```bash
python -m venv .venv-test
source .venv-test/bin/activate
python -m pip install aws-lambda-slo-optimizer
lambdaopt version --plain
```

Expected output:

```text
0.1.0
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv-test
.\.venv-test\Scripts\Activate.ps1
python -m pip install aws-lambda-slo-optimizer
lambdaopt version --plain
```

## Safety

The publishing workflow does not use AWS credentials. It builds and publishes Python package artifacts only.

The publishing workflow does not run real AWS integration tests. AWS-facing tests in CI must use mocks, stubs, or local fixtures. Real AWS smoke tests are manual and should be run from a sandbox or non-production AWS account.
