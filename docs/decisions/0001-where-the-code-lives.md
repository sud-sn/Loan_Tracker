# 0001 · Where the code lives

**Status:** accepted (owner's instruction, 4 Nov 2026)

The PRD asks for a monorepo. The owner asked for a new repository `sud-sn/loan-tracker`; it did not
exist and this session cannot create repositories, so, as the owner instructed, the project was built
on branch `claude/new-product-requirements-xihztp` of `sud-sn/ADF` with the ADF files removed from
that branch only (ADF is untouched on `master`).

**Later:** create `sud-sn/loan-tracker`, then `git push <new-remote> claude/new-product-requirements-xihztp:main`.
Nothing in the code depends on the repository name.
