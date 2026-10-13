# Public progress report

The Django site and Anki sync run locally. GitHub Pages publishes only the generated files in `docs/`.

Refresh the report from the project root:

```sh
uv run python manage.py build_progress_report --sync-anki
```

Keep Anki desktop and AnkiConnect open for this command. If the sync fails, the command stops before changing the report. To use the last locally saved Anki snapshot instead:

```sh
uv run python manage.py build_progress_report
```

Open `docs/index.html` to review the result. Then commit and push the generated `docs/` files. The workflow in `.github/workflows/pages.yml` deploys that snapshot when `docs/` changes on `main`. Running the workflow manually republishes the committed snapshot; GitHub Actions cannot access your local database or Anki app.

In the GitHub repository's **Settings → Pages**, select **GitHub Actions** as the build and deployment source. The published project URL is `https://beirern.github.io/Chinese/`.

The local `db.sqlite3` is ignored by Git. The report contains aggregate counts, source names and links, and lesson titles and descriptions; review `docs/index.html` before committing if you want to keep any lesson text private.
