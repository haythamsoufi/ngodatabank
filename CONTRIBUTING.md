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

## Repository automation (already enabled)

This **public** repository uses:

- **Branch ruleset** “Protect main” — pull requests required to update `main`, merge methods allowed, stale review dismissal, **resolved review threads required before merge**, no force-push, no branch deletion, and a **required status check** named **`Analyze (CodeQL)`** (see [`.github/ruleset-protect-main.json`](.github/ruleset-protect-main.json); `do_not_enforce_on_create` on that rule avoids blocking brand-new branches).
- **Secret scanning** and **secret scanning push protection** (`gh repo edit`).
- **Dependabot** — [`.github/dependabot.yml`](.github/dependabot.yml) (pip/npm/pub + GitHub Actions).
- **Code scanning** — [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) for `javascript-typescript` and `python` over `Backoffice/` and `Website/` (see [`.github/codeql/codeql-config.yml`](.github/codeql/codeql-config.yml)).
- **Dependency Review** on pull requests — [`.github/workflows/dependency-review.yml`](.github/workflows/dependency-review.yml).

Security reporting: [`SECURITY.md`](SECURITY.md). Conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

### Tweaking settings with `gh repo edit`

```bash
gh repo edit OWNER/ngodatabank --delete-branch-on-merge --allow-update-branch
gh repo edit OWNER/ngodatabank --enable-auto-merge
# Optional: --enable-discussions, --enable-wiki=false, etc.
```

### Ruleset: inspect, re-apply, or update

```bash
gh ruleset list --repo OWNER/ngodatabank
gh ruleset check main --repo OWNER/ngodatabank
# After editing .github/ruleset-protect-main.json (includes ruleset id in GitHub UI URL):
gh api repos/OWNER/ngodatabank/rulesets/RULESET_ID -X PUT --input .github/ruleset-protect-main.json
```

To **create** the ruleset from scratch (new repo or renamed default branch):

```bash
gh api repos/OWNER/ngodatabank/rulesets --method POST --input .github/ruleset-protect-main.json
```

**Private personal repos (GitHub Free):** the ruleset / branch-protection **REST APIs** may return **403** until the repo is **public** or you use **GitHub Pro**; you can still mirror these options under **Settings → Rules → Rulesets** or **Settings → Branches**.

### Tightening review requirements

`required_approving_review_count` is **0** so a solo maintainer is not blocked (GitHub does not allow self-approval on the same account). When a second maintainer joins, raise it to **1** in the ruleset and optionally add **CODEOWNERS** + `require_code_owner_review`.

## CI note (root workflows)

GitHub Actions only loads workflows from **`.github/workflows/` at the repository root**. Workflows under `Backoffice/.github/workflows/` are **not** executed unless mirrored or moved to the root. After the first **CodeQL** run on a PR, confirm the check name in the PR **Checks** tab if you add more required workflows to the ruleset.

## Security and secrets

Never commit `.env`, database dumps, or Firebase admin JSON. See the root `.gitignore` and [`CLAUDE.md`](CLAUDE.md) for environment and migration practices.

## Questions

Open a **GitHub Issue** or discuss with the maintainers for access, branching policy, or release process.
