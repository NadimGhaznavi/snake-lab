---
title: Snake Lab Server
author_profile: true
layout: single
---

![Snake Lab](/pages/images/snake-lab.png)

The **Snake Lab Server** is built around Patrick Loeber's [Train an AI to Play Snake Tutorial](https://www.youtube.com/watch?v=L8ypSXwyBds). The [reinforcement learning](https://en.wikipedia.org/wiki/Reinforcement_learning) tutorial demonstrates how to build a simple AI that learns to play Snake by training over hundreds or thousands of games.

At the heart of the AI is its [neural network](https://www.youtube.com/playlist?list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi) and training configuration. Changes to parameters such as model size, learning rate, discount factor, and reward values can have a significant effect on the performance the AI ultimately achieves.

The Snake Lab Server accepts a simulation configuration message over the network. The message describes the neural network and training configuration, along with instructions for running the simulation. Snake Lab validates the request, executes the simulation, and stores the results in a database where clients can retrieve the data.

This project was created to support the [Ax3l Project](https://ax3l.osoyalce.com), which uses a *Large Language Model* (LLM) with the Snake Lab Server to optimize the configuration and maximize the high score.

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
- [Tech Stack and Credits](/pages/tech-stack)
- [Snake Lab Server GitHub Repo](https://github.com/NadimGhaznavi/snake-lab)

