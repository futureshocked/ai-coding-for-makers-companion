# Deploying to the internet

Only the booking system (Ch 29) is deployed to a public server. The other builds run on your own computer.

The full step-by-step runbook is in [`builds/ch29-makerspace-booking/code/README_DEPLOY.md`](../builds/ch29-makerspace-booking/code/README_DEPLOY.md). This page lists the accounts you need before you start, so you can set them up in advance.

## Accounts and services

| Service | What it does in the deployment | Cost |
|---|---|---|
| A domain name | The address people visit; each organisation gets its own subdomain | About the price of a coffee per month, billed yearly |
| [Cloudflare](https://www.cloudflare.com/) | Hosts the domain's DNS records, and issues the API token Caddy uses to obtain a wildcard TLS certificate | Free plan is enough |
| [Hetzner Cloud](https://www.hetzner.com/cloud) (or any VPS provider) | The virtual private server that runs the app, database, scheduler and web proxy | A few euros per month for the smallest suitable server |
| [Resend](https://resend.com/) | Sends password-reset and booking-reminder emails | Free tier is enough for a small makerspace |
| [GitHub](https://github.com/) | Hosts your copy of the code, runs the tests, builds the Docker images and deploys on every push to `main` | Free |

## Setting up Cloudflare

1. Create a Cloudflare account and **add your domain** (Cloudflare calls it a site or zone). Choose the free plan.
2. At your domain registrar, replace the domain's nameservers with the two Cloudflare gives you. This can take a few hours to take effect.
3. Once the domain shows as **Active** in Cloudflare, follow section C of the runbook. It adds the DNS records that point your domain at the VPS and creates an API token with **Zone → DNS → Edit** permission for that one domain.
4. Put the token in the server's `.env` file as `CLOUDFLARE_API_TOKEN`. It never goes into Git.

## Before your first deploy

1. Copy `builds/ch29-makerspace-booking/code/` into a new, empty repository of your own, so the GitHub Actions workflows in `.github/workflows/` sit at the repository root where GitHub can run them.
2. Replace `makerbooking.com` with your domain everywhere it appears. The note at the top of the runbook lists the files.
3. Store the server's address, user and SSH key as GitHub Actions secrets (runbook section F), never in a file in the repository.
