from typing import Dict, List
from app.models import DraftForm, FormField

def get_prefilled_fields_status(previous_form: DraftForm, current_form: DraftForm) -> Dict[str, List[FormField]]:
    """
    Compare the previous and current form fields.

    Returns a dictionary with the following keys:
    - prefilled_fields: List[FormField]
    - empty_fields: List[FormField]
    """
    prefilled_fields = []
    empty_fields = []

    for i, field in enumerate(previous_form.fields):
        # TODO: Extend this to support other field types
        if field.value == "" and field.type == "text":
            if (previous_form.fields[i].value == current_form.fields[i].value):
                empty_fields.append(field)
            else:
                prefilled_fields.append(current_form.fields[i])
    return {
        "prefilled_fields": prefilled_fields,
        "empty_fields": empty_fields
    }

def check_if_form_complete(draft_form: DraftForm) -> bool:
    """
    Check if the form is complete.
    """
    for field in draft_form.fields:
        if field.value == "":
            return False
    return True