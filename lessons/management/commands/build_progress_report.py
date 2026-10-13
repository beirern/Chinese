"""Build the public report from this machine's lesson and Anki data."""

import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Prefetch
from django.template.loader import render_to_string
from django.utils import timezone

from lessons.anki_sync import AnkiSyncError, sync_anki_progress
from lessons.models import Lesson, Source, Word
from lessons.views import progress_data


class Command(BaseCommand):
    help = "Generate the public, read-only progress report in docs/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.BASE_DIR / "docs",
            help="Directory to write the report HTML, CSS, and JavaScript (default: docs/).",
        )
        parser.add_argument(
            "--sync-anki",
            action="store_true",
            help="Refresh from local Anki before building; requires Anki and AnkiConnect.",
        )

    def handle(self, *args, **options):
        if options["sync_anki"]:
            try:
                result = sync_anki_progress()
            except AnkiSyncError as error:
                raise CommandError(str(error)) from error
            self.stdout.write(
                f"Anki: {result['matched']} matched, {result['unmatched']} unmatched, "
                f"{result['ambiguous']} ambiguous."
            )

        lessons = Lesson.objects.annotate(word_count=Count("vocabulary", distinct=True)).order_by(
            "created_at", "id"
        )
        sources = Source.objects.prefetch_related(Prefetch("lessons", queryset=lessons))
        source_rows = []
        for source in sorted(sources, key=lambda item: item.name.casefold()):
            source_rows.append({
                "id": source.id,
                "name": source.name,
                "creator": source.creator,
                "kind": source.kind,
                "kind_label": source.get_kind_display(),
                "url": source.url,
                "lessons": list(source.lessons.all()),
            })
        for source in source_rows:
            source["lesson_count"] = len(source["lessons"])

        word_rows = []
        words = (
            Word.objects.filter(lessons__isnull=False)
            .distinct()
            .select_related("anki_progress")
            .prefetch_related("lessons__source")
            .order_by("traditional", "pinyin", "id")
        )
        for word in words:
            linked_lessons = sorted(word.lessons.all(), key=lambda lesson: (lesson.created_at, lesson.id))
            lesson_names = [lesson.title for lesson in linked_lessons]
            source_ids = sorted({lesson.source_id for lesson in linked_lessons})
            anki_progress = getattr(word, "anki_progress", None)
            word_rows.append({
                "word": word,
                "lesson_names": lesson_names,
                "source_ids": " ".join(map(str, source_ids)),
                "search_text": " ".join((
                    word.traditional, word.simplified, word.pinyin, word.english,
                    *lesson_names, *(lesson.source.name for lesson in linked_lessons),
                )),
                "state": anki_progress.state if anki_progress else "unmatched",
                "state_label": anki_progress.get_state_display() if anki_progress else "No Anki match",
            })

        featured_word = next((row for row in word_rows if row["word"].traditional == "歡迎"), None)
        if featured_word is None and word_rows:
            featured_word = word_rows[0]
        featured_meaning = (
            "Welcome!" if featured_word and featured_word["word"].traditional == "歡迎"
            else featured_word["word"].english if featured_word else ""
        )

        progress = progress_data()
        status = progress["anki_status_chart"]
        context = {
            **progress,
            "sources": source_rows,
            "source_count": len(source_rows),
            "word_rows": word_rows,
            "featured_word": featured_word,
            "featured_meaning": featured_meaning,
            "report_date": timezone.localtime(),
            "anki_reviewing": next((segment["count"] for segment in status["segments"] if segment["key"] == "reviewing"), 0) if status else 0,
        }
        html = render_to_string("lessons/public_report.html", context)
        html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
        css = (Path(__file__).resolve().parents[2] / "static/lessons/public_report.css").read_text()
        javascript = (Path(__file__).resolve().parents[2] / "static/lessons/public_report.js").read_text()

        output = options["output"].resolve()
        output.mkdir(parents=True, exist_ok=True)
        self._write_file(output / "public_report.css", css)
        self._write_file(output / "public_report.js", javascript)
        self._write_file(output / "index.html", html)
        self.stdout.write(self.style.SUCCESS(f"Built report: {output / 'index.html'}"))

    @staticmethod
    def _write_file(destination, contents):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as temporary:
            temporary.write(contents)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
