# 0005 The public demo is a static copy of the service's answers

**Decision.** The public link serves precomputed answers of the real service for 32 restaurants and
every design the create screen can produce. The live service runs locally or in Docker; the offline
bundle runs from a folder or a zip with no network at all.

**Why.** A judge must be able to open the link at any time without a server waking up, and the
demo must not fail on a venue's network. The answers are the service's own (the export calls the
API in-process and a self-check fails the build if any file the page can request is missing), so
the static demo shows exactly what the live service would.

**What follows.** The static demo cannot answer designs outside the create screen, and a renewal
replays the first period's weeks (it says so). Browser tests run against the static site, the offline
bundle (from a file and over a local server with the network blocked), the live service and a phone
viewport; CI publishes only after all of them pass.
