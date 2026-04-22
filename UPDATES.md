# How to Ship Updates

## Steps every time you want to push a new version to all users

1. Make your code changes

2. Bump the version in `shared/version.py`:
   ```python
   APP_VERSION = "1.2.0"  # change this
   ```

3. Update `version.json` in the project root:
   ```json
   {
     "version": "1.2.0",
     "download_url": "https://github.com/salma383/myva-call-analyzer/releases/latest/download/CallAnalyzer.exe",
     "release_notes": "Describe what changed here."
   }
   ```

4. Rebuild the exe:
   ```
   python build_config.py
   ```

5. Commit and push everything:
   ```
   git add -A
   git commit -m "v1.2.0 — describe what changed"
   git push
   ```

6. Create a new GitHub release and upload the exe:
   ```
   gh release create v1.2.0 "dist/CallAnalyzer.exe" --title "v1.2.0" --notes "Describe what changed"
   ```

That's it. Everyone who opens the old app will see an update prompt and can download the new exe with one click.

---

## Current release

- **Version:** 1.1.0
- **Repo:** https://github.com/salma383/myva-call-analyzer
- **Latest release:** https://github.com/salma383/myva-call-analyzer/releases/latest

---

## Swapping the app icon

If you want to use your actual logo instead of the generated one:

1. Save your logo as `assets/icons/logo.png`
2. Run: `python create_icon.py`
3. Run: `python build_config.py`
