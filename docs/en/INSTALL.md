# Install

Installation verifies the Python package only. Operational readiness additionally requires connecting every real browser tool adapter, registering the protocol in the host's persistent agent instructions without overwriting user instructions, checking a common DB and current browser state, and verifying isolation capabilities with a real read-only smoke test. Without access to those components, report installation success only. The coordinator does not supply browser control or an automatic heartbeat bridge.

Use Python 3.10+ on a local POSIX filesystem. This release is tested in an isolated Linux environment; it does not certify Windows, network filesystems, or every Python/platform combination. SQLite is supplied by Python. No browser, network port, credentials, or service is configured by installation.

Download or clone this repository, enter its directory, then run:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agent-browser-coordinator --version
python -m agent_browser_coordinator --version
```

The source build uses Setuptools from the configured Python package index. For an offline installation, use a verified release wheel:

```sh
python -m pip install --no-index --no-deps ./agent_browser_coordinator-0.3.5-py3-none-any.whl
```

This document does not claim a PyPI publication. Do not run an unrelated similarly named index package. Verify the actual repository/release identity and SHA-256 first. To remove the installed package: `python -m pip uninstall agent-browser-coordinator`. Removing a package does not stop workers or delete runtime state.

From a source checkout, run the synthetic checks:

```sh
python -m scripts.validate_release
python -m scripts.package_release
```

[Configuration](CONFIGURATION.md) · [Usage](USAGE.md) · [Recovery](RECOVERY.md)
