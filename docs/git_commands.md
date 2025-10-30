# Git Commands Reference

## Standard Commit and Push Process

```bash
# 1. Stage all changes
git add .

# 2. Commit with descriptive message
git commit -m "Your commit message here"

# 3. Push to remote repository
git push
```

## Recent Commits

### Latest Fixes (October 30, 2025)
```bash
git add .
git commit -m "Fixed auto-search clearing results when selecting planets within the same system - now only triggers on actual FSD jumps to new systems, preserving search results during planet navigation"
git push
```

### Previous Fixes
```bash
git add .
git commit -m "Fix refinery dialog for single sessions - only show at session end, not when cargo emptied"
git push
```

## Other Useful Git Commands

### Check Status
```bash
git status
```

### View Recent Commits
```bash
git log --oneline -10
```

### View Changes
```bash
git diff
```

### Create and Switch to New Branch
```bash
git checkout -b feature-branch-name
```

### Switch Between Branches
```bash
git checkout main
git checkout feature-branch-name
```

### Merge Branch to Main
```bash
git checkout main
git merge feature-branch-name
```

### Pull Latest Changes
```bash
git pull
```

### Reset to Last Commit (CAREFUL!)
```bash
git reset --hard HEAD
```

### View Remote Repository
```bash
git remote -v
```