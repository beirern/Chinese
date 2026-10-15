from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


def validate_journal_help(value):
    if not isinstance(value, list) or any(item not in ("google_translate", "pleco") for item in value):
        raise ValidationError("Select Google Translate, Pleco, or both.")


class JournalEntry(models.Model):
    class HelpUsed(models.TextChoices):
        GOOGLE_TRANSLATE = "google_translate", "Google Translate"
        PLECO = "pleco", "Pleco"

    title = models.CharField(max_length=200, blank=True)
    text = models.TextField(verbose_name="Chinese writing")
    english_note = models.TextField(blank=True, verbose_name="What I was trying to say in English")
    help_used = models.JSONField(default=list, blank=True, validators=[validate_journal_help])
    written_on = models.DateField(default=timezone.localdate, verbose_name="Writing date")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-written_on", "-created_at", "-id")
        verbose_name_plural = "journal entries"

    def __str__(self):
        return f"{self.written_on}: {self.title or self.text[:60]}"

    @property
    def help_used_labels(self):
        return [label for value, label in self.HelpUsed.choices if value in self.help_used]


class Word(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    traditional = models.CharField(max_length=100, help_text="Traditional Chinese form; used as the primary display form.")
    simplified = models.CharField(max_length=100)
    pinyin = models.CharField(
        max_length=200,
        help_text="Use tone marks and spaces between words, keeping syllables within a word together (for example, shénme shíhòu).",
    )
    english = models.CharField(max_length=255, verbose_name="English translation")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("traditional", "pinyin"), name="unique_word_traditional_pinyin"),
        ]
        ordering = ("traditional", "pinyin")

    def __str__(self):
        return f"{self.traditional} ({self.pinyin})"


class AnkiProgress(models.Model):
    class State(models.TextChoices):
        NEW = "new", "New"
        LEARNING = "learning", "Learning"
        REVIEWING = "reviewing", "Reviewing"
        RELEARNING = "relearning", "Relearning"
        SUSPENDED = "suspended", "Suspended"

    word = models.OneToOneField(Word, on_delete=models.CASCADE, related_name="anki_progress")
    card_id = models.BigIntegerField(unique=True)
    state = models.CharField(max_length=20, choices=State.choices)
    interval_days = models.PositiveIntegerField(default=0)
    again_count = models.PositiveIntegerField(default=0)
    hard_count = models.PositiveIntegerField(default=0)
    good_count = models.PositiveIntegerField(default=0)
    easy_count = models.PositiveIntegerField(default=0)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField()

    @property
    def answer_count(self):
        return self.again_count + self.hard_count + self.good_count + self.easy_count

    def __str__(self):
        return f"{self.word}: {self.get_state_display()}"


class Source(models.Model):
    class Kind(models.TextChoices):
        BOOK = "book", "Book"
        TEXTBOOK = "textbook", "Textbook"
        VIDEO = "video", "Video"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200, verbose_name="Title or name")
    creator = models.CharField(max_length=200, blank=True, verbose_name="Author or creator")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    url = models.URLField(blank=True, help_text="Optional link to the book, video, or other original material.")

    class Meta:
        ordering = ("name", "creator", "id")

    def __str__(self):
        return f"{self.name} — {self.creator}" if self.creator else self.name


class Lesson(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(help_text="Describe the lesson's setting or context.")
    vocabulary = models.ManyToManyField(Word, related_name="lessons", blank=True)

    class Meta:
        ordering = ("source__name", "title")
        constraints = [
            models.UniqueConstraint(fields=("source", "title"), name="unique_lesson_title_per_source"),
        ]

    def __str__(self):
        return self.title


class Sentence(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="sentences")
    text = models.TextField()
    words = models.ManyToManyField(Word, related_name="sentences", blank=True)

    class Meta:
        ordering = ("lesson", "id")

    def __str__(self):
        return self.text[:80]
