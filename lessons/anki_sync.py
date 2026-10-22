"""Read review progress from the locally running Anki desktop app."""

import html
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from .models import AnkiProgress, Word
from .anki_fields import word_anki_fields


ANKI_CONNECT_URL = "http://127.0.0.1:8765"
ANKI_DECK_NAME = "My Mandarin Lessons"


class AnkiSyncError(Exception):
    pass


def anki_request(action, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    request = Request(ANKI_CONNECT_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise AnkiSyncError("Could not reach AnkiConnect. Open Anki desktop and check that the add-on is running.") from error
    if data.get("error") is not None:
        raise AnkiSyncError(f"AnkiConnect: {data['error']}")
    return data["result"]


def batches(values, size=100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def card_state(card):
    if card["queue"] == -1:
        return AnkiProgress.State.SUSPENDED
    return {
        0: AnkiProgress.State.NEW,
        1: AnkiProgress.State.LEARNING,
        2: AnkiProgress.State.REVIEWING,
        3: AnkiProgress.State.RELEARNING,
    }[card["type"]]


def sync_anki_progress():
    """Replace local snapshots after all Anki reads succeed; never alter Anki."""
    words = list(Word.objects.all())
    existing = {progress.word_id: progress for progress in AnkiProgress.objects.all()}

    if ANKI_DECK_NAME not in anki_request("deckNames"):
        raise AnkiSyncError(f'Anki deck "{ANKI_DECK_NAME}" was not found. No progress was saved.')
    note_ids = anki_request(
        "findNotes", query=f'deck:"{ANKI_DECK_NAME}" -deck:"{ANKI_DECK_NAME}::*"'
    )
    notes = [note for group in batches(note_ids) for note in anki_request("notesInfo", notes=group)]
    by_card_id = {}
    by_content = defaultdict(list)
    for note in notes:
        cards = note.get("cards", [])
        fields = note.get("fields", {})
        if not cards or "Front" not in fields or "Back" not in fields:
            continue
        for card_id in cards:
            by_card_id[card_id] = note
        key = (html.unescape(fields["Front"]["value"]), html.unescape(fields["Back"]["value"]))
        by_content[key].append(note)

    matched_notes = {}
    ambiguous = 0
    for word in words:
        old = existing.get(word.id)
        if old and old.card_id in by_card_id:
            note = by_card_id[old.card_id]
        else:
            front = word.traditional
            if word.simplified != word.traditional:
                front += f"（{word.simplified}）"
            # Support both updated cards and older imports without a snapshot.
            new_front, new_back = word_anki_fields(word)[:2]
            keys = {(new_front, new_back), (front, f"{word.pinyin} - {word.english}")}
            candidates = [note for key in keys for note in by_content[key]]
            if len(candidates) > 1:
                ambiguous += 1
            if len(candidates) != 1:
                continue
            note = candidates[0]
        matched_notes[word.id] = note

    card_ids = list(dict.fromkeys(
        card_id for note in matched_notes.values() for card_id in note["cards"]
    ))
    cards = {}
    for group in batches(card_ids):
        cards.update({card["cardId"]: card for card in anki_request("cardsInfo", cards=group)})
    if set(cards) != set(card_ids):
        raise AnkiSyncError("Anki did not return every matched card. No progress was saved.")

    matched = {}
    used_cards = set()
    for word_id, note in matched_notes.items():
        note_cards = note["cards"]
        old = existing.get(word_id)
        if old and old.card_id in note_cards:
            # Keep tracking the same card even if templates have been reordered.
            card_id = old.card_id
        elif len(note_cards) == 1:
            card_id = note_cards[0]
        else:
            # New reverse templates are appended; ord 0 is the original direction.
            forward = [card_id for card_id in note_cards if cards[card_id].get("ord") == 0]
            if len(forward) != 1:
                raise AnkiSyncError("Could not identify the original Anki card. No progress was saved.")
            card_id = forward[0]
        if card_id in used_cards:
            ambiguous += 1
            continue
        used_cards.add(card_id)
        matched[word_id] = card_id

    reviews = {}
    for group in batches(list(matched.values())):
        reviews.update(anki_request("getReviewsOfCards", cards=group))

    now = timezone.now()
    with transaction.atomic():
        AnkiProgress.objects.exclude(word_id__in=matched).delete()
        for word_id, card_id in matched.items():
            card = cards[card_id]
            history = reviews.get(str(card_id), reviews.get(card_id, []))
            counts = Counter(row["ease"] for row in history)
            latest = max((row["id"] for row in history), default=None)
            AnkiProgress.objects.update_or_create(
                word_id=word_id,
                defaults={
                    "card_id": card_id,
                    "state": card_state(card),
                    "interval_days": max(0, card["interval"]),
                    "again_count": counts[1],
                    "hard_count": counts[2],
                    "good_count": counts[3],
                    "easy_count": counts[4],
                    "last_reviewed_at": datetime.fromtimestamp(latest / 1000, tz=UTC) if latest else None,
                    "synced_at": now,
                },
            )
    return {"matched": len(matched), "unmatched": len(words) - len(matched), "ambiguous": ambiguous}
