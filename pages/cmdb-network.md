---
title: CMDB_NETWORK App Developer Guide
author_profile: true
layout: single
---

[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})

## Status and purpose

`CMDB_NETWORK` is the application-side standard for declaring an app's default
network listeners. Apps should adopt it now so their declarations are ready for
future CMDB discovery. CMDB does not yet collect, store, or display these network
declarations. No scanner, schema, or UI changes are required when updating an app.

The declaration must drive the app's listener defaults, so inventory metadata
and runtime defaults have one source. MyCount and CMDB use this pattern, with
production JSON overrides resolved by `Configuration` and `Network` interfaces.
For CMDB's own production settings, see
[runtime configuration](https://cmdb.osoyalce.com/pages/installation.html#runtime-configuration).

## Declare the listeners

Put `CMDB_NETWORK` in the app's existing constants file beside its literal
`VERSION` and other `CMDB_*` metadata. The application discovery convention is
`/opt/prod/<lowercase-name>/<lowercase-name>/constants/D<Name>.py`; for example,
CMDB uses `/opt/prod/cmdb/cmdb/constants/DCMDB.py`. See
[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %}#registration-and-constants-file)
for the existing registration and constants-file convention.

This fictional Example app declares two listeners:

```python
from typing import Final


class DExample:
    VERSION: Final[str] = "1.0.0"
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (
        ("http", "0.0.0.0", 18080),
        ("backend", "127.0.0.1", 18081),
    )
```

Each entry is a literal `(use, interface, port)` tuple:

| Field | Meaning and app-side requirements |
| --- | --- |
| `use` | A unique, nonempty string identifying the listener's role. Keep it stable because configuration and consumers look it up by this name. Examples include `http`, `https`, `report`, and `backend`. |
| `interface` | An IPv4 bind address as a string. `0.0.0.0` listens on all IPv4 interfaces; `127.0.0.1` listens on loopback only. |
| `port` | An integer from 1 to 65535. Strings and booleans are invalid. |

Declare every listener owned or configured by the app, including internal
listeners and managed proxy listeners. Use direct literals at module or class
scope. Do not construct the declaration from environment variables, function
calls, other constants, or comprehensions: the discovery convention reads
constants as data without importing or executing application code.

`use` identifies a role; this tuple has no separate transport field. The current
MyCount and CMDB implementations use IPv4 addresses. Hostnames, IPv6, Unix
sockets, and transport-specific extensions are outside this documented pattern.

Outbound dependencies such as MariaDB and GeoIP retain their own connection
settings. Declare database references separately with `CMDB_DATABASES`, as
described in the
[CMDB_DATABASES guide]({{ site.baseurl }}{% link pages/cmdb-databases.md %}).
Never place credentials in `CMDB_NETWORK` or the network JSON file.

## Wire the app to the declaration

Replace the old listener host and port constants with lookups by `use`. Avoid
tuple-position lookups and duplicate fallback values. In the reference pattern:

```python
interface, port = Network.binding("http")
```

`Network.binding` returns the resolved bind address and port. Route all consumers
through the same resolver: server startup, managed proxy listeners and upstreams,
installation health checks, and any router mapping creation or cleanup.
Only include the consumers the app actually has.

For a local client such as a health check or proxy upstream, use
`Network.destination(use)`. It returns the configured address and port, replacing
the wildcard bind address `0.0.0.0` with `127.0.0.1`. Specific addresses remain
unchanged. Existing server CLI overrides such as `--host` and `--port` should
continue to work for an individual invocation.

## Production overrides

Follow the MyCount and CMDB pattern with `conf/<app>.json` beneath the production
installation directory. For the fictional Example app, a partial override is:

```json
{
  "network": {
    "http": {
      "interface": "127.0.0.1",
      "port": 19080
    }
  }
}
```

Resolve settings in this order, from lowest to highest precedence:

1. Literal `CMDB_NETWORK` defaults.
2. Production JSON overrides for known uses and fields.
3. Supported command-line overrides for that invocation.

A missing file uses the defaults. Omitted uses and fields inherit their defaults.
Reject malformed JSON, unknown uses or fields, invalid IPv4 addresses, and
invalid ports with an error identifying the file or setting. Invalid files
must not silently fall back to defaults. Read resolved configuration once per
process; restart affected processes to apply edits.

The installer should create a readable network configuration from the declaration
only when the file is missing, preserve existing files during reinstall and
upgrade, and validate configuration before stopping services. A restart command
should validate first, then apply all affected settings, including generated
proxy configuration or router mappings where applicable. Deployment health
checks must use the same resolved settings as the services they check.

The declaration describes **default inventory**, even when production JSON or CLI
arguments change the actual listener. Updating an app to this standard does not
promise discovery of its effective runtime settings. Future scanner behavior,
validation rules, persistence, and display remain deferred.

## Verify an app update

- Change the declaration in a test and confirm server defaults and relevant
  proxy, health-check, and router consumers follow the new address and port.
- Verify a missing config file and partial overrides resolve correctly, and
  supported CLI arguments take precedence.
- Verify invalid configuration fails clearly before restart actions, and
  reinstall or upgrade preserves an existing configuration file.
- Verify local destinations translate wildcard bindings to loopback and retain
  specific addresses.
- Verify edits take effect after restart and all affected consumers receive the
  new settings.
- Document the app's uses, production config path, and restart procedure, and
  remove replaced listener constants and hardcoded values from runtime consumers.
