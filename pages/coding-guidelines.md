---
title: Coding Guidelines
author_profile: true
layout: single
---

[Architecture](/pages/architecture.html) · [Developer integration](/pages/developer.html)

SnakeLab should be easy to navigate, understand, and maintain. Each component
should have a clear responsibility, an obvious home, and a defined interface.
These guidelines describe the design goals for the ongoing refactor; some
existing modules still need to be brought into this structure.

## Organize code by responsibility

Group related components under `snake_lab/`:

| Package | Responsibility |
| --- | --- |
| `nn/` | Neural networks, training, epsilon policy, and replay memory |
| `game/` | Game state, rules, and episode environment |
| `server/` | Server orchestration, simulation runs, and configuration processing |
| `client/` | TUI components, plots, stylesheets, and client adapters |
| `zmq/` | ZeroMQ transport components |
| `database/` | Application database operations and generic MariaDB access |
| `utils/` | Shared utilities such as logging |

Give each major class its own module, named after the class:
`GameState.py`, `GameRules.py`, `SnakeGame.py`, `TelemetryPublisher.py`, and
`ConfigurationReader.py`. Small supporting types and private helpers may stay
with the component they serve.

Prefer explicit imports from the owning module, for example:

```python
from snake_lab.game.GameState import GameState
from snake_lab.database.SnakeDb import SnakeDb
```

Keep presentation code with the client. `SnakeBoard` renders snapshots in the
TUI; the server operates on game state and publishes telemetry. Keep client
assets, including `client.tcss`, alongside the client code.

Keep package initializers small as the refactor progresses. Code temporarily
held in `__init__.py` during a package conversion should be extracted into its
own modules in subsequent steps. Use `__main__.py` for package entry points so
existing commands such as `python -m snake_lab.server` continue to work.

## Separate application meaning from implementation mechanics

Application code should call an interface that expresses its intent. That
interface translates the request into operations on a lower-level helper.
Callers should not bypass the interface or reach into the helper's resources.

Keep generic helpers independent of SnakeLab rules and schema details. Keep
application decisions in the layer that understands SnakeLab. Use composition
to make that relationship explicit.

## Trust internal contracts

SnakeLab's internal modules are developed and maintained together. Use clear
interfaces, type annotations, and tests to establish their contracts. Do not
add runtime type checks, attribute-existence checks, repeated validation, or
fallback paths merely to defend against another internal module being used
incorrectly.

Validate external inputs at their entry points, such as configuration files,
incoming messages, and decoded database results. Once data has been validated
and converted into application objects, internal callers should use those
objects directly without rechecking the same contract at every layer.

Let internal programming errors surface clearly, even if they stop the
application. Fix the root cause and add a regression test. Do not hide bugs
with broad exception handlers, silent defaults, coercions, or speculative
recovery code intended to keep execution going.

Keep resource cleanup and transaction rollback reliable while allowing the
failure to propagate. Handle expected external failures at the responsible
boundary, preserving their cause. These responsibilities do not justify
defensive scaffolding around trusted internal calls.

## Use a shared data access layer

Both server persistence and client database lookups must use the same data
access layer (DAL):

```text
Server -------------------> SnakeDb ---> DbMgr ---> MariaDB
Client ConfigurationReader ----^
```

`SnakeDb` owns the application interface:

- Operations such as `create_run()`, `mark_started()`, `record_episode()`,
  `finish_run()`, and `get_configuration()`.
- SnakeLab table names, column mappings, and application queries.
- Conversion between application values and persisted representations.
- Decisions about which operations must succeed together in one transaction.

For example, `SnakeDb.mark_started(run_id)` translates the request into
`DbMgr.update()` with the appropriate table, values, and conditions.

`DbMgr` owns the database mechanics:

- MariaDB connection creation, credentials, timeouts, and connection cleanup.
- Cursor creation, use, and cleanup. Cursors never escape this layer.
- Generic `select()`, `insert()`, `update()`, and `delete()` operations.
- SQL construction, identifier validation and quoting, and bound values.
- Transaction execution: begin, commit, rollback, and read-only transactions.
- Consistent result handling and database errors that preserve their causes.

Let database errors leave the transaction block so `DbMgr` can roll back and
report them. Handle them outside the block; do not swallow an error and
continue issuing statements inside the same transaction. Rely on MariaDB's
row locks and constraints rather than adding duplicate consistency checks.

`DbMgr` must not know about runs, episodes, game rules, or SnakeLab tables.
`SnakeDb` must not create connections through the driver, handle cursors, or
implement a second SQL execution mechanism. Client adapters must not duplicate
connection or query code.

Keep application side effects explicit. Recovering interrupted runs is a
server startup operation; opening a client database connection must never
trigger it.

## Keep configuration validation behind one interface

Use `server/Configuration.py` as the public configuration interface:

```text
Server ---> Configuration ---> JSONValidator
       ---> Simulator (resolved configuration)
```

`Configuration` selects the SnakeLab schema, loads it, and applies the
application rules. These include relationships between epsilon values, snake
length and board dimensions, and replay capacity and training batch size. It
returns a complete configuration or raises `ConfigurationError`. The server
resolves external input before creating a run; `Simulator` takes a private
copy of that resolved configuration without validating it again.

`JSONValidator` is strictly an internal helper for `Configuration`. It handles
schema defaults, merging, and JSON Schema validation. It contains no SnakeLab
rules. Other application modules must not import or call it directly.

Resolving a configuration must not mutate the caller's data or share mutable
defaults between resolutions. Keep validation errors specific enough to
identify the field that failed.

## Refactor in reviewable steps

Make one coherent structural change at a time. Preserve behavior when moving
or renaming components, and treat behavior changes as separate work.

For each move, update imports, relevant test references, resource paths, and
deployment file lists and copying rules. A module that works in the source
checkout must also be included in the installed application.

Run the tests relevant to the change. For changes to layer boundaries, verify
contracts such as transaction atomicity, rollback, resource cleanup, error
translation, and client/server use of the shared interface. Check entry points
and asset loading when converting a module into a package.

Distinguish new failures from existing failures. Report verification limits
clearly, including when live database integration has not been tested.
