---
title: CMDB_DATABASES App Developer Guide
author_profile: true
layout: single
---

[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})

## Declare database references

The constants file may declare databases used by the application:

```python
CMDB_DATABASES = (("MyCount", "mycount"),)
```

`CMDB_DATABASES` is optional and accepts a literal tuple or list of `(label,
catalog)` pairs at module or class scope; annotated assignments are supported.
`VERSION` is still required for application detection. Labels and catalog names
are trimmed, nonempty strings without control characters. Labels are limited to
255 characters. Computed declarations and malformed entries are ignored, and
duplicate pairs are recorded once.

Each literal tuple or list entry contains an application connection label and an
exact MariaDB catalog name. Names are case-sensitive; catalog names are limited
to 64 characters. Invalid entries are ignored and constants are never executed.
Application discovery refreshes MariaDB inventory on that same machine using
its default local socket, including during Re-Scan Applications and Add Application.
Only catalogs observed in that refresh are eligible for a new connection.
Missing catalogs and failed reads preserve previously recorded connections.

When a catalog matches, discovery creates a named `MariaDB Client` Component
within the application release and a DataProvider deployment on its machine.
`DeployedComponentsUsage` links the application deployment to that provider.
ProviderConnection is owned by the provider and references the MariaDB server's
DataManager; its inherited name records the connection label. The provider's
`dataPackage` references the matching Catalog through DataManagerDataPackage.
Repeated scans reuse these identities; upgrades rebind the client deployment
to the new release. Deleting the application removes its provider and connections
while preserving the MariaDB server, catalogs, and backup history.

These are discovery references, not database connection credentials or runtime
connection settings. The implemented matching is limited to MariaDB catalogs on
the application's own machine; the declaration has no remote host or port field.

CMDB's own declaration is:

```python
CMDB_DATABASES = (("CMDB", "cmdb"),)
```

## Verify an app update

Confirm each catalog name matches the actual database, including case. Re-scan a
registered application on a host where that catalog exists and verify its database
connection appears. A declaration alone does not create a database.
