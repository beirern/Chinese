import csv
import io
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.db import transaction
from django.forms import formset_factory
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Lesson, Source, Word


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ("source", "title", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class SourceForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = ("name", "kind", "url")


class LessonWordEntryForm(forms.Form):
    traditional = forms.CharField(max_length=100, label="Traditional")
    simplified = forms.CharField(max_length=100, label="Simplified")
    pinyin = forms.CharField(max_length=200, help_text="Tone marks; separate syllables with spaces.")
    english = forms.CharField(max_length=255, label="English meaning")


LessonWordFormSet = formset_factory(LessonWordEntryForm, extra=1, can_delete=True)


def lesson_list(request):
    sources = Source.objects.prefetch_related("lessons__vocabulary")
    return render(request, "lessons/lesson_list.html", {"sources": sources})


def home(request):
    return render(request, "lessons/home.html", {
        "lesson_count": Lesson.objects.count(),
        # Count distinct words linked as lesson vocabulary. Sentence-only words
        # are not part of the learner's known vocabulary total.
        "word_count": Word.objects.filter(lessons__isnull=False).distinct().count(),
    })


def progress(request):
    lesson_counts = {
        row["day"]: row["added"]
        for row in Lesson.objects.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(added=Count("id"))
    }
    word_counts = {
        row["day"]: row["added"]
        for row in Word.objects.filter(lessons__isnull=False)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(added=Count("id", distinct=True))
    }

    history = []
    lesson_total = word_total = 0
    for day in sorted(lesson_counts.keys() | word_counts.keys()):
        lessons_added = lesson_counts.get(day, 0)
        words_added = word_counts.get(day, 0)
        lesson_total += lessons_added
        word_total += words_added
        history.append({
            "day": day,
            "lessons_added": lessons_added,
            "words_added": words_added,
            "lesson_total": lesson_total,
            "word_total": word_total,
        })

    week_ago = timezone.localdate() - timedelta(days=7)
    comparison_available = bool(history and history[0]["day"] <= week_ago)
    week_ago_lessons = week_ago_words = 0
    if comparison_available:
        for row in history:
            if row["day"] > week_ago:
                break
            week_ago_lessons = row["lesson_total"]
            week_ago_words = row["word_total"]

    return render(request, "lessons/progress.html", {
        "history": reversed(history),
        "lesson_total": lesson_total,
        "word_total": word_total,
        "tracking_started": history[0]["day"] if history else None,
        "comparison_available": comparison_available,
        "week_ago": week_ago,
        "week_ago_lessons": week_ago_lessons,
        "week_ago_words": week_ago_words,
        "lessons_added_this_week": lesson_total - week_ago_lessons,
        "words_added_this_week": word_total - week_ago_words,
    })


def word_list(request):
    scope = request.GET.get("scope", "all")
    source_id = request.GET.get("source", "")
    lesson_ids = request.GET.getlist("lesson")
    words = words_for_filter(scope, source_id, lesson_ids)
    sources = Source.objects.prefetch_related("lessons")
    return render(request, "lessons/word_list.html", {
        "words": words,
        "sources": sources,
        "scope": scope,
        "selected_source": source_id,
        "selected_lessons": lesson_ids,
    })


def words_for_filter(scope, source_id, lesson_ids):
    words = Word.objects.filter(lessons__isnull=False)
    if scope == "source":
        if not source_id.isdigit():
            return words.none()
        words = words.filter(lessons__source_id=int(source_id))
    elif scope == "lessons":
        valid_ids = [int(value) for value in lesson_ids if value.isdigit()]
        if not valid_ids:
            return words.none()
        words = words.filter(lessons__id__in=valid_ids)
    return words.distinct()


def word_export(request):
    scope = request.GET.get("scope", "all")
    source_id = request.GET.get("source", "")
    lesson_ids = request.GET.getlist("lesson")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for word in words_for_filter(scope, source_id, lesson_ids):
        front = word.traditional
        if word.simplified != word.traditional:
            front += f"（{word.simplified}）"
        writer.writerow((front, f"{word.pinyin} - {word.english}"))
    response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="chinese-words-anki.csv"'
    return response


def lesson_create(request):
    if request.method == "POST":
        lesson_form = LessonForm(request.POST)
        entry_formset = LessonWordFormSet(request.POST, prefix="words")
        lesson_valid = lesson_form.is_valid()
        entries_valid = entry_formset.is_valid()
        valid = lesson_valid and entries_valid
        if valid:
            entries = [form for form in entry_formset if form.cleaned_data and not form.cleaned_data.get("DELETE")]
            seen_words = {}
            for form in entries:
                data = form.cleaned_data
                key = (data["traditional"], data["pinyin"])
                word_values = (data["simplified"], data["english"])
                prior = seen_words.get(key)
                existing = Word.objects.filter(traditional=key[0], pinyin=key[1]).first()
                if prior is not None and prior != word_values:
                    form.add_error(None, "This traditional form and pinyin were entered with conflicting simplified or English values in another row.")
                    valid = False
                elif existing and (existing.simplified, existing.english) != word_values:
                    form.add_error(None, "A word with this traditional form and pinyin already exists with different simplified or English data. Update that word first, or correct this row.")
                    valid = False
                seen_words[key] = word_values

            # The same word cannot be linked twice to one lesson.
            seen_keys = set()
            for form in entries:
                data = form.cleaned_data
                key = (data["traditional"], data["pinyin"])
                if key in seen_keys:
                    form.add_error(None, "This word appears more than once in the lesson. Keep only one row for it.")
                    valid = False
                seen_keys.add(key)

            if valid:
                with transaction.atomic():
                    lesson = lesson_form.save()
                    for form in entries:
                        data = form.cleaned_data
                        word, _ = Word.objects.get_or_create(
                            traditional=data["traditional"],
                            pinyin=data["pinyin"],
                            defaults={"simplified": data["simplified"], "english": data["english"]},
                        )
                        lesson.vocabulary.add(word)
                messages.success(request, f'Created “{lesson.title}” with {len(entries)} vocabulary entries.')
                return redirect("lesson-list")
    else:
        initial = {}
        if Source.objects.count() == 1:
            initial["source"] = Source.objects.first()
        lesson_form = LessonForm(initial=initial)
        entry_formset = LessonWordFormSet(prefix="words")

    return render(request, "lessons/lesson_form.html", {
        "lesson_form": lesson_form,
        "entry_formset": entry_formset,
    })


def source_create(request):
    if request.method == "POST":
        source_form = SourceForm(request.POST)
        if source_form.is_valid():
            source = source_form.save()
            messages.success(request, f'Created source “{source.name}”.')
            return redirect("lesson-create")
    else:
        source_form = SourceForm()

    return render(request, "lessons/source_form.html", {"source_form": source_form})
