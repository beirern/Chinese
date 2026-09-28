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


ANKI_CONNECT_URL = "http://127.0.0.1:8765"


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

    note_ids = anki_request("findNotes", query="")
    notes = [note for group in batches(note_ids) for note in anki_request("notesInfo", notes=group)]
    by_card_id = {}
    by_content = defaultdict(list)
    for note in notes:
        cards = note.get("cards", [])
        fields = note.get("fields", {})
        if len(cards) != 1 or "Front" not in fields or "Back" not in fields:
            continue
        card_id = cards[0]
        by_card_id[card_id] = note
        key = (html.unescape(fields["Front"]["value"]), html.unescape(fields["Back"]["value"]))
        by_content[key].append(note)

    matched = {}
    used_cards = set()
    ambiguous = 0
    for word in words:
        old = existing.get(word.id)
        if old and old.card_id in by_card_id:
            note = by_card_id[old.card_id]
        else:
            front = word.traditional
            if word.simplified != word.traditional:
                front += f"（{word.simplified}）"
            candidates = by_content[(front, f"{word.pinyin} - {word.english}")]
            if len(candidates) > 1:
                ambiguous += 1
            if len(candidates) != 1:
                continue
            note = candidates[0]
        card_id = note["cards"][0]
        if card_id in used_cards:
            ambiguous += 1
            continue
        used_cards.add(card_id)
        matched[word.id] = card_id

    card_ids = list(matched.values())
    cards = {}
    reviews = {}
    for group in batches(card_ids):
        cards.update({card["cardId"]: card for card in anki_request("cardsInfo", cards=group)})
        reviews.update(anki_request("getReviewsOfCards", cards=group))
    if set(cards) != set(card_ids):
        raise AnkiSyncError("Anki did not return every matched card. No progress was saved.")

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
