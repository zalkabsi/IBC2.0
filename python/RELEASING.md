# Releasing ibc2

1. Make sure `ant test` and `pytest` pass (CI does this on every push).
2. Bump `__version__` in `src/ibc2/__init__.py` and the `ver` property in `../build.xml`.
3. One-time: on pypi.org create the project `ibc2` (or add a *pending publisher*) with
   - owner/repo: this repository, workflow: `release.yml`, environment: `pypi`.
   In GitHub, create an environment named `pypi`. No token is stored anywhere.
4. `git tag v0.1.0 && git push origin v0.1.0` - the workflow builds the jar and wheel and publishes.

Local build for testing:

```
ant jar                       # needs IBC_BIN pointing at a Gateway/TWS jars folder
cd python
python build_assets.py
python -m build
```
