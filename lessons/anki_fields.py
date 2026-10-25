"""Shared field layout for Anki exports and progress matching."""

from html import escape

from django.db.models import Prefetch

from .models import Sentence, Source


def song_sentences():
    return Sentence.objects.filter(lesson__source__kind=Source.Kind.SONG).select_related("lesson__source")


def with_anki_context(words):
    return words.prefetch_related(Prefetch("sentences", queryset=song_sentences(), to_attr="anki_sentences"))


def word_anki_fields(word, *, include_context=True):
    back = f"{word.pinyin} - {word.english}<br>Simplified: {word.simplified}"
    if include_context:
        sentences = getattr(word, "anki_sentences", None)
        if sentences is None:
            sentences = song_sentences().filter(words=word)
        seen = set()
        for sentence in sentences:
            text = sentence.text.strip()
            key = (sentence.lesson_id, text)
            if not text or key in seen:
                continue
            seen.add(key)
            source = sentence.lesson.source
            attribution = source.name
            if source.creator:
                attribution += f" — {source.creator}"
            text = escape(text).replace("\n", "<br>")
            back += (
                '<div class="song-context" style="margin-top: 16px;">'
                f'<small>{escape(attribution)}</small><br>{text}</div>'
            )
    return (
        word.traditional,
        back,
        word.traditional,
        word.english,
        word.simplified,
    )
