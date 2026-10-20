---
title: CMDB_CODENAME App Developer Guide
author_profile: true
layout: single
---

[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})

## Declare the release codename

Use `CMDB_CODENAME` for the application release's codename. Discovery stores
it as a `TaggedValue` on the SoftwareSystem with tag `VERSION_CODENAME`.
The tag references the SoftwareSystem through its inherited ModelElement identity;
there is no separate SoftwareSystem codename attribute. Keep `VERSION` as the
release version even when a codename is supplied.

Example declaration alongside the required version:

```python
VERSION = "1.2.3"
CMDB_CODENAME = "Orion"
```

Place the literal at module or class scope in the application's constants file.
Annotated assignments are also supported. Values are trimmed and must be
nonempty strings of at most 255 characters, without control characters.
Missing, computed, or invalid values are ignored and do not erase metadata
already stored for a matching release.

See [shared metadata rules]({{ site.baseurl }}{% link pages/app-discovery.md %}#shared-metadata-rules)
for constants-file placement, registration, and how discovery handles omitted or
conflicting metadata across releases and hosts.
