---
title: CMDB_COMPONENTS App Developer Guide
author_profile: true
layout: single
---

[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})

## Declare filesystem components

The constants file may also declare persistent filesystem data components:

```python
CMDB_COMPONENTS = (
    ("Marketing Screenshots", "pages/marketing"),
    ("Uploads", "/srv/mycount/uploads"),
)
```

`CMDB_COMPONENTS` is an optional literal tuple or list of `(name, path)` pairs
at module or class scope; annotated assignments are supported. Each valid pair
creates a named Component owned by the discovered SoftwareSystem release and a
DeployedComponent whose namespace and `machine` identify the host. Relative
paths resolve from the installation directory: `pages/marketing` for MyCount
becomes `/opt/prod/mycount/pages/marketing`. Absolute paths stay absolute. Redundant slashes and `.` segments are normalized.
Discovery records declarations without checking whether their paths exist.

Names and paths are trimmed, nonempty strings without control characters;
names are limited to 255 characters and paths to 4096. Parent traversal (`..`)
and the relative path `.` are ignored. Computed declarations and malformed
entries are ignored; duplicate pairs are recorded once. `VERSION` is still
required. Components with the same name share a definition within a release;
deployments are identified by host, application name, component name, and path.
Repeated scans reuse records, and version changes relink observed deployments
while preserving their IDs and other hosts' release references. Changed paths
create additional deployments. Omitted, removed, or invalid declarations retain
previously recorded deployments. The application and its filesystem components
are written in the same transaction. Declared directory deployments are eligible
for scheduled or manual tarball backups in the Backups page's Application panel;
see [backups](https://cmdb.osoyalce.com/pages/backups.html#execution).

## Verify an app update

Check that relative paths resolve beneath the production installation directory,
absolute paths identify the intended data, and each declared directory is suitable
for application backups. Re-scan a registered application and confirm its named
components and deployment paths. Discovery does not check filesystem existence.
