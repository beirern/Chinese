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
from lessons.models import Lesson, Source
from lessons.views import progress_data


class Command(BaseCommand):
    help = "Generate the public, read-only progress report in docs/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.BASE_DIR / "docs",
            help="Directory to write index.html and public_report.css (default: docs/).",
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
        kind_order = {Source.Kind.TEXTBOOK: 0, Source.Kind.BOOK: 1, Source.Kind.VIDEO: 2}
        source_rows = []
        for source in sorted(sources, key=lambda item: (kind_order.get(item.kind, 3), item.name)):
            source_rows.append({
                "name": source.name,
                "creator": source.creator,
                "kind": source.kind,
                "kind_label": source.get_kind_display(),
                "url": source.url,
                "lessons": list(source.lessons.all()),
            })
        for source in source_rows:
            source["lesson_count"] = len(source["lessons"])

        progress = progress_data()
        status = progress["anki_status_chart"]
        segments = [segment for segment in status["segments"] if segment["count"]] if status else []
        context = {
            **progress,
            "sources": source_rows,
            "source_count": len(source_rows),
            "report_date": timezone.localtime(),
            "anki_segments": segments,
            "anki_matched": sum(segment["count"] for segment in segments if segment["key"] != "unmatched"),
            "anki_reviewing": next((segment["count"] for segment in segments if segment["key"] == "reviewing"), 0),
        }
        html = render_to_string("lessons/public_report.html", context)
        html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
        css = (Path(__file__).resolve().parents[2] / "static/lessons/public_report.css").read_text()

        output = options["output"].resolve()
        output.mkdir(parents=True, exist_ok=True)
        self._write_file(output / "public_report.css", css)
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
