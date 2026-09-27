from django.contrib import admin
from .models import Lesson, Sentence, Source, Word


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
    list_display = ("name", "kind", "url")
    list_filter = ("kind",)
    search_fields = ("name",)


@admin.register(Sentence)
class SentenceAdmin(admin.ModelAdmin):
    list_display = ("text", "lesson")
    list_filter = ("lesson",)
    search_fields = ("text",)
    filter_horizontal = ("words",)
