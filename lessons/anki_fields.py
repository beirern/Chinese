"""Shared field layout for Anki exports and progress matching."""


def word_anki_fields(word):
    return (
        word.traditional,
        f"{word.pinyin} - {word.english}<br>Simplified: {word.simplified}",
        word.traditional,
        word.english,
        word.simplified,
    )
