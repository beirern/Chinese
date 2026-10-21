import csv
import io
from unittest.mock import patch
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .anki_sync import AnkiSyncError, sync_anki_progress
from .models import AnkiProgress, JournalEntry, Lesson, Source, Word


class JournalTests(TestCase):
    def test_help_choices_and_clearing(self):
        for choice in JournalEntry.HelpUsed:
            response = self.client.post(reverse("journal-create"), {
                "written_on": "2026-10-13", "text": "今天我寫日記。", "help_used": choice,
            })
            entry = JournalEntry.objects.latest("id")
            self.assertRedirects(response, reverse("journal-detail", args=[entry.pk]))
            self.assertEqual(entry.help_used, [choice])
            self.assertContains(self.client.get(reverse("journal-detail", args=[entry.pk])), choice.label)
        self.client.post(reverse("journal-edit", args=[entry.pk]), {
            "written_on": "2026-10-13", "text": entry.text,
        })
        entry.refresh_from_db()
        self.assertEqual(entry.help_used, [])
        response = self.client.post(reverse("journal-create"), {
            "written_on": "2026-10-13", "text": "日記", "help_used": "unknown",
        })
        self.assertIn("help_used", response.context["form"].errors)

    def test_both_help_tools_are_saved_and_preselected_when_editing(self):
        self.client.post(reverse("journal-create"), {
            "written_on": "2026-10-13", "text": "日記", "help_used": ["google_translate", "pleco"],
        })
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.help_used, ["google_translate", "pleco"])
        response = self.client.get(reverse("journal-edit", args=[entry.pk]))
        self.assertEqual(response.context["form"].initial["help_used"], entry.help_used)
        response = self.client.get(reverse("journal-detail", args=[entry.pk]))
        self.assertContains(response, "Google Translate, Pleco")

    def test_create_backdated_entry_and_edit_in_place(self):
        response = self.client.post(reverse("journal-create"), {
            "written_on": "2026-09-01",
            "text": "今天我去公園。\n天氣很好。",
            "english_note": "I went to the park today. The weather was nice.",
        })
        entry = JournalEntry.objects.get()
        self.assertRedirects(response, reverse("journal-detail", args=[entry.pk]))
        self.assertEqual(entry.written_on, date(2026, 9, 1))
        created_at, updated_at = entry.created_at, entry.updated_at
        response = self.client.get(reverse("journal-edit", args=[entry.pk]))
        self.assertContains(response, 'value="2026-09-01"')
        with patch("django.utils.timezone.now", return_value=datetime(2027, 1, 1, tzinfo=UTC)):
            response = self.client.post(reverse("journal-edit", args=[entry.pk]), {
                "written_on": "2026-09-02", "text": "今天我去了公園。", "english_note": "",
            })
        self.assertRedirects(response, reverse("journal-detail", args=[entry.pk]))
        entry.refresh_from_db()
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(entry.text, "今天我去了公園。")
        self.assertEqual(entry.english_note, "")
        self.assertEqual(entry.created_at, created_at)
        self.assertNotEqual(entry.updated_at, updated_at)

    def test_form_validation_preserves_input(self):
        response = self.client.post(reverse("journal-create"), {
            "written_on": "invalid", "text": "", "english_note": "My intended meaning",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My intended meaning")
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(JournalEntry.objects.exists())

    def test_list_orders_by_writing_date_and_detail_escapes_text(self):
        newer = JournalEntry.objects.create(written_on=date(2026, 10, 1), text="新的日記")
        older = JournalEntry.objects.create(
            written_on=date(2026, 9, 1), text='<script>alert("test")</script>', english_note="An English note",
        )
        response = self.client.get(reverse("journal-list"))
        self.assertEqual(list(response.context["entries"]), [newer, older])
        response = self.client.get(reverse("journal-detail", args=[older.pk]))
        self.assertContains(response, "An English note")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("test")</script>')
        self.assertEqual(self.client.get(reverse("journal-edit", args=[999999])).status_code, 404)

    def test_empty_list_and_default_date(self):
        self.assertContains(self.client.get(reverse("journal-list")), "Write your first entry")
        response = self.client.get(reverse("journal-create"))
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')


class SourceTests(TestCase):
    def test_books_with_same_title_can_be_distinguished_by_author(self):
        first = Source.objects.create(name="Shared title", kind=Source.Kind.BOOK, creator="First author")
        second = Source.objects.create(name="Shared title", kind=Source.Kind.BOOK, creator="Second author")

        response = self.client.get(reverse("lesson-list"))
        self.assertContains(response, "First author")
        self.assertContains(response, "Second author")
        self.assertEqual(str(first), "Shared title — First author")
        self.assertEqual(str(second), "Shared title — Second author")

    def test_source_form_accepts_book_and_creator(self):
        response = self.client.post(reverse("source-create"), {
            "kind": Source.Kind.BOOK,
            "name": "Book title",
            "creator": "Book author",
            "url": "",
        })

        self.assertRedirects(response, reverse("lesson-create"))
        self.assertTrue(Source.objects.filter(name="Book title", kind="book", creator="Book author").exists())


class LessonWordReadingTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(name="Textbook")
        self.word = Word.objects.create(
            traditional="行", simplified="行", pinyin="xíng", english="to walk"
        )

    def lesson_data(self, pinyin, confirm=False):
        return {
            "source": self.source.pk,
            "title": "New lesson",
            "description": "Reading practice",
            "words-TOTAL_FORMS": "1",
            "words-INITIAL_FORMS": "0",
            "words-MIN_NUM_FORMS": "0",
            "words-MAX_NUM_FORMS": "1000",
            "words-0-traditional": "行",
            "words-0-simplified": "行",
            "words-0-pinyin": pinyin,
            "words-0-english": "to walk",
            "words-0-confirm_new_reading": "on" if confirm else "",
        }

    def test_different_pinyin_shows_existing_reading_without_saving(self):
        response = self.client.post(reverse("lesson-create"), self.lesson_data("xing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "xíng (to walk)")
        self.assertContains(response, "This is a different reading")
        self.assertFalse(Lesson.objects.exists())
        self.assertEqual(Word.objects.count(), 1)

    def test_corrected_pinyin_reuses_word(self):
        response = self.client.post(reverse("lesson-create"), self.lesson_data("xíng"))

        self.assertRedirects(response, reverse("lesson-list"))
        self.assertEqual(Word.objects.count(), 1)
        self.assertEqual(list(Lesson.objects.get().vocabulary.all()), [self.word])

    def test_confirmed_different_reading_creates_another_word(self):
        response = self.client.post(reverse("lesson-create"), self.lesson_data("háng", confirm=True))

        self.assertRedirects(response, reverse("lesson-list"))
        self.assertEqual(Word.objects.count(), 2)
        self.assertEqual(list(Lesson.objects.get().vocabulary.values_list("pinyin", flat=True)), ["háng"])


class WordExportTests(TestCase):
    def test_export_shows_only_traditional_on_front_and_keeps_clean_tts_text(self):
        word = Word.objects.create(
            traditional="女兒", simplified="女儿", pinyin="nǚ'ér", english="daughter, girl"
        )
        source = Source.objects.create(name="Textbook")
        lesson = Lesson.objects.create(source=source, title="Family")
        lesson.vocabulary.add(word)
        # A reused word must still produce just one import row.
        other = Lesson.objects.create(source=source, title="People")
        other.vocabulary.add(word)

        response = self.client.get(reverse("word-export"))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows, [["女兒", "nǚ'ér - daughter, girl<br>Simplified: 女儿", "女兒"]])
        page = self.client.get(reverse("word-list"))
        self.assertContains(page, "CSV columns: Front, Back, Chinese")


class PracticeTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(name="Textbook")
        self.other_source = Source.objects.create(name="Stories")
        self.lesson = Lesson.objects.create(source=self.source, title="Family")
        self.other_lesson = Lesson.objects.create(source=self.other_source, title="New neighbor")
        self.word = Word.objects.create(
            traditional="姊姊/姐姐", simplified="姐姐", pinyin="jiějie", english="older sister"
        )
        self.other_word = Word.objects.create(
            traditional="鄰居", simplified="邻居", pinyin="línjū", english="neighbor"
        )
        self.lesson.vocabulary.add(self.word)
        self.other_lesson.vocabulary.add(self.word, self.other_word)
        Word.objects.create(traditional="水", simplified="水", pinyin="shuǐ", english="water")

    def test_uses_lesson_vocabulary_once_and_retains_readings_and_context(self):
        response = self.client.get(reverse("practice"))
        rows = response.context["practice_words"]
        self.assertEqual({row["id"] for row in rows}, {self.word.id, self.other_word.id})
        row = next(row for row in rows if row["id"] == self.word.id)
        self.assertEqual(row["traditional"], "姊姊/姐姐")
        self.assertEqual(row["pinyin"], "jiějie")
        self.assertEqual(set(row["lessons"]), {"Textbook · Family", "Stories · New neighbor"})
        self.assertFalse(AnkiProgress.objects.exists())

    def test_filters_sources_and_lessons_without_writing_data(self):
        before = (Word.objects.count(), Lesson.objects.count())
        for params, expected in [
            ({"scope": "source", "source": self.source.id}, {self.word.id}),
            ({"scope": "lessons", "lesson": [self.other_lesson.id]}, {self.word.id, self.other_word.id}),
            ({"scope": "source", "source": "invalid"}, set()),
            ({"scope": "lessons", "lesson": ["invalid"]}, set()),
        ]:
            with self.subTest(params=params):
                response = self.client.get(reverse("practice"), params)
                self.assertEqual({row["id"] for row in response.context["practice_words"]}, expected)
        self.assertEqual((Word.objects.count(), Lesson.objects.count()), before)
        self.assertFalse(AnkiProgress.objects.exists())

    def test_json_payload_escapes_script_content_and_mode_is_validated(self):
        self.word.english = '</script><script>alert("test")</script>'
        self.word.save()
        response = self.client.get(reverse("practice"), {"mode": "writing"})
        self.assertEqual(response.context["mode"], "writing")
        self.assertNotContains(response, '<script>alert("test")</script>')
        self.assertContains(response, r"\u003C/script\u003E")
        self.assertEqual(self.client.get(reverse("practice"), {"mode": "unknown"}).context["mode"], "listening")


class AnkiProgressTests(TestCase):
    def setUp(self):
        self.word = Word.objects.create(
            traditional="女兒", simplified="女儿", pinyin="nü'ér", english="daughter"
        )
        source = Source.objects.create(name="Textbook")
        lesson = Lesson.objects.create(source=source, title="Family", description="Family")
        lesson.vocabulary.add(self.word)

    def anki_response(self, action, **params):
        if action == "deckNames":
            return ["Default", "My Mandarin Lessons", "SpoonfedChinese Traditional"]
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
    def test_sync_matches_new_layout_without_existing_snapshot(self, request):
        def response(action, **params):
            result = self.anki_response(action, **params)
            if action == "notesInfo":
                result[0]["fields"]["Front"]["value"] = "女兒"
                result[0]["fields"]["Back"]["value"] = "nü&#x27;ér - daughter<br>Simplified: 女儿"
            return result

        request.side_effect = response
        self.assertEqual(sync_anki_progress(), {"matched": 1, "unmatched": 0, "ambiguous": 0})
        self.assertEqual(AnkiProgress.objects.get(word=self.word).card_id, 20)

    @patch("lessons.anki_sync.anki_request")
    def test_sync_rejects_ambiguous_old_and_new_layouts(self, request):
        def response(action, **params):
            result = self.anki_response(action, **params)
            if action == "notesInfo":
                result.append({"cards": [21], "fields": {
                    "Front": {"value": "女兒"},
                    "Back": {"value": "nü'ér - daughter<br>Simplified: 女儿"},
                }})
            return result

        request.side_effect = response
        self.assertEqual(sync_anki_progress(), {"matched": 0, "unmatched": 1, "ambiguous": 1})
        self.assertFalse(AnkiProgress.objects.exists())

    @patch("lessons.anki_sync.anki_request")
    def test_sync_counts_answers_and_displays_status(self, request):
        request.side_effect = self.anki_response
        self.assertEqual(sync_anki_progress(), {"matched": 1, "unmatched": 0, "ambiguous": 0})
        request.assert_any_call("deckNames")
        request.assert_any_call(
            "findNotes", query='deck:"My Mandarin Lessons" -deck:"My Mandarin Lessons::*"'
        )
        self.assertEqual(
            [call.kwargs["query"] for call in request.call_args_list if call.args[0] == "findNotes"],
            ['deck:"My Mandarin Lessons" -deck:"My Mandarin Lessons::*"'],
        )
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

    @patch("lessons.anki_sync.anki_request")
    def test_missing_deck_keeps_existing_snapshot(self, request):
        request.side_effect = self.anki_response
        sync_anki_progress()
        request.reset_mock()
        request.return_value = ["Default", "SpoonfedChinese Traditional"]
        request.side_effect = None

        response = self.client.post(reverse("word-sync-anki"), follow=True)

        self.assertContains(response, 'Anki deck &quot;My Mandarin Lessons&quot; was not found')
        request.assert_called_once_with("deckNames")
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


class PublicReportTests(TestCase):
    def test_build_uses_local_sources_lessons_and_anki_snapshot(self):
        source = Source.objects.create(
            name="Book & More", kind=Source.Kind.BOOK, creator="An Author",
            url="https://example.com/book",
        )
        lesson = Lesson.objects.create(source=source, title="Greetings", description="Say <hello>")
        word = Word.objects.create(
            traditional="你好", simplified="你好", pinyin="nǐ hǎo", english="hello"
        )
        lesson.vocabulary.add(word)
        next_lesson = Lesson.objects.create(source=source, title="More greetings", description="Practice")
        next_lesson.vocabulary.add(word)
        AnkiProgress.objects.create(
            word=word, card_id=123, state=AnkiProgress.State.REVIEWING,
            synced_at=timezone.now(),
        )

        with TemporaryDirectory() as directory:
            output = Path(directory)
            call_command("build_progress_report", output=output)
            html = (output / "index.html").read_text()
            self.assertTrue((output / "public_report.css").is_file())
            self.assertTrue((output / "public_report.js").is_file())

        self.assertIn("My Chinese", html)
        self.assertIn('<div class="feature-caption"><span>nǐ hǎo</span><strong>hello</strong></div>', html)
        self.assertIn("Book &amp; More", html)
        self.assertIn('href="https://example.com/book"', html)
        self.assertIn("Greetings", html)
        self.assertIn("More greetings", html)
        self.assertEqual(html.count('class="word-row"'), 1)
        self.assertIn('data-search="你好 你好 nǐ hǎo hello Greetings More greetings Book &amp; More Book &amp; More"', html)
        self.assertIn('data-state="reviewing"', html)
        self.assertIn('aria-label="Vocabulary pages"', html)
        self.assertIn("1</strong><span>cards reviewing", html)
        self.assertNotIn("/admin/", html)

    @patch("lessons.management.commands.build_progress_report.sync_anki_progress")
    def test_failed_anki_sync_does_not_replace_report(self, sync):
        sync.side_effect = AnkiSyncError("Anki is closed")
        with TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "index.html").write_text("previous report")
            with self.assertRaisesMessage(CommandError, "Anki is closed"):
                call_command("build_progress_report", output=output, sync_anki=True)
            self.assertEqual((output / "index.html").read_text(), "previous report")
            self.assertFalse((output / "public_report.css").exists())
