# Security

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository.

This is a personal project maintained on a best-effort basis, with no guaranteed response time.

## Threat model

- **Accounts are for people you trust.** A logged-in user feeds files to LibreOffice and
  ImageMagick, which are large parsers with a history of vulnerabilities. The backend
  container is hardened (no outbound network, unprivileged user, CPU, memory and process
  limits) to contain a malicious file, not to make hostile users safe.
- **Anonymous visitors** can only reach the login form (rate-limited) and the health check.
  Uploads are rejected before the file is read.
- **TLS is not included.** The app listens on `127.0.0.1` by default. Put an HTTPS reverse
  proxy in front before exposing it: credentials and documents otherwise travel in clear text.
- **Documents are not kept.** Each conversion runs in its own temporary directory, deleted
  once the PDF has been sent or the conversion has failed.
