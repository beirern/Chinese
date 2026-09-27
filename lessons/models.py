from django.db import models


class Word(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    traditional = models.CharField(max_length=100, help_text="Traditional Chinese form; used as the primary display form.")
    simplified = models.CharField(max_length=100)
    pinyin = models.CharField(
        max_length=200,
        help_text="Use tone marks (for example, nǐ hǎo) and separate syllables with spaces.",
    )
    english = models.CharField(max_length=255, verbose_name="English translation")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("traditional", "pinyin"), name="unique_word_traditional_pinyin"),
        ]
        ordering = ("traditional", "pinyin")

    def __str__(self):
        return f"{self.traditional} ({self.pinyin})"


class Source(models.Model):
    class Kind(models.TextChoices):
        TEXTBOOK = "textbook", "Textbook"
        VIDEO = "video", "Video"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    url = models.URLField(blank=True, help_text="Optional link to the book, video, or other original material.")

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


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
