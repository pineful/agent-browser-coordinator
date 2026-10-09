# Security and privacy boundaries

This is cooperative coordination, not authentication, an OS lock, a browser sandbox, or remote-call cancellation. A caller with DB access can impersonate actor labels. A client that bypasses the coordinator can bypass coordination. Fencing is checked by this library; browser servers do not independently enforce these tokens.

Keep a runtime DB private and on a single local filesystem accessible only to trusted participating processes. Do not store credentials, URLs, private content, or browser state in actor, tab, checkpoint, evidence, or request fields. Do not publish runtime DBs, WAL/SHM files, screenshots, environment secrets, or diagnostic logs.

If you find a problem, do not put secrets or private runtime records in a public issue. Use a minimal synthetic reproduction. Follow the recovery guide before changing an active deployment. No security contact address or supported private disclosure channel is claimed before repository setup is verified.
