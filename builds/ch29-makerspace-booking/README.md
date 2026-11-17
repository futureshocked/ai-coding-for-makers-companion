# Chapters 23–29: makerspace resource booking system

A web application that lets makerspace members book shared equipment (laser cutters, 3D printers, workshop bays) with conflict detection, opening hours, public holidays, email reminders and an admin console. Version 2 adds multi-tenancy: several independent organisations each get their own subdomain, members, resources and bookings, with a platform super-admin above them.

Part IV of the book (Chapters 23–28) covers multi-user design, databases and ORMs, multi-file projects with an agent, external APIs and scheduled jobs, finishing and shipping, and designing for multiple organisations. Chapter 29 is the complete build.

## Read these first

| File | What it is |
|---|---|
| [`code/docs/brainstorm.md`](code/docs/brainstorm.md) | The brainstorm that settled the scope |
| [`code/docs/spec.md`](code/docs/spec.md) | The specification the agent built from, including the acceptance criteria |
| [`code/docs/build_prompts/`](code/docs/build_prompts/) | All 21 prompts from the build, numbered in the order they were used (see below) |
| [`code/docs/REFACTORING.md`](code/docs/REFACTORING.md) | The plan for the version 2 multi-tenancy refactor |
| [`code/README.md`](code/README.md) | Developer guide: local setup, configuration, tests |
| [`code/README_DEPLOY.md`](code/README_DEPLOY.md) | Production deployment runbook |

## The build prompts

| Files | Stage |
|---|---|
| `01`–`04` | Answers to the assistant's brainstorm questions, over four rounds |
| `05`–`11` | Core build: authentication, resource management, seed data, availability, booking with conflict detection |
| `12`–`15` | Iteration: interface refresh, avatars and profiles, editing bookings, admin pages |
| `16` | Extra features: public holidays from the Nager.Date API, reminder emails, password reset |
| `17`–`19` | Getting ready to ship: deployment plan, documentation, versioning |
| `20`–`21` | Version 2: multi-tenancy and the fixes that followed |

Several prompts begin "Read memory.md for current project state." That file was the agent's running project memory (Chapter 25). It changed after every session, so it isn't included; the prompts that ask the agent to update it (`08` and `11`) show what it recorded.

## Run it locally

You need Python 3.10 or newer, Git, PostgreSQL (Docker is the easiest way to run it) and a free Resend account for email ([install guide](../../setup/01-install-tools.md), [API keys](../../setup/02-api-keys-and-secrets.md)).

Follow the Quick Start in [`code/README.md`](code/README.md), working inside the `code/` folder. It covers copying `.env.example` to `.env` and filling it in, installing the dependencies, creating the database, applying the migrations and seeding test data.

When it is running, open <http://lvh.me:5000>. `lvh.me` is a public name that always points to your own computer, which lets each organisation's subdomain work without extra setup. The developer guide lists the test organisations and accounts the seed command creates.

## Deploy it

Read [Deploying to the internet](../../setup/03-deploying-to-the-internet.md) for the accounts you need (a VPS, Cloudflare, Resend and GitHub), then follow [`code/README_DEPLOY.md`](code/README_DEPLOY.md). The note at the top of the runbook lists the values to replace with your own, including the domain.
