# Reuse the pinned Debian-based runtime already used by local tooling.
FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
RUN apt-get update && apt-get install -y --no-install-recommends antiword=0.37-16 && rm -rf /var/lib/apt/lists/*
USER 65534:65534
ENTRYPOINT ["antiword", "-x", "db", "-"]
