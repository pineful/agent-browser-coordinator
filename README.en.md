# Agent Browser Coordinator

[한국어](README.md) · [English](README.en.md) · [日本語](README.ja.md)

Cooperative ordering for agents that share a browser UI.

## Why this exists

Several agents may share one desktop, focused tab, keyboard, and mouse. In that environment, unrelated clicks, typing, native file pickers, and screen observations can interfere even when tasks use different tabs. This project gives participating workers a common ownership record, a wait queue, safe handoff, and a way to resume after interruption.

This is a conservative one-resource policy for a shared UI. It does not claim that every browser operation requires serialization, that all tab-level DOM APIs conflict, or that collisions are impossible. Independent tab operations are a future validation topic, not a feature of this release.

## What is included

Version **0.3.4** provides a Python library and CLI with one local SQLite database, atomic ownership, priority/aging, unique request IDs, generation tokens, begin/end tracking, tab retention, and explicit verified recovery. It has no third-party runtime dependency. Every participating tool wrapper must use the coordinator; direct calls are not forcibly blocked.

No browser driver, login, service account, daemon, automatic task messaging, or live state is included. The experimental v0.4 owner-message/keepalive work is **not shipped or activated** here. It still needs host lifecycle and timeout integration.

## Start here

- [Install](docs/en/INSTALL.md)
- [Agent installation prompt samples](docs/en/AGENT_INSTALL_PROMPTS.md)
- [Configure one shared resource](docs/en/CONFIGURATION.md)
- [Use the CLI and Python API](docs/en/USAGE.md)
- [Handoff and recovery](docs/en/RECOVERY.md)
- [Limits and future work](docs/en/LIMITATIONS.md)
- [Contribute and release](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md)

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agent-browser-coordinator --version
python demo.py
```

The demo uses only synthetic workers and temporary state; it does not open a browser. Read the initialization and recovery preconditions before connecting real tools. A successful ownership grant never grants permission for an external action.

[MIT license](LICENSE). See [source and licensing](NOTICE.md).

[Pre-release security review and mandatory release gate](SECURITY_REVIEW.md)
