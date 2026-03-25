# Contributing to NGO Databank

This monorepo contains **Backoffice** (Flask), **Website** (Next.js), and **MobileApp** (Flutter). Day-to-day developer setup and conventions are summarized in [`CLAUDE.md`](CLAUDE.md) and the per-app READMEs.

## Git and GitHub CLI

- **`git`** — clone, branch, commit, merge, push.
- **`gh`** ([GitHub CLI](https://cli.github.com/)) — issues, PRs, releases, and **some** repository settings (`gh repo edit`, `gh pr create`, …).

Branch protection and rulesets are **not** configured with plain `git`. They are enforced on GitHub via **branch protection rules**, **rulesets**, or the **`gh api`** REST calls below.

## Collaboration workflow

1. **Branch from `main`** using a short, descriptive name (e.g. `fix/backoffice-csrf`, `feature/website-maps`).
2. **Keep commits focused**; prefer rebase or merge from `main` before opening a PR if the branch is long-lived.
3. **Open a pull request** into `main` with a clear title and what/why in the description. Link issues with `Fixes #123` when applicable.
4. **Review** — address feedback and resolve review threads before merge.
5. **Merge** — squash, merge, or rebase according to team preference (all three are left enabled on the repo).

### Areas of the tree (for reviewers)

| Path | Typical reviewer focus |
|------|-------------------------|
| `Backoffice/` | Python, Flask, SQL migrations, admin routes, security |
| `Website/` | Next.js, public API usage, a11y, performance |
| `MobileApp/` | Flutter, platform builds, store policies |

## Repository settings applied via GitHub CLI

These use **`gh repo edit`** (they work on typical free private repos):

```bash
gh repo edit OWNER/ngodatabank --delete-branch-on-merge --allow-update-branch
```

Replace `OWNER` with your GitHub user or organization. Optional flags you can toggle:

```bash
# Examples — use =false to turn off
gh repo edit OWNER/ngodatabank --enable-auto-merge
gh repo edit OWNER/ngodatabank --enable-issues
gh repo edit OWNER/ngodatabank --enable-discussions
```

## Branch protection

### If you are on GitHub Free with a private personal repository

The **REST API** for branch protection and rulesets may return **403** (“Upgrade to GitHub Pro or make this repository public”). You can still configure protection in the browser:

**Settings → Branches → Add branch protection rule** (for `main`), then enable as appropriate:

- Require a pull request before merging  
- Require approvals (e.g. **1** for teams; **0** if only the maintainer merges their own PRs)  
- Dismiss stale pull request approvals when new commits are pushed  
- Require conversation resolution before merging  
- Do not allow bypassing the above settings (optional; admins can still override in emergencies if allowed)  
- Do not allow force pushes  
- Do not allow deletions  

Add **required status checks** only after workflows run on every PR (see *CI note* below).

### If the repo is public or you use GitHub Pro / Enterprise

You can create a **ruleset** with **`gh api`** (save the JSON to a file, then):

```bash
gh api repos/OWNER/ngodatabank/rulesets --method POST --input ruleset-protect-main.json
```

Example `ruleset-protect-main.json`:

```json
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"]
    }
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["merge", "squash", "rebase"],
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 1,
        "required_review_thread_resolution": true
      }
    },
    { "type": "non_fast_forward" },
    { "type": "deletion" }
  ]
}
```

Adjust `required_approving_review_count` (e.g. `0` for solo maintainers). Inspect rulesets with:

```bash
gh ruleset list --repo OWNER/ngodatabank
gh ruleset check main --repo OWNER/ngodatabank
```

Legacy **branch protection** (alternative to rulesets) via API:

```bash
gh api repos/OWNER/ngodatabank/branches/main/protection -X PUT --input branch-protection.json
```

Use GitHub’s docs for the current `branch-protection.json` shape: [Update branch protection](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection).

## CI note (required checks)

GitHub Actions only loads workflows from **`.github/workflows/` at the repository root**. Workflows under `Backoffice/.github/workflows/` are **not** picked up unless you symlink, copy, or otherwise expose them at the root. Before requiring a check on `main`, ensure a workflow runs on pull requests and note the **exact check name** as shown in the PR “Checks” tab.

## Security and secrets

Never commit `.env`, database dumps, or Firebase admin JSON. See the root `.gitignore` and [`CLAUDE.md`](CLAUDE.md) for environment and migration practices.

## Questions

Open a **GitHub Issue** or discuss with the maintainers for access, branching policy, or release process.
