# Chinese Study Site

## Purpose and current scope

This is a personal, context-first Chinese study site focused on Taiwanese usage and traditional characters. Vocabulary is collected from lessons and source material rather than as a disconnected word list. Lesson creation currently happens through a manually completed web form. Photo OCR, YouTube lesson creation, and practice modes such as flashcards, quizzes, dialogue, listening, and speaking are future ideas; they are not implemented yet.

## Current structure

- `chinese_site/` contains Django settings and the root URL configuration.
- `lessons/` contains the study models, lesson entry/list views, admin registrations, templates, and migrations.
- `/` lists lessons. `/lessons/new/` creates one lesson and its textbook vocabulary rows. `/admin/` is Django admin.
- `db.sqlite3` is the configured local database. Preserve it and existing records when changing the schema.

## Data model and invariants

- `Word` is a vocabulary unit. It may be one character, a multi-character word or compound (for example, 東西), or a learned expression (for example, 感興趣). Keep the automatic numeric primary key. Traditional Chinese, simplified Chinese, pinyin, and English are required; traditional characters are the primary display form. The database prevents duplicate `(traditional, pinyin)` pairs, allowing one traditional form to have multiple readings. Pinyin uses tone marks and spaces between syllables.
- `Lesson` has a title, context description, and intended vocabulary through `LessonWord`.
- `LessonWord` records a word's textbook section, position within that section, and optional part of speech. Its sections are Vocabulary, Phrases, Proper Nouns, and Supplementary Vocabulary. “Phrases” is a textbook section, not a separate model. A word can be reused across lessons, but appears at most once within a lesson.
- `Sentence` belongs to one lesson and links to words occurring in it. Keep this distinct from `LessonWord`: words mentioned in example sentences are not automatically intended lesson vocabulary.
- The lesson form saves the lesson and rows atomically. It reuses a word with matching traditional characters and pinyin only when simplified characters and English also match; conflicting details should be shown to the user, never silently overwritten.

Migration `0003` copies any links from the former automatic vocabulary join table into `LessonWord`. That old table may remain in an existing database; `LessonWord` is the authoritative relation.

## Setup and common commands

The project requires Python 3.13 or newer and declares Django in `pyproject.toml`; `uv.lock` is present. From the project root:

```sh
uv sync
uv run python manage.py migrate
uv run python manage.py check
uv run python manage.py runserver
```

Create schema changes with `uv run python manage.py makemigrations` and apply them with `uv run python manage.py migrate`. Commit migration files with model changes. Do not reset or replace the SQLite database to apply schema changes.

## Implementation guidance

Keep the schema and dependencies small. Preserve the source lesson's section and row order when importing vocabulary. Do not introduce a separate phrase model or treat sentence words as lesson vocabulary. Treat future OCR/video ingestion as a prefill path for reviewed lesson data unless the product requirements change.
