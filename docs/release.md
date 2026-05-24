# Release Checklist

This checklist is for preparing LambdaOpt `v0.1.0` production beta releases.

## Pre-Release Checks

- [ ] Version is bumped in `pyproject.toml`.
- [ ] Version is bumped in `lambdaopt/__init__.py`.
- [ ] `lambdaopt version --plain` prints the expected version.
- [ ] `CHANGELOG.md` includes the release entry.
- [ ] README and docs are reviewed.
- [ ] `make check` passes locally.
- [ ] Package build works locally.
- [ ] GitHub Actions CI passes on GitHub.
- [ ] AWS smoke test is completed in a sandbox or non-production AWS account.
- [ ] GitHub release notes are drafted.
- [ ] Release tag is created and pushed.

## Local Commands

Check repository state:

```bash
git status
```

Run the full local check suite:

```bash
make check
```

Build source distribution and wheel:

```bash
python -m build
```

Verify the CLI version:

```bash
lambdaopt version --plain
```

Expected output:

```text
0.1.0
```

## Tagging v0.1.0

Create the release tag after local checks and GitHub CI pass:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## GitHub Release

Draft a GitHub release for `v0.1.0` and include:

- release summary,
- safety defaults,
- known limitations,
- link to the AWS smoke test guide,
- link to IAM permissions docs.

## Beta Wording

Use beta wording in release notes. LambdaOpt is suitable for evaluation and non-production validation, with conservative read-only defaults. Do not describe it as a fully automated production mutation system.

## Known Limitations to Include

- No production mutation by default.
- Benchmarking different configurations requires candidate test functions or aliases.
- CloudWatch percentile availability may vary.
- Cold-start analysis depends on CloudWatch Logs access and log completeness.
- Cost estimates are approximate and configurable.
