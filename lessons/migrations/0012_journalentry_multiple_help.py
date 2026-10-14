from django.db import migrations, models
import lessons.models


def copy_help(apps, schema_editor):
    entries = apps.get_model("lessons", "JournalEntry").objects.using(schema_editor.connection.alias)
    for entry in entries.all().iterator():
        entry.help_used = [entry.legacy_help_used] if entry.legacy_help_used else []
        entry.save(update_fields=["help_used"])


def restore_help(apps, schema_editor):
    entries = apps.get_model("lessons", "JournalEntry").objects.using(schema_editor.connection.alias)
    for entry in entries.all().iterator():
        entry.legacy_help_used = entry.help_used[0] if entry.help_used else None
        entry.save(update_fields=["legacy_help_used"])


class Migration(migrations.Migration):
    dependencies = [("lessons", "0011_journalentry_help_used")]
    operations = [
        migrations.RenameField(model_name="journalentry", old_name="help_used", new_name="legacy_help_used"),
        migrations.AddField(
            model_name="journalentry", name="help_used",
            field=models.JSONField(blank=True, default=list, validators=[lessons.models.validate_journal_help]),
        ),
        migrations.RunPython(copy_help, restore_help),
        migrations.RemoveField(model_name="journalentry", name="legacy_help_used"),
    ]
