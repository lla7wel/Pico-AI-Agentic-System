// ca_cert.h — TLS trust configuration for the WSS link.
//
// Fly.io serves a Let's Encrypt certificate, which chains to the ISRG Root X1
// CA. Two options:
//
//   USE_CA_PINNING 0 (default): connect with beginSSL() and skip certificate
//     verification. Simplest and lowest RAM, but the link is not authenticated
//     — fine for bring-up on a trusted network; understand the tradeoff.
//
//   USE_CA_PINNING 1: verify the server against the single pinned root below.
//     Pinning ONE root (not a full CA bundle) keeps the BearSSL memory
//     footprint small while still authenticating the server.
//
// To enable pinning: set USE_CA_PINNING to 1 and paste the current ISRG Root
// X1 PEM into WS_CA_CERT. Get it from https://letsencrypt.org/certificates/
// (download "ISRG Root X1", PEM). It is left blank here on purpose rather than
// shipping a possibly-stale copy.
#pragma once

// Whether the link to WS_HOST:WS_PORT is TLS (wss://) or plaintext (ws://).
// Fly.io (production) terminates TLS at 443 -> WS_USE_TLS 1.
// A local dev backend (e.g. `uvicorn ... --port 8080`, no TLS) -> WS_USE_TLS 0.
// Define this in secrets.h per-deployment; default to TLS if not set there.
#ifndef WS_USE_TLS
#define WS_USE_TLS 1
#endif

#define USE_CA_PINNING 0

#if USE_CA_PINNING
static const char WS_CA_CERT[] PROGMEM = R"CERT(
-----BEGIN CERTIFICATE-----
... paste ISRG Root X1 PEM here ...
-----END CERTIFICATE-----
)CERT";
#endif
