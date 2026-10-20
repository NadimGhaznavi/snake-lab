---
title: App Discovery Settings
author_profile: true
layout: single
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Snake Lab declares its inventory metadata in
`snakelab/constants/DSnakeLab.py`. Register **SnakeLab** in CMDB and scan the
production installation at `/opt/prod/snakelab`. The declarations include the
application type, Simulation Server subtype, supplier, release codename, the
`snakelab` MariaDB catalog, and the persistent `logs` directory. Database
references describe same-host catalogs; database credentials remain separate.

The `control`, `telemetry`, and `events` entries in `CMDB_NETWORK` also supply
runtime listener defaults. See [Snake Lab network configuration](/pages/install.html#network-configuration)
for overrides and restart instructions. CMDB network discovery is still deferred.

These reference guides are adapted from the CMDB project's `pages/cmdb-*.md`
and `pages/app-discovery.md` documentation.

Use this guide when making an application discoverable by CMDB. Each setting
has a separate reference with its declaration format and behavior.

| Setting | Purpose | Discovery status |
| --- | --- | --- |
| `VERSION` | Required literal application release; see the constants-file convention below. | Implemented |
| [CMDB_TYPE]({{ site.baseurl }}{% link pages/cmdb-type.md %}) | Broad software classification | Implemented |
| [CMDB_SUBTYPE]({{ site.baseurl }}{% link pages/cmdb-subtype.md %}) | More specific software classification | Implemented |
| [CMDB_SUPPLIER]({{ site.baseurl }}{% link pages/cmdb-supplier.md %}) | Software supplier | Implemented |
| [CMDB_CODENAME]({{ site.baseurl }}{% link pages/cmdb-codename.md %}) | Release codename | Implemented |
| [CMDB_COMPONENTS]({{ site.baseurl }}{% link pages/cmdb-components.md %}) | Persistent filesystem data components | Implemented |
| [CMDB_DATABASES]({{ site.baseurl }}{% link pages/cmdb-databases.md %}) | References to same-host MariaDB catalogs | Implemented |
| [CMDB_NETWORK]({{ site.baseurl }}{% link pages/cmdb-network.md %}) | Default listener declarations and runtime wiring | Application standard available; discovery coming |

## Registration and constants file

Named SoftwareSystems created through Add Application are discovery targets.
For `MyCount`, the scanner checks `/opt/prod/mycount`, using
`DCMDB.BASE_INSTALL_DIR` and the lowercase application name. If that directory
exists, it reads `/opt/prod/mycount/mycount/constants/DMyCount.py` through the
inventory agent's SSH interface, or directly for the local host.
For `CMDB`, it reads `/opt/prod/cmdb/cmdb/constants/DCMDB.py` and the literal
`DCMDB.VERSION`. Register `CMDB` through Add Application to enable discovery
on inventoried hosts. Development checkouts under `/opt/dev` are not installed
application targets.

Application names must match `[A-Za-z_][A-Za-z0-9_]*` for this discovery convention.
Definitions with other names can still be saved but are skipped by discovery.

A nonempty literal string assigned to `VERSION` at module or class scope
confirms an installation. Annotated assignments such as
`VERSION: Final[str] = "1.2.3"` are supported. The constants file is parsed,
never imported or executed; computed versions are not evaluated.

All `CMDB_*` settings are optional for current application detection. Use direct
literals at module or class scope; annotated assignments are supported. CMDB
reads constants as data and does not execute the application. Network declarations
remain preparatory and are not yet read by the scanner.

## Shared metadata rules

The four string settings `CMDB_TYPE`, `CMDB_SUBTYPE`, `CMDB_SUPPLIER`, and
`CMDB_CODENAME` share these rules:

Values are trimmed and must be nonempty strings of at most 255 characters,
without control characters. Missing, computed, or invalid optional values are
ignored and do not erase metadata already stored for a matching release.
`VERSION` remains required for detection. Metadata fills missing fields on a
compatible release; conflicting values select or create a separate definition,
preserving definitions used by other hosts. When optional fields are omitted,
discovery prefers the host's existing compatible release. A new version stores
only the metadata supplied by that observation.
Named applications remain discovery targets after their type is populated.

## Updating an app

Add the relevant declarations to the existing constants file, preserving a literal
`VERSION`. Keep credentials out of all discovery metadata. Follow each setting's
reference for validation and any runtime wiring, then register the application
and use Re-Scan Applications to verify implemented discovery settings.

For deployment identities, scan scheduling, failure handling, and pruning, see
[application discovery behavior](https://cmdb.osoyalce.com/pages/software-deployment.html#application-discovery).
