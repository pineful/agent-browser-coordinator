# Contributing and release discipline

Use a separate development checkout and synthetic temporary databases. Never test against someone else's live browser or production database. Keep code, CLI examples, all three language guides, regression tests and version metadata consistent.

```sh
mkdir -p -m 700 dist
python -m scripts.release_gate --output-dir dist/new-reviewed-release
```

Review every path in config/release-allowlist.json, run python -m scripts.scan_public_release, and inspect the actual wheel, source distribution and source ZIP before publication. The pattern scan is not an exhaustive secret detector. Never publish runtime state, screenshots, credentials, account paths, private conversations, or private instructions. New source files must be intentionally added to the allowlist. Build artifacts are not automatically committed.

Install the resulting wheel in a new virtual environment from outside this checkout, check its import/version/CLI, and run a disposable mock workflow. Verify the source ZIP SHA-256 from a separate trusted record, restore into a new empty directory, and rerun tests. This is a clean Python environment and directory on the test host, not a claim of a separately isolated VM.

For a release, agree on scope and license, update CHANGELOG.md and package version, record exact source commit and artifact checksums, and verify the uploaded bytes/commit. [docs/ci-example.yml](docs/ci-example.yml) is a pinned, read-only workflow reference, not an active repository workflow. A maintainer can review and enable it with the required GitHub permissions. This release does not request extra workflow authorization or claim hosted CI passed. Keep older known-good source artifacts; runtime migration requires its own safe stop and drain plan. Do not downgrade or replace active state merely to match a source version.

Stable 0.3.5 deliberately excludes the experimental owner-liveness host bridge and unverified tab concurrency. Any future expansion must document cancellation, late responses, old writers, replay, unknown external outcomes, and safe recovery, with adversarial tests. Code that increments a timestamp is not by itself proof a remote worker is alive.

The release gate is mandatory and returns nonzero on any failure. Do not publish partial outputs or bypass a failed check. Read [the security review](docs/SECURITY_REVIEW.md), including same-OS-user and artifact-trust limitations.
