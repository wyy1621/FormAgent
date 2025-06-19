from typing import Dict, List, TypedDict, Annotated, Union
import os
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage
from app.utils.llm import clean_llm_response, get_llm
from app.models import FormField

async def field_surveyor(form_fields: List[FormField], unanswered_field: FormField) -> str:
    """
    Given a form field, the goal is to come up with a question that will solicit the information needed to answer the field.
    """
    if unanswered_field.type == "text":
        return await text_field_surveyor(form_fields, unanswered_field)
    elif unanswered_field.type == "checkbox_group":
        return checkbox_field_surveyor(form_fields, unanswered_field)
    elif unanswered_field.type == "dropdown":
        return dropdown_field_surveyor(form_fields, unanswered_field)
    else:
        raise ValueError(f"Unsupported field type: {unanswered_field.type}")

async def text_field_surveyor(form_fields: List[FormField], unanswered_field: FormField) -> str:
    """
    Given a text field, the goal is to come up with a question that will solicit the information needed to answer the field.
    """
    PROMPT = f"""
    You are a friendly and helpful assistant that wants to help a user answer a field in a form. 
    You are given information about the form field and your goal is to come up with a question that will solicit the information needed to answer the field.

    As context, take into account all the fields in the form and the user's previous answers:
    <form>
        {form_fields}
    </form>
    
    The field that the user needs to answer is:
    <field>
        <label>{unanswered_field.label}</label>
        <description>{unanswered_field.description}</description>
        <type>{unanswered_field.type}</type>
    </field>    Ask a polite and clear question that will help the user answer the field. /no_think
    """
    
    model = get_llm("QUESTIONS_LLM", temperature=0.0)
    response = await model.ainvoke(PROMPT)
    question = clean_llm_response(response.content)
    return question

def checkbox_field_surveyor(form_fields: List[FormField], unanswered_field: FormField) -> str:
    """
    Given a checkbox field, the goal is to come up with a question that will solicit the information needed to answer the field.
    """
    # TODO: Implement checkbox field surveyor
    return "What is the checkbox field's answer?"

def dropdown_field_surveyor(form_fields: List[FormField], unanswered_field: FormField) -> str:
    """
    Given a dropdown field, the goal is to come up with a question that will solicit the information needed to answer the field.
    """
    # TODO: Implement dropdown field surveyor
    return "What is the dropdown field's answer?"