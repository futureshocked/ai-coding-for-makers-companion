# API keys and secrets

Two builds call paid services and need keys:

1. **Datasheet Q&A (Ch 22)** needs an Anthropic API key.
2. **Booking system (Ch 29)** needs a Resend API key to send email, and in production a Cloudflare API token (see [Deploying to the internet](03-deploying-to-the-internet.md)).

## Get an Anthropic API key

1. Create an account at <https://console.anthropic.com/>.
2. Add a payment method and a small amount of credit under **Billing**. Set a monthly spend limit while you are there; the datasheet tool costs very little per question, but a limit protects you from a runaway loop.
3. Open **API Keys**, create a key and copy it. The console shows it only once.

## Store keys in a `.env` file

Each project reads its keys from environment variables. The simplest way to set them is a file named `.env` in the project folder:

```
ANTHROPIC_API_KEY=your_key_here
```

The datasheet tool and the booking system load `.env` automatically. For the booking system, copy `.env.example` to `.env` and fill in the values; `.env.example` lists every variable the app reads.

## Keep keys out of Git

A key that reaches a commit stays in the repository's history even after you delete the file, and public repositories are scanned continuously by automated tools looking for exactly this. Three habits prevent it:

1. Make sure `.env` is listed in the project's `.gitignore` before you create the file. Every project in this repository already does this.
2. Before each commit, run `git status` and check that `.env` is not in the list of files to be committed.
3. If a key is ever committed, treat it as compromised: revoke it in the provider's console and create a new one. Deleting the file is not enough.

You can check a project's history for leaked secrets at any time:

```bash
git log -p | grep -iE "api_key|secret|password|token" 
```
