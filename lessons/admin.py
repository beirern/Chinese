from django.contrib import admin
from .models import JournalEntry, Lesson, Sentence, Source, Word
from .forms import JournalEntryForm


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    form = JournalEntryForm
    list_display = ("written_on", "title", "text", "help_used_labels", "created_at", "updated_at")
    search_fields = ("title", "text", "english_note")
    date_hierarchy = "written_on"
    readonly_fields = ("created_at", "updated_at")


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ("traditional", "simplified", "pinyin", "english")
    search_fields = ("traditional", "simplified", "pinyin", "english")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "source")
    list_filter = ("source",)
    search_fields = ("title", "description")
    filter_horizontal = ("vocabulary",)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "creator", "kind", "url")
    list_filter = ("kind",)
    search_fields = ("name", "creator")


@admin.register(Sentence)
class SentenceAdmin(admin.ModelAdmin):
    list_display = ("text", "lesson")
    list_filter = ("lesson",)
    search_fields = ("text",)
    filter_horizontal = ("words",)
