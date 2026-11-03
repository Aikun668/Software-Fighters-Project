# Security notice

Git history was rewritten on `main`, `for-work`, `archive/stash-20260603-main-wip`, and `archive/stash-20260609-agent-dev` to remove the tracked path `ai-service/.env`.

That file must stay untracked. It is ignored by `ai-service/.gitignore` on current branches and by a root `.gitignore` rule for `.env`. Do not force-add a real env file.

If you cloned or fetched this repository before the rewrite, the old history is still in your local clone. Discard it:

```bash
git fetch origin
git checkout for-work
git reset --hard origin/for-work
```

Do the same hard reset for any other local branch you had (`main` and the `archive/*` branches), or clone the repository again. Old local stashes, backups, and tags created before the rewrite can still contain the removed file.
