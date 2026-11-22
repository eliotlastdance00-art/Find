# Security policy

## Supported versions

Only the latest release and the `main` branch receive fixes.

| Version | Supported |
|---|---|
| `main`, latest release | ✅ |
| older releases | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private reporting instead:
[**Report a vulnerability**](https://github.com/eliotlastdance00-art/Find/security/advisories/new)
(repository → *Security* → *Advisories* → *Report a vulnerability*).

Include what you found, how to reproduce it, and the version or commit. You can expect a first
answer within a week. Once a fix is released, the report is published as an advisory and you are
credited unless you prefer otherwise.

## What is in scope

Deepfake Detektor is a self-hosted application: uploaded files are analysed on the machine that
runs it and are not sent anywhere. Reports are especially welcome about:

* authentication and session handling (Argon2id password hashes, JWT bearer tokens, login throttling);
* access to another user's scans, media or reports;
* the upload pipeline: file-type detection, size and duration limits, FFmpeg and image decoding;
* path traversal, injection, or script execution through file names, metadata or report contents;
* the container image (non-root user, read-only file system) and the default configuration.

Out of scope: wrong verdicts of the detection models (use the *Wrong verdict* issue form), and
problems that require an administrator account or physical access to the server.

Design and hardening notes are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
