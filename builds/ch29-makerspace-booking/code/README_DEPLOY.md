# Deployment runbook — MakerBooking on Hetzner

This is the one-time setup. Subsequent deploys happen automatically on `git push` to `main`. Rollbacks happen via a GitHub Actions button.

**Target:** `https://makerbooking.com` (apex) and `https://*.makerbooking.com` (tenant subdomains + super-admin) on a single Hetzner CPX22 VPS, Ubuntu 26.04 LTS.

> **Before you start (companion repo note).** This is the runbook used to deploy the book's build. Replace these values with your own as you go:
>
> 1. **Domain:** `makerbooking.com` appears in this runbook, `caddy/Caddyfile`, `config.py`, `docker-compose.yml`, the scripts in `scripts/` and the workflows in `.github/workflows/`. Search the project for it and replace it with your domain.
> 2. **Server address:** `203.0.113.10` is a reserved documentation address. Use your VPS's IPv4 address.
> 3. **GitHub account:** `YOUR_GITHUB_USER` and `GHCR_OWNER` should be your GitHub username (lowercase for `GHCR_OWNER`).
> 4. **Workflows:** the files in `.github/workflows/` only run when this project is the root of its own repository. Copy the `code/` folder into a new repository before you follow section A.
>
> Never commit your `.env` file. Only `.env.example`, which holds placeholders, belongs in git.

---

## A. Push the repo to GitHub (5 min, local)

Create an empty GitHub repository (no README), then note its address:

- **HTTPS:** `https://github.com/YOUR_GITHUB_USER/makerspace_booking_system.git`
- **SSH:** `git@github.com:YOUR_GITHUB_USER/makerspace_booking_system.git`

```bash
# From the repo root on your dev machine
git status                       # confirm clean / commit anything pending
git log -p -- .env config.py | grep -iE 'key|secret|password|token' || echo "clean"
# If anything matches, scrub history with `git filter-repo` before pushing.

git remote add origin git@github.com:YOUR_GITHUB_USER/makerspace_booking_system.git
git push -u origin main
```

The repo's `.gitignore` already excludes `.env`, `data/`, and `*.sql.gz` so nothing sensitive should leave your machine.

### How GitHub knows which repo to deploy from

The linkage is implicit — once you push, everything finds itself by convention. Worth understanding once:

- `git remote add origin git@github.com:YOUR_GITHUB_USER/makerspace_booking_system.git` points your local repo at the GitHub remote. After this, `git push` and `git push origin main` both go there (verify with `git remote -v`).
- The workflow files in `.github/workflows/` are auto-discovered by GitHub Actions the moment they appear in the repo. **No "enable Actions" step is required** for new repos — it's on by default.
- Inside a workflow run, GitHub auto-populates `${{ github.repository }}`, `${{ github.repository_owner }}`, `${{ github.actor }}`, and `${{ secrets.GITHUB_TOKEN }}` based on the repo the workflow is running in. That's how the build step knows to push the image to `ghcr.io/YOUR_GITHUB_USER/makerspace_booking_system` without you ever typing your username in YAML.
- The **VPS** doesn't know your GitHub URL at all. It just pulls images from GHCR using the `GHCR_OWNER` value in `/opt/makerbooking/.env` plus the image name baked into `docker-compose.yml`. If you ever rename the repo or move it to a GitHub organization, update `GHCR_OWNER` on the server — nothing else changes.

---

## B. Bootstrap the Hetzner VPS (one command, run from your development machine)

Create the VPS, then note its IPv4 address. This runbook uses the documentation address **`203.0.113.10`** as a placeholder; replace it with yours. Set the shell variable once so every command below can be copy-pasted:

```bash
export VPS_IP=203.0.113.10
```

### Bootstrap the server

[scripts/bootstrap_vps.sh](scripts/bootstrap_vps.sh) is an idempotent script that does everything: creates the `deploy` user, installs Docker + UFW + fail2ban + unattended-upgrades, opens 22/80/443, hardens SSH, enables auto-updates, and creates `/opt/makerbooking/` with the right ownership. Safe to re-run.

```bash
scp scripts/bootstrap_vps.sh root@$VPS_IP:/tmp/
ssh root@$VPS_IP "bash /tmp/bootstrap_vps.sh && rm /tmp/bootstrap_vps.sh"
```

Verify you can SSH in as `deploy`:

```bash
ssh deploy@$VPS_IP "docker ps && id"
```

You should see an empty Docker container table (no containers yet — that's expected) and `deploy` listed in the `docker` group. UFW was configured by the bootstrap script as root and doesn't need a separate check here.

---

## C. DNS + Cloudflare (10 min)

The app uses wildcard TLS (`*.makerbooking.com`) obtained via Caddy's DNS-01 ACME challenge. DNS-01 requires a Cloudflare API token — Caddy creates a temporary TXT record in your zone to prove ownership. HTTP-01 cannot issue wildcard certs, so this step is mandatory.

1. In Cloudflare DNS for `makerbooking.com`, add **three A records** (all `203.0.113.10`, all **DNS only / grey cloud** for now):

   | Name | Points to | Notes |
   |------|-----------|-------|
   | `@` (apex) | `203.0.113.10` | Landing page and password reset |
   | `www` | `203.0.113.10` | Redirects to apex via Caddyfile |
   | `*` (wildcard) | `203.0.113.10` | All tenant subdomains + `app.` super-admin |

2. **SSL/TLS → Overview** → set encryption mode to **Full (strict)**.

3. Create a Cloudflare API token for Caddy:
   - Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → Profile → API Tokens → **Create Token**.
   - Use the **Edit zone DNS** template.
   - Scope it to `makerbooking.com` only.
   - Copy the token — you will paste it into the server `.env` in step E.

4. (Defer flipping the proxy to orange until step G is green.)

---

## D. Resend (10 min)

1. <https://resend.com> → API Keys → create key labeled `makerbooking-prod`. Copy and save it — you'll paste it into `/opt/makerbooking/.env` in step E.
2. Domains → Add Domain → `makerbooking.com`. Resend gives you a DKIM record + an SPF record — add both to Cloudflare DNS (grey cloud, DNS only).
3. Wait for verification (usually under a minute). Use `noreply@makerbooking.com` as the sender.

---

## E. Server `.env` (5 min)

On your development machine, generate the secrets first, then write the file:

```bash
# Generate secrets — copy these values, you'll paste them below
openssl rand -hex 32   # → SECRET_KEY
openssl rand -hex 24   # → POSTGRES_PASSWORD (use the same value for <DBPASS>)
```

Create `/tmp/makerbooking.env` (do NOT commit it). Replace every `<…>` placeholder with a real value before saving:

```
SECRET_KEY=<paste openssl rand -hex 32 output>
DATABASE_URL=postgresql://makerbooking:<DBPASS>@db:5432/makerbooking
POSTGRES_DB=makerbooking
POSTGRES_USER=makerbooking
POSTGRES_PASSWORD=<paste openssl rand -hex 24 output — same value as DBPASS above>
RESEND_API_KEY=<paste prod key from step D>
RESEND_FROM_EMAIL=noreply@makerbooking.com
REMINDER_INTERVAL_HOURS=1
REMINDER_HOURS_BEFORE=24
NAGER_DATE_COUNTRY=AU
GHCR_OWNER=your_github_user_lowercase
CLOUDFLARE_API_TOKEN=<paste token from step C.3>
```

> ⚠️ **Do not upload until every `<…>` placeholder is replaced.** The deploy script sources
> this file as a bash script. Values containing `<` or `>` are interpreted as shell
> redirections and will cause a cryptic `syntax error near unexpected token 'newline'`
> at deploy time.
>
> The `CLOUDFLARE_API_TOKEN` is consumed by the `caddy` Docker service to perform DNS-01
> ACME challenges for wildcard TLS. Without it Caddy cannot obtain a certificate for
> `*.makerbooking.com` and all HTTPS requests will fail.

Validate the file before uploading:

```bash
# Should print "syntax ok" — if it errors, check for un-replaced placeholders
bash -n <(sed 's/^/x=/' /tmp/makerbooking.env) && echo "syntax ok"
```

Upload it and lock down permissions:

```bash
scp /tmp/makerbooking.env deploy@$VPS_IP:/opt/makerbooking/.env
ssh deploy@$VPS_IP "chmod 600 /opt/makerbooking/.env"
shred -u /tmp/makerbooking.env   # delete from your development machine
```

---

## F. GitHub Actions secrets (10 min, never done this before? follow each step)

You need to give GitHub Actions three pieces of information so it can SSH into your VPS and run the deploy. We'll do it click-by-click.

### F.1 Generate a deploy-only SSH key on your development machine

A new key just for this deploy, so it can be rotated without touching the key you use yourself.

```bash
ssh-keygen -t ed25519 -N "" -C "makerbooking-gha" -f ~/.ssh/makerbooking_gha
ssh-copy-id -i ~/.ssh/makerbooking_gha.pub deploy@$VPS_IP
```

Verify the new key works:

```bash
ssh -i ~/.ssh/makerbooking_gha deploy@$VPS_IP "echo ok"
# should print: ok
```

### F.2 Open the secrets page in your browser

1. Go to `https://github.com/YOUR_GITHUB_USER/makerspace_booking_system`.
2. Click the **Settings** tab in the repo header (rightmost tab — NOT the gear icon next to your profile picture).
3. In the left sidebar, scroll down to the **Security** section.
4. Click **Secrets and variables** → **Actions**.

You should land on a page titled "Actions secrets and variables" with tabs **Secrets** and **Variables**. Stay on **Secrets**.

### F.3 Add each secret

The secrets page has two sections: **Environment secrets** (top) and **Repository secrets** (bottom). Use **Repository secrets** — environment secrets are scoped to a named deployment environment (e.g. "production"), which this project doesn't configure. Repository secrets are available to all workflow runs unconditionally. The green **New repository secret** button is in the lower section.

For each of the three rows below, click that green **New repository secret** button (top right of the "Repository secrets" section), fill in Name + Value, click **Add secret**. Names are case-sensitive; spaces aren't allowed.

| Name              | Value                                                      |
|-------------------|------------------------------------------------------------|
| `SSH_HOST`        | `203.0.113.10`                                           |
| `SSH_USER`        | `deploy`                                                   |
| `SSH_PRIVATE_KEY` | the entire contents of `~/.ssh/makerbooking_gha` — see note below |

**For `SSH_PRIVATE_KEY`:** the value MUST include the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines AND the trailing newline. Copy it to the clipboard exactly:

```bash
# Linux (print to terminal, then select-all and copy):
cat ~/.ssh/makerbooking_gha

# macOS:
pbcopy < ~/.ssh/makerbooking_gha
```

Then paste into the Value box and click **Add secret**. (If the workflow later fails with a vague "load key" / "permission denied" SSH error, the most common cause is a missing trailing newline — re-add the secret using `cat` again.)

GitHub hides the value after saving. You can update or delete a secret later, but you can never view it again.

### F.4 Confirm the secrets are saved

Back on the Secrets page you should now see three entries: `SSH_HOST`, `SSH_PRIVATE_KEY`, `SSH_USER`, each with an "Updated NOW" timestamp.

### F.5 Confirm Actions is enabled

In the same Settings sidebar, click **Actions** → **General**. Under "Actions permissions", the default for new repos is **Allow all actions and reusable workflows** — that's what you want. If it's been disabled, set it here and click Save.

### F.6 No GHCR token needed

The deploy workflow pushes the Docker image to GitHub Container Registry (`ghcr.io`) using the built-in `GITHUB_TOKEN` that GitHub provisions per workflow run. The `permissions: packages: write` block in `.github/workflows/deploy.yml` grants it write access to your repo's container registry. You do NOT need to create a Personal Access Token or any extra secret for this.

### F.7 Where to watch runs

Click the **Actions** tab at the top of the repo. Each push to `main` creates a workflow run. Click into one to see step-by-step logs. The "Compute image tag" step in `deploy` prints the short SHA used as the image tag — useful to note down if you ever need to roll back.

---

## G. First deploy (5 min)

The compose file, Caddyfile, and scripts ship into `/opt/makerbooking/` automatically on each deploy (via SCP from the GitHub Actions workflow). For the very first deploy, prime them by hand so the first SSH step has something to run against:

```bash
scp docker-compose.yml caddy/Caddyfile deploy@$VPS_IP:/opt/makerbooking/   # caddy goes to caddy/Caddyfile
ssh deploy@$VPS_IP "mkdir -p /opt/makerbooking/caddy && mv /opt/makerbooking/Caddyfile /opt/makerbooking/caddy/Caddyfile"
scp scripts/deploy.sh scripts/backup.sh deploy@$VPS_IP:/opt/makerbooking/scripts/
ssh deploy@$VPS_IP "chmod +x /opt/makerbooking/scripts/*.sh"
```

Then trigger the first deploy:

```bash
git commit --allow-empty -m "first deploy"
git push origin main
```

Watch <https://github.com/YOUR_GITHUB_USER/makerspace_booking_system/actions>. The workflow will:
1. Run pytest.
2. Build the Docker image with `APP_VERSION=<shortsha>+<date>`.
3. Push to `ghcr.io`.
4. SSH into the VPS and run `./scripts/deploy.sh <shortsha>`, which pulls the image, runs migrations, and brings the containers up.

When it goes green, Caddy will request a Let's Encrypt wildcard cert in the background via DNS-01 (takes ~30–60 s). Watch the logs:

```bash
ssh deploy@$VPS_IP "cd /opt/makerbooking && docker compose logs --tail=50 caddy"
```

Once you see `certificate obtained successfully` for `*.makerbooking.com`, your origin is serving HTTPS for all subdomains. **Do NOT flip Cloudflare to orange-cloud yet** — finish section H first.

### Seed the database with test data

```bash
ssh deploy@$VPS_IP "cd /opt/makerbooking && docker compose exec app flask seed-db"
```

This creates two demo tenant organisations (`acme` and `widgetco`) with sample users and resources, so you can poke at the live app immediately.

> ⚠️ **Security warning — read this before continuing**
>
> The seed data includes hardcoded weak passwords for test accounts:
>
> - `admin@acme.example.com` / `adminpass` (acme tenant admin)
> - `alice@acme.example.com` / `memberpass`
> - `bob@acme.example.com` / `memberpass`
> - Same pattern for widgetco tenant
>
> The site is currently only reachable via the raw VPS IP (Cloudflare is still grey-cloud). Treat this as a private test stage. **Section H removes these accounts and creates your real admin BEFORE you flip Cloudflare to orange-cloud (i.e. before the site is publicly findable).** Do not skip section H, and do not enable the orange proxy until step H.5.

---

## H. Pre-launch sequence (do every step, in order)

This sequence takes you from "test data on a server only you know the IP of" to "publicly announced production". Step 4 is non-negotiable — do not skip to step 5.

### H.1 Verify the app works with seed data

Add the following to your local `/etc/hosts` to reach the live server via its domain names (remove after testing):

```
203.0.113.10  acme.makerbooking.com widgetco.makerbooking.com app.makerbooking.com
```

Visit `https://acme.makerbooking.com` and log in as `admin@acme.example.com` / `adminpass`.

- The footer should show `v<shortsha>+<date>` (admin-only).
- Create a resource, make a booking, log in as `alice@acme.example.com` to check the member view.
- Visit `https://widgetco.makerbooking.com` to confirm the two tenants are isolated (alice's acme bookings are not visible).

### H.2 Create your real admin account and platform super-admin

You need two accounts: a tenant admin for your real organisation, and the platform super-admin.

**Create the platform super-admin first:**

```bash
ssh deploy@$VPS_IP
cd /opt/makerbooking
docker compose exec app flask create-super-admin
# Enter email (yours), display name, password (twice).
```

Verify: visit `https://app.makerbooking.com/super/login` and log in with those credentials. You should see the super-admin dashboard listing the two seed tenants.

**Create your real tenant and its admin:**

If you want to run your own makerspace organisation, either:

- Use the org self-signup form at `https://makerbooking.com/register/org` and then approve yourself in the super-admin dashboard, or
- Create a tenant directly in the Flask shell and then run `flask create-admin --tenant-subdomain <your-subdomain>`.

### H.3 Verify your real admin works

Log out of the seed admin, log in as the account you just created, confirm you have admin access (you should see admin nav items).

### H.4 Delete the seed test users

```bash
docker compose exec app flask delete-seed-users
```

This removes all seed test accounts across both `acme` and `widgetco` tenants. Idempotent — only touches the seeded emails, not any accounts you've created.

Verify they're gone by trying to log in as `admin@acme.example.com` (should fail).

### H.5 Flip Cloudflare to orange-cloud (proxied)

In Cloudflare DNS, edit **all three A records** (`@`, `www`, `*`) and toggle each proxy status to **proxied (orange cloud)**. After ~30 seconds all subdomains and the apex domain will be served via Cloudflare's edge.

### H.6 Final smoke test

- Visit `https://makerbooking.com` — landing page loads with no cert warning.
- Visit `https://<your-org>.makerbooking.com` — tenant login page loads.
- Log in as your real admin — footer shows `v<shortsha>+<date>`.
- Visit `https://app.makerbooking.com/super/login` — super-admin dashboard loads.
- Trigger a booking with a reminder window and verify the email lands (check Resend dashboard).

---

## I. Enable nightly backups

```bash
ssh deploy@$VPS_IP
crontab -e
```

Add:

```
0 3 * * * /opt/makerbooking/scripts/backup.sh >> /opt/makerbooking/data/backups/backup.log 2>&1
```

That runs `pg_dump` daily at 03:00 UTC. Dumps go to `/opt/makerbooking/data/backups/`, gzipped, with 7-day retention. Test once by hand:

```bash
/opt/makerbooking/scripts/backup.sh && ls -lh /opt/makerbooking/data/backups/
```

---

## Subsequent deploys

```bash
git commit -m "your change"
git push origin main
```

That's it. Watch Actions for green/red.

---

## How to roll back

If a deploy breaks something:

1. Open <https://github.com/YOUR_GITHUB_USER/makerspace_booking_system/actions/workflows/rollback.yml>.
2. Click **Run workflow** (top right).
3. In `image_tag`, paste the **12-char short SHA** of the previous good commit. You can find it:
   - In the GitHub Actions history (each successful Deploy run names its tag in the build step), or
   - Locally: `git log --oneline -5` (use the first 12 chars).
4. Click **Run workflow**.

The same `deploy.sh` runs with the old tag. Migrations re-run (must be backwards-compatible — see note below). Health check confirms it came up.

**About migration rollbacks:** rolling back the *code* is a one-click operation; rolling back the *database schema* is not. Always write backwards-compatible migrations (add columns nullable; deploy code that ignores them; backfill; then a later release makes them required). If a deploy required a destructive schema change and you need to roll back, restore the most recent `pg_dump` from `/opt/makerbooking/data/backups/` first.

---

## Common operations

### Your IP is banned by fail2ban

fail2ban watches SSH login attempts and bans IPs that fail too many times. This can catch you if you mistype a password, use the wrong key, or simply if the VPS has been offline and your SSH client retried aggressively.

**Symptoms:** `ssh: connect to host … port 22: Connection refused` even though the server is up and `sshd` is running.

**Fix — use the Hetzner web console to unban your IP:**

1. Go to [console.hetzner.cloud](https://console.hetzner.cloud), open your server, and click **Console**.
2. Log in as `root`.
3. Check whether fail2ban is the cause and find your IP:
   ```bash
   fail2ban-client status sshd
   ```
   Look for your IP in the "Banned IP list".
4. Unban it:
   ```bash
   fail2ban-client unban <YOUR_IP>
   ```
5. Confirm by trying SSH from your machine again.

**To find your current public IP** (run locally):
```bash
curl -s ifconfig.me
```

**Prevention:** add your home/office IP as a permanent allow rule in UFW so fail2ban can never touch it:
```bash
# Run on the server as root
ufw insert 1 allow from <YOUR_IP> to any port 22
```
Re-run this whenever your ISP assigns you a new IP.

---

```bash
# tail logs
ssh deploy@$VPS_IP "cd /opt/makerbooking && docker compose logs -f app"
ssh deploy@$VPS_IP "cd /opt/makerbooking && docker compose logs -f scheduler"

# Flask shell
ssh deploy@$VPS_IP "cd /opt/makerbooking && docker compose exec app flask shell"

# Restore from backup
ssh deploy@$VPS_IP
cd /opt/makerbooking
ls data/backups/                                   # pick a file
docker compose exec -T db psql -U makerbooking -d makerbooking \
  < <(gunzip -c data/backups/makerbooking-YYYYMMDD…sql.gz)

# Rotate Resend / SECRET_KEY: edit /opt/makerbooking/.env then
docker compose up -d app scheduler
```

---

## Out of scope for v2 (revisit later)

- Offsite backups (Hetzner Storage Box / Backblaze B2).
- Staging environment.
- Uptime monitoring (Uptime Kuma, healthchecks.io ping from `backup.sh`).
- Centralized log aggregation.
- Tenant-level billing / subscription management.
- Per-tenant custom email domains.
