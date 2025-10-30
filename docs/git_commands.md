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
git commit -m "Fix UI scrollbars and EDSM timing - improved prospector panel scrollbar, added vertical scrollbar to mineral analysis, fixed EDSM fallback timing issue"
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