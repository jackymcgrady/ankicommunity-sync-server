# Git Submodule Setup Guide

This guide explains how to integrate the `ankipi-meta` documentation hub as a git submodule in each of the three AnkiPi projects.

## What is a Git Submodule?

A git submodule allows you to keep a git repository as a subdirectory of another git repository. This lets you:
- Access documentation locally while working on a project
- Keep documentation in sync across projects
- Version documentation alongside code

## Initial Setup

### For Each Project (ankipi, ankipiweb, ankicommunity-sync-server)

#### 1. Add the Submodule

Navigate to your project repository and run:

```bash
cd /path/to/your/project
git submodule add https://github.com/jackymcgrady/ankipi-meta.git ankipi-meta
```

This will:
- Clone the `ankipi-meta` repository into an `ankipi-meta/` subdirectory
- Create/update `.gitmodules` file to track the submodule
- Stage the changes for commit

#### 2. Commit the Submodule

```bash
git add .gitmodules ankipi-meta
git commit -m "Add ankipi-meta documentation hub as submodule"
git push
```

#### 3. Update Project's CLAUDE.md

Add these instructions to your project's `CLAUDE.md`:

```markdown
## Documentation Hub

This project includes the ankipi-meta documentation hub as a submodule.

### Accessing Documentation
- All cross-project documentation is in `./ankipi-meta/docs/`
- Start with `./ankipi-meta/docs/architecture/overview.md` for system understanding
- Check `./ankipi-meta/docs/cross-project/` for integration details

### Updating Documentation
When you make changes that affect architecture, APIs, or cross-project behavior:

1. Update relevant docs in `./ankipi-meta/docs/`
2. Commit and push from within the submodule:
   ```bash
   cd ankipi-meta
   git add docs/
   git commit -m "docs: [your changes]"
   git push
   cd ..
   ```
3. Update the parent repo to reference the new commit:
   ```bash
   git add ankipi-meta
   git commit -m "Update documentation reference"
   git push
   ```

### Pulling Latest Documentation
```bash
git submodule update --remote ankipi-meta
```
```

#### 4. Update Project's .gitignore (if needed)

Ensure your `.gitignore` doesn't ignore the submodule:

```bash
# Make sure these lines are NOT in .gitignore:
# ankipi-meta/
```

## Working with the Submodule

### Cloning a Project with Submodules

When cloning a project that has the submodule:

```bash
# Option 1: Clone with submodules in one command
git clone --recurse-submodules https://github.com/jackymcgrady/ankipi.git

# Option 2: Clone then initialize submodules
git clone https://github.com/jackymcgrady/ankipi.git
cd ankipi
git submodule init
git submodule update
```

### Updating to Latest Documentation

```bash
# Pull latest documentation changes
git submodule update --remote ankipi-meta

# Commit the reference update if you want to lock this version
git add ankipi-meta
git commit -m "Update documentation to latest"
git push
```

### Making Documentation Changes

#### From Your Project Repository:

```bash
# 1. Navigate into the submodule
cd ankipi-meta

# 2. Make sure you're on the main branch
git checkout main
git pull origin main

# 3. Make your documentation changes
# Edit files in docs/...

# 4. Commit and push from within the submodule
git add docs/
git commit -m "docs: [describe your changes]"
git push origin main

# 5. Go back to parent project
cd ..

# 6. Update parent project's reference to the submodule
git add ankipi-meta
git commit -m "Update documentation reference"
git push
```

#### Directly in the ankipi-meta Repository:

```bash
# If you're working directly in the ankipi-meta repo
cd /path/to/ankipi-meta
git checkout main
git pull origin main

# Make changes...

git add docs/
git commit -m "docs: [describe your changes]"
git push origin main

# Then update all projects that use it as a submodule:
cd /path/to/your-project
git submodule update --remote ankipi-meta
git add ankipi-meta
git commit -m "Update documentation reference"
git push
```

### Checking Submodule Status

```bash
# See current submodule commit
git submodule status

# See if submodule has uncommitted changes
cd ankipi-meta
git status
cd ..
```

## Common Workflows

### Workflow 1: AI Agent Implementing a Feature

```bash
# 1. Agent starts work, reads documentation
cd /path/to/ankipi-project
cat ankipi-meta/docs/architecture/overview.md
cat ankipi-meta/docs/api-contracts/ankipi-api.md

# 2. Implement the feature
# ... code changes ...

# 3. Update documentation if API or architecture changed
cd ankipi-meta
git checkout main
# Edit relevant docs
git add docs/
git commit -m "docs: update API contract for new endpoint"
git push origin main
cd ..

# 4. Commit feature implementation
git add .
git commit -m "feat: implement new feature"
git add ankipi-meta
git commit -m "Update documentation reference"
git push
```

### Workflow 2: Synchronizing Documentation Across Projects

```bash
# Project A made documentation updates, now update Project B

cd /path/to/project-b
git submodule update --remote ankipi-meta
git add ankipi-meta
git commit -m "Sync documentation updates from project A"
git push
```

### Workflow 3: Agent Fixing a Bug

```bash
# 1. Check troubleshooting docs
cd /path/to/project
cat ankipi-meta/docs/troubleshooting/common-errors.md

# 2. Fix the bug
# ... code changes ...

# 3. Document the solution
cd ankipi-meta
git checkout main
# Add entry to troubleshooting docs
git add docs/troubleshooting/
git commit -m "docs: add solution for [bug description]"
git push origin main
cd ..

# 4. Commit fix
git add .
git commit -m "fix: [bug description]"
git add ankipi-meta
git commit -m "Update documentation reference"
git push
```

## Troubleshooting

### Submodule shows modified but no changes

This usually means the submodule is on a different commit than expected.

```bash
# Reset submodule to tracked commit
git submodule update ankipi-meta

# Or update to latest and commit the reference
git submodule update --remote ankipi-meta
git add ankipi-meta
git commit -m "Update documentation reference"
```

### Submodule is empty after clone

You forgot to initialize/update submodules.

```bash
git submodule init
git submodule update
```

### Can't push changes from submodule

Make sure you're on a branch (not detached HEAD).

```bash
cd ankipi-meta
git checkout main
git pull origin main
# Now make your changes
```

### Merge conflicts in submodule reference

Different branches updated to different submodule commits.

```bash
# Choose which version you want
git checkout --theirs .gitmodules ankipi-meta
# or
git checkout --ours .gitmodules ankipi-meta

# Then update submodule
git submodule update
```

## Best Practices

### DO:
- ✅ Always pull latest docs before making changes
- ✅ Work on main branch of submodule
- ✅ Commit documentation changes separately from code
- ✅ Push submodule changes before parent repo
- ✅ Keep submodule reference updated

### DON'T:
- ❌ Make changes in detached HEAD state
- ❌ Forget to push submodule changes
- ❌ Commit submodule and code changes together
- ❌ Ignore submodule status in git status

## Alternative: No Submodule Setup

If you prefer not to use submodules, agents can still access the documentation:

### Option 1: Clone Separately
```bash
# Clone documentation repo separately
git clone https://github.com/jackymcgrady/ankipi-meta.git ~/ankipi-meta

# Reference in CLAUDE.md
echo "Documentation available at ~/ankipi-meta" >> CLAUDE.md
```

### Option 2: Fetch on Demand
```bash
# Agents can fetch docs via GitHub API when needed
# Add to CLAUDE.md:
"Documentation hub: https://github.com/jackymcgrady/ankipi-meta
Agents should fetch documentation using GitHub API as needed."
```

However, submodules provide the best experience for local development and keep documentation versioned with code.

## Summary

**Setup:** `git submodule add https://github.com/jackymcgrady/ankipi-meta.git ankipi-meta`
**Clone with submodules:** `git clone --recurse-submodules https://github.com/jackymcgrady/ankipi.git`
**Update docs:** `git submodule update --remote ankipi-meta`
**Make changes:** Work inside `ankipi-meta/`, commit there, then commit reference in parent

For questions or issues, see the main `README.md` or `CONTRIBUTING.md`.
