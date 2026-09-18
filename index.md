---
title: Snake Lab Server
author_profile: true
layout: single
---

![Snake Lab](/pages/images/snake-lab.png)

The Snake Lab Server operates as a Linux systemd service. It allows users to submit a simulation run configuration. The simulations are of an **AI Snake Game** run. The server houses the entire Snake Game and neural network machinary. Once it receives a valid config it starts a fixed number of simulation episodes. Simulation and simulation run data is stored in MariaDb.

This project was created to support the [Fr3d Project](https://fr3d.osoyalce.com/) which has evolved into the [Ax3l Project](https://ax3l.osoyalce.com).

## User Docs

- [Installation](/pages/install)
- [Run a simulation](/pages/run-a-simulation)
- [Sample configuration](/pages/sample-config)

## Technical Docs

- [Architecture](/pages/architecture)
- [Developer integration](/pages/developer)
- [Control protocol](/pages/control-protocol)
- [Event protocol](/pages/event-protocol)
- [Coding guidelines](/pages/coding-guidelines)

