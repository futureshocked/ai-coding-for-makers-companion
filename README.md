# AI Coding for Makers and Solopreneurs: Companion Repository

This repository accompanies the book and video course **AI Coding for Makers and Solopreneurs** by Peter Dalmaris (Tech Explorations). It holds the finished code for every build in the book, the documents each build started from (brainstorms, specifications, architecture notes) and the prompts used along the way.

Book and course resources: <https://ai.techexplorations.com/resources/>

## What is in here

| Book chapter(s) | Folder | What you get |
|---|---|---|
| Ch 4 | [`prompts/ch04-spec-builder-interview.md`](prompts/ch04-spec-builder-interview.md) | The spec-builder interview prompt |
| Ch 6 | [`builds/ch06-rc-filter-analyser/`](builds/ch06-rc-filter-analyser/) | Finished RC low-pass filter analyser (single HTML file) and its specification prompt |
| Ch 7–16 | [`builds/ch16-serial-plotter/`](builds/ch16-serial-plotter/) | Finished Arduino serial data plotter (Flask, Chart.js), the agent spec, the architecture document, the Arduino sketches and the build prompts |
| Ch 18 | [`prompts/ch18-datasheet-system-prompt.md`](prompts/ch18-datasheet-system-prompt.md) | The system prompt from the API basics chapter |
| Ch 17–22 | [`builds/ch22-datasheet-qa/`](builds/ch22-datasheet-qa/) | Finished datasheet Q&A tool (RAG over PDF datasheets), its specification, the build prompts and links to the datasheets used |
| Ch 23–29 | [`builds/ch29-makerspace-booking/`](builds/ch29-makerspace-booking/) | Finished multi-tenant makerspace booking system, its brainstorm and specification, all 21 build prompts in order, and the production deployment runbook |

Chapters not listed (for example Chapters 1–3, 5 and the business chapter) teach concepts and have no code of their own.

Each build folder has its own `README.md` that tells you which chapter it belongs to, which files to read first and how to run it.

## Before you start

The setup guides cover what you need to install and configure:

1. [Install the tools](setup/01-install-tools.md): Python, Git, a code editor, an AI coding assistant, the Arduino IDE and Docker.
2. [API keys and secrets](setup/02-api-keys-and-secrets.md): getting an Anthropic API key, storing keys in a `.env` file and keeping them out of Git.
3. [Deploying to the internet](setup/03-deploying-to-the-internet.md): the accounts and services the booking system uses in production (a VPS, Cloudflare DNS, Resend email and GitHub Actions).

## About this code

This is the code as it stood at the end of each build, not a polished reference implementation. It was written with AI coding agents following the workflow in the book, and it carries the decisions, fixes and small inconsistencies that real builds accumulate. Where the code differs from a listing in the book, the book shows the version at that point in the chapter and this repository shows the final version.

Model names, library versions and prices change often. If a model named in a config file has been retired, replace it with a current one from your provider.

## Security

No API keys, passwords or private credentials are included. Every project reads its secrets from environment variables or a `.env` file, and every project's `.gitignore` excludes `.env`. Where a project needs one, a `.env.example` file lists the variables with placeholder values. When you copy a project into your own repository, keep it that way: never commit a `.env` file.

## Licence

The code in this repository is released under the [MIT licence](LICENSE). The written material (prompts, specifications, brainstorm notes and guides) is © Tech Explorations, provided for your personal learning; see [CONTENT-LICENSE.md](CONTENT-LICENSE.md).

## Corrections and questions

If you find a problem with the code, open an issue in this repository. For questions about the book or course, use the contact details at <https://ai.techexplorations.com>.
