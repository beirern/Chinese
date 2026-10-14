from django import forms

from .models import JournalEntry


class JournalEntryForm(forms.ModelForm):
    help_used = forms.MultipleChoiceField(
        choices=JournalEntry.HelpUsed.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Help used",
        help_text="Select any tools you used, or leave both unchecked.",
    )

    class Meta:
        model = JournalEntry
        fields = ("title", "written_on", "text", "english_note", "help_used")
        widgets = {
            "written_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "text": forms.Textarea(attrs={"rows": 12, "lang": "zh-Hant"}),
            "english_note": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {"english_note": "Optional: describe your intended meaning in English."}
