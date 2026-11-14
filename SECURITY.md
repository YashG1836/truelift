# Security

TrueLift is a hackathon prototype. It holds no real customer, restaurant or payment data: every
customer, order and profit figure is simulated, and the demo OTP is shown on screen on purpose.

## Reporting a problem

Open a GitHub issue that describes the problem without exploit details, or contact the team through
the repository owner's GitHub profile and we will reply there. Please give us a few days before
publishing anything.

## What the service does to stay safe

- The model bundle is loaded only if it matches the SHA-256 checksum committed beside it, because
  unpickling runs code from the file; a bundle built with another scikit-learn version or on other
  inputs is refused with instructions.
- Every demo visitor has their own session (`X-Session`); one visitor cannot see or reset another's
  offers. OTPs expire after ten minutes and lock after five wrong attempts.
- The consent ledger is hash-chained: changing any stored approval breaks the chain, and the API
  reports it.
- Every response carries security headers; the page loads nothing from other origins (the font is
  bundled), so its Content-Security-Policy allows only its own origin.
- Errors are returned as RFC 9457 problem details without stack traces.
- The container runs as a non-root user with a health check.
- CodeQL code scanning runs in CI on every push.

## Not in scope for a prototype

Real authentication, rate limiting at the edge, secrets management and encryption at rest would come
from Zomato's own platform if TrueLift were adopted.
