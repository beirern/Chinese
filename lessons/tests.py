from unittest.mock import patch
from datetime import UTC, date, datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .anki_sync import AnkiSyncError, sync_anki_progress
from .models import AnkiProgress, Lesson, Source, Word


class AnkiProgressTests(TestCase):
    def setUp(self):
        self.word = Word.objects.create(
            traditional="女兒", simplified="女儿", pinyin="nü'ér", english="daughter"
        )
        source = Source.objects.create(name="Textbook")
        lesson = Lesson.objects.create(source=source, title="Family", description="Family")
        lesson.vocabulary.add(self.word)

    def anki_response(self, action, **params):
        if action == "findNotes":
            return [10]
        if action == "notesInfo":
            return [{
                "cards": [20],
                "fields": {
                    "Front": {"value": "女兒（女儿）"},
                    "Back": {"value": "nü&#x27;ér - daughter"},
                },
            }]
        if action == "cardsInfo":
            return [{"cardId": 20, "queue": 2, "type": 2, "interval": 18}]
        if action == "getReviewsOfCards":
            return {"20": [
                {"id": 1_700_000_000_000, "ease": 1},
                {"id": 1_700_000_100_000, "ease": 3},
                {"id": 1_700_000_200_000, "ease": 4},
            ]}
        self.fail(f"Unexpected Anki action: {action}")

    @patch("lessons.anki_sync.anki_request")
    def test_sync_counts_answers_and_displays_status(self, request):
        request.side_effect = self.anki_response
        self.assertEqual(sync_anki_progress(), {"matched": 1, "unmatched": 0, "ambiguous": 0})
        progress = AnkiProgress.objects.get(word=self.word)
        self.assertEqual(progress.state, AnkiProgress.State.REVIEWING)
        self.assertEqual(progress.answer_count, 3)
        self.assertEqual((progress.again_count, progress.good_count, progress.easy_count), (1, 1, 1))
        self.assertEqual(progress.interval_days, 18)
        self.assertIsNotNone(progress.last_reviewed_at)
        response = self.client.get(reverse("word-list"))
        self.assertContains(response, "Reviewing")
        self.assertContains(response, "Answered 3 times")
        self.assertContains(response, "Again 1")

    @patch("lessons.anki_sync.anki_request")
    def test_failed_refresh_keeps_existing_snapshot(self, request):
        request.side_effect = self.anki_response
        sync_anki_progress()
        request.side_effect = AnkiSyncError("Anki is closed")
        response = self.client.post(reverse("word-sync-anki"), follow=True)
        self.assertContains(response, "Anki is closed")
        self.assertEqual(AnkiProgress.objects.get(word=self.word).answer_count, 3)

    def test_refresh_requires_post(self):
        response = self.client.get(reverse("word-sync-anki"))
        self.assertEqual(response.status_code, 405)

    def test_progress_groups_utc_midnight_under_pacific_day(self):
        timestamp = datetime(2026, 9, 28, 0, 8, tzinfo=UTC)
        Word.objects.filter(pk=self.word.pk).update(created_at=timestamp)
        Lesson.objects.update(created_at=timestamp)
        response = self.client.get(reverse("progress"))
        self.assertEqual(response.context["tracking_started"], date(2026, 9, 27))

    def test_status_chart_counts_distinct_lesson_words_and_missing_matches(self):
        other = Word.objects.create(
            traditional="媽媽", simplified="妈妈", pinyin="mā ma", english="mother"
        )
        lesson = Lesson.objects.get(title="Family")
        lesson.vocabulary.add(other)
        another_lesson = Lesson.objects.create(source=lesson.source, title="More family", description="")
        another_lesson.vocabulary.add(self.word)
        AnkiProgress.objects.create(
            word=self.word,
            card_id=20,
            state=AnkiProgress.State.REVIEWING,
            synced_at=timezone.now(),
        )

        response = self.client.get(reverse("progress"))
        chart = response.context["anki_status_chart"]
        counts = {segment["key"]: segment["count"] for segment in chart["segments"]}
        self.assertEqual(response.context["word_total"], 2)
        self.assertEqual(counts["reviewing"], 1)
        self.assertEqual(counts["unmatched"], 1)
        self.assertContains(response, "Reviewing: 1")
        self.assertContains(response, "No Anki match: 1")

    def test_status_chart_has_unsynced_empty_state(self):
        response = self.client.get(reverse("progress"))
        self.assertIsNone(response.context["anki_status_chart"])
        self.assertContains(response, "No Anki progress has been synced yet")
