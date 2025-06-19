from typing import Any, Dict, List
import os
import json
from langchain_core.prompts import ChatPromptTemplate
from datetime import datetime
from app.models import SupportDoc, FormField, DraftForm
from app.utils.llm import get_llm

def doc_data_to_string(doc_data: Dict) -> str:
    """
    Convert a document data dictionary to a string

    Returns:
        A string of the form:
        <reference_start>
           Document ID: {doc_data['docId']}
           Content: {doc_data['content']}
        <reference_end>
    """
    return f"""
    <reference>
        <document_id>
            {doc_data['docId']}
        </document_id>
        <content>
            {doc_data['content']}
        </content>
    </reference>
    """

def parse_llm_response(response):
    """
    Parse the LLM response into a dictionary.
    """
    # Remove markdown code blocks if present
    content = response.strip()
    
    # Remove ```json and ``` markers
    if content.startswith('```json'):
        content = content[7:]  # Remove ```json
    elif content.startswith('```'):
        content = content[3:]   # Remove ```
    
    if content.endswith('```'):
        content = content[:-3]  # Remove closing ```
    
    content = content.strip()
    
    try:
        data = json.loads(content)
        # Ensure required keys exist with defaults
        return {
            "value": data.get("value", ""),
            "docId": data.get("docId")
        }
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}")

async def text_field_processor(field: FormField, context: str) -> FormField:
    """
    Uses an LLM to find the answer to the field using the context data. If the context data is not enough for filling the field, leave the field empty.
    """
    llm = get_llm("PREFILL_LLM")

    SYSTEM_PROMPT = """
        Your task is to find the answers for fields in a form.
        You are given the following context to answer the fields:

        <context>
            {context}
        </context>

        Respond with valid JSON only.

        Example of correct response:
        {{"value": <field_value>, "docId": <document_id>}}

        You can only use the context to answer the fields. 
        If the context is not enough to answer, you can only return an empty value:
        {{"value": "", "docId": null}}
    """
    prompt = ChatPromptTemplate([
        ("system", SYSTEM_PROMPT),
        ("user", """Please answer the following field:
            <field>
                <label>
                    {field[label]}
                </label>
                <description>
                    {field[description]}
                </description>
                <type>
                    {field[type]}
                </type>
            </field>
            If you don't know the answer, please return an empty value.
            """
        )
    ])
    messages = prompt.format_messages(field=field, context=context)

    response = await llm.ainvoke(messages)
    output_field = field.copy()
    parsed_response = parse_llm_response(response.content)
    output_field["value"] = parsed_response["value"]
    output_field["docId"] = parsed_response["docId"]
    output_field["lastProcessed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return output_field


def format_pdf_value(value: Any, field_type: str, options: List[str] = None) -> Any:
    """
    Format a value according to PDF requirements.
    """
    if field_type == "checkbox_group":
        # For checkboxes, ensure we have a list of "/Yes" or "/Off" values
        if isinstance(value, list):
            return [str(v) if v in ["/Yes", "/Off"] else "/Off" for v in value]
        return ["/Off"]
    elif field_type == "dropdown" or field_type == "list_box":
        # For dropdowns and list boxes, ensure the value is in the options list
        if options and value not in options:
            return options[0] if field_type == "dropdown" else []
        return value
    else:
        # For text fields, convert to string
        return str(value) if value is not None else ""


async def checkbox_field_processor(field: FormField, context: str) -> FormField:
    """
    Process a checkbox field using the LLM.
    """
    # TODO: Test implementation
    try:
        # Extract information from context
        prompt = f"""Determine if the {field['label']} should be checked based on the following context.
        Return a list of "/Yes" or "/Off" values for each checkbox in the group.
        Context: {context}"""
        
        response = await get_llm().ainvoke(prompt)
        value = response.content.strip()
        
        # Parse the response into a list of values
        values = [v.strip() for v in value.split(",")]
        values = [v if v in ["/Yes", "/Off"] else "/Off" for v in values]
        
        return {
            "label": field["label"],
            "type": field["type"],
            "value": format_pdf_value(values, field["type"]),
            "options": field.get("options", [])
        }
    except Exception as e:
        return {
            "label": field["label"],
            "type": field["type"],
            "value": ["/Off"] * len(field.get("options", [])),
            "options": field.get("options", [])
        }


async def dropdown_field_processor(field: FormField, context: str) -> FormField:
    """
    Process a dropdown field using the LLM.
    """
    # TODO: Test implementation
    try:
        # Extract information from context
        prompt = f"""Select the most appropriate option for {field['label']} from the following options: {field['options']}
        Based on the context: {context}
        Return only the selected option."""
        
        response = await get_llm().ainvoke(prompt)
        value = response.content.strip()
        
        # Validate the response is in the options list
        if value not in field["options"]:
            value = field["options"][0]
        
        return {
            "label": field["label"],
            "type": field["type"],
            "value": format_pdf_value(value, field["type"], field["options"]),
            "options": field["options"]
        }
    except Exception as e:
        return {
            "label": field["label"],
            "type": field["type"],
            "value": field["options"][0] if field["options"] else "",
            "options": field["options"]
        }


async def list_box_field_processor(field: FormField, context: str) -> FormField:
    """
    Process a list box field using the LLM.
    """
    # TODO: Test implementation
    try:
        # Extract information from context
        prompt = f"""Select all applicable options for {field['label']} from the following options: {field['options']}
        Based on the context: {context}
        Return a comma-separated list of selected options."""
        
        response = await get_llm().ainvoke(prompt)
        values = [v.strip() for v in response.content.split(",")]
        
        # Filter out invalid selections
        values = [v for v in values if v in field["options"]]
        
        return {
            "label": field["label"],
            "type": field["type"],
            "value": format_pdf_value(values, field["type"], field["options"]),
            "options": field["options"]
        }
    except Exception as e:
        return {
            "label": field["label"],
            "type": field["type"],
            "value": [],
            "options": field["options"]
        }


async def prefill_in_memory_form(draft_form: DraftForm, docs_data: List[SupportDoc]) -> DraftForm:
    """
    Loops through all form fields and calls the corresponding field processor for each field.

    Args:
        draft_form: The form data to prefill
        docs_data: The supporting documents to use for context

    Returns:
        A dictionary with the updated form data
    """
    form_fields = draft_form["fields"]
    output_form = draft_form.copy()
    output_fields = []
    # supporting documents
    context = "\n".join([doc_data_to_string(doc) for doc in docs_data])

    for field in form_fields:
        output_field = field.copy()  # Always start with a copy

        try:
            if field["type"] == "text":
                output_field = await text_field_processor(field, context)
            elif field["type"] == "checkbox":
                # output_field = checkbox_field_processor(field, context)
                pass
            elif field["type"] == "dropdown":
                # output_field = dropdown_field_processor(field, context)
                pass
            else:
                raise ValueError(f"Unsupported field type: {field['type']}")
        except Exception as e:
            output_field["lastProcessed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output_field["error"] = str(e)

        output_fields.append(output_field)

    output_form["fields"] = output_fields
    return output_form
