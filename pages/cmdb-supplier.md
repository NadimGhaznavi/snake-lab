---
title: CMDB_SUPPLIER App Developer Guide
author_profile: true
layout: single
---

[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})

## Declare the software supplier

Use `CMDB_SUPPLIER` to identify the software supplier. Discovery stores the
value in `SoftwareSystem.supplier`. Declare it explicitly; application discovery
does not infer it from a repository URL or account name.

Example declaration alongside the required version:

```python
VERSION = "1.2.3"
CMDB_SUPPLIER = "Example Supplier"
```

Place the literal at module or class scope in the application's constants file.
Annotated assignments are also supported. Values are trimmed and must be
nonempty strings of at most 255 characters, without control characters.
Missing, computed, or invalid values are ignored and do not erase metadata
already stored for a matching release.

See [shared metadata rules]({{ site.baseurl }}{% link pages/app-discovery.md %}#shared-metadata-rules)
for constants-file placement, registration, and how discovery handles omitted or
conflicting metadata across releases and hosts.
