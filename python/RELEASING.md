# Releasing ibc2

The `ibc2` project already exists on PyPI. Every upload must use a version that has never been published.
For the next release, update `__version__` in `src/ibc2/__init__.py` (currently `0.1.0`) and add the
release notes to the root `CHANGELOG.md`. Bump the Java version in `../build.xml` only when the IBC Java
code changes.

## Check the release locally

For a full release check, use JDK 17, Ant, and set `IBC_BIN` to the `jars` directory from an offline TWS
or IB Gateway installation. From the repository root:

```
ant test jar
```

Then from `python/`:

```
python build_assets.py --jar ../resources/IBC.jar
python -m pip install -e ".[test]" build twine
python -m pytest -q
python -m build
python -m twine check dist/*
```

The GitHub release workflow runs these checks before publishing.

## Configure PyPI publishing once

In the existing `ibc2` project on PyPI, add a Trusted Publisher for GitHub Actions:

- Owner: `zalkabsi`
- Repository: `IBC2.0`
- Workflow: `release.yml`
- Environment: `pypi`

Create a GitHub Actions environment named `pypi` in the repository settings. The workflow uses PyPI's
OIDC Trusted Publishing, so no PyPI token is stored in GitHub.

## Publish a release

Merge and push the tested changes to the repository, then tag the release commit with the same version
as `__version__`. For example, if the next unused version is `0.1.1`:

```
git tag v0.1.1
git push origin v0.1.1
```

The `v*` tag starts `.github/workflows/release.yml`. It rebuilds the IBC jar, runs the Java and Python
tests, builds and checks the wheel and source distribution, then publishes them to PyPI. Confirm the
GitHub Actions run succeeds and `pip install --upgrade ibc2` shows the new version.
