# GIT Commands

## New repository

Run these commands from the project root after reviewing the staged files:

```bash
git init
git branch -M main
git add .
git commit -m "Initialize syllabicator v2"
```

Add the GitHub remote only when the repository has been created there:

```bash
git remote add origin https://github.com/eagles-edu/syll_v2.git
git push -u origin main
```

## Existing repository

```bash
git remote add origin https://github.com/eagles-edu/syll_v2.git
git branch -M main
git push -u origin main
```
