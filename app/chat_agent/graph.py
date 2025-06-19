from typing import List, Annotated
import operator
import streamlit as st
import asyncio
from typing import Dict, Any, List
from dataclasses import dataclass
from langgraph.graph import StateGraph, END
from langchain_core.messages.base import BaseMessage
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
import json
from app.utils.llm import get_llm
from langgraph.prebuilt import ToolNode
from app.models import DraftForm
from app.form.inquire import field_surveyor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser

@dataclass
class ChatAgentState:
    messages: Annotated[List[BaseMessage], operator.add]
    form_filepath: str = None
    draft_form: DraftForm = None
    next: str = None  # For storing supervisor routing decisions

llm = None

async def workflow_guide_node(state: ChatAgentState) -> Dict[str, Any]:
    SYSTEM_PROMPT = """
    You are a friendly and cheerful assistant. 
    You will guide the user through the following workflow:

    1. User uploads the form that needs to be completed
    2. User uploads any support documents relevant to the form.
    3. User fills out any empty fields in the form with the help of the FormInquirer.
    /no_think
    """
    prompt = ChatPromptTemplate([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),   
    ])
    messages = prompt.format_messages(messages=state.messages)
    response = await llm.ainvoke(messages)
    return {"messages" : [response]}


async def form_assistant_node(state: ChatAgentState) -> Dict[str, Any]:
    # 检查是否是Excel表单
    excel_content = ""
    if state.draft_form:
        for field in state.draft_form.fields:
            if field.type == "markdown":
                excel_content = field.value
                break
    
    # 如果是Excel表单，使用专门的Excel系统提示
    if excel_content:
        from app.chat_agent.excel_helpers import get_excel_agent_system_prompt
        SYSTEM_PROMPT = get_excel_agent_system_prompt()
        
        # 创建包含最新表格数据的提示
        prompt = ChatPromptTemplate([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
            ("system", """
Remember to always work with the most current data when responding:
    
<current_excel_data>
{excel_content}
</current_excel_data>

Ensure your response maintains ALL rows from the data above unless explicitly asked to delete.
"""),
        ])
        
        messages = prompt.format_messages(
            messages=state.messages,
            excel_content=excel_content
        )
    else:
        # 非Excel表单使用原始提示
        SYSTEM_PROMPT = """
        You are a friendly and cheerful assistant. 
        You help the user by answering any questions they might have about the form.
        The form is as follows:
        <form>
            {draft_form}
        </form>
        /no_think
        """
        prompt = ChatPromptTemplate([
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="messages"),   
        ])
        messages = prompt.format_messages(messages=state.messages, draft_form=state.draft_form)
    
    response = await llm.ainvoke(messages)
    return {"messages" : [response]}


async def form_inquirer_node(state: ChatAgentState) -> Dict[str, Any]:
    draft_form = state.draft_form
    messages = state.messages
    unanswered_fields = []

    for field in draft_form.fields:
        # TODO: Extend this to support other field types
        if field.value == "" and field.type == "text":
            unanswered_fields.append(field)

    if len(unanswered_fields) > 0:
        unanswered_field = unanswered_fields[0]
        question = await field_surveyor(draft_form.fields, unanswered_field)
        return {"messages" : [AIMessage(content=f"[fields left: {len(unanswered_fields)}] {question}")]}
    else:
        return {"messages" : [AIMessage(content="All fields have been answered. Feel free to download the form. Thank you for using Form Agent!")]}


async def supervisor_node(state: ChatAgentState) -> Dict[str, Any]:
    """Wrapper node for the supervisor to handle state properly"""
    global llm
    """An LLM-based router."""
    
    members = ["WorkflowGuide", "FormAssistant", "FormInquirer"]
    members_descriptions = """
    WorkflowGuide explains the workflow to the user.
    FormAssistant tells the user information about the form.
    FormInquirer asks the user a question related to one of the empty form fields.
    """

    SYSTEM_PROMPT = """
    You are a supervisor responsible for helping a user fill out a form. 
    /no_think
    """
    function_def = {
        "name": "route",
        "description": "Select the next role.",
        "parameters": {
            "title": "routeSchema",
            "type": "object",
            "properties": {
                "next": {
                    "title": "Next",
                    "anyOf": [
                        {"enum": members},
                    ],
                },
            },
            "required": ["next"],
        },
    }
    prompt = ChatPromptTemplate([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        ("system", "Based on this conversation, you must decide which of the following workers needs to act next. {members_descriptions} Select one of: {members}."),
    ])
    messages = prompt.format_messages(messages=state.messages, members=members, members_descriptions=members_descriptions)
    
    llm.bind_functions(functions=[function_def], function_call="route")
    response = await llm.ainvoke(messages)
    return {"next": response.content}
    
# Create the graph
def create_chat_graph():
    global llm
    llm = get_llm(type="CHAT_LLM", temperature=0.0)
    
    workflow = StateGraph(ChatAgentState)
    
    # Add nodes
    workflow.add_node("WorkflowGuide", workflow_guide_node)
    workflow.add_node("FormAssistant", form_assistant_node)
    workflow.add_node("FormInquirer", form_inquirer_node)
    workflow.add_node("Supervisor", supervisor_node)
    
    # Connect nodes
    workflow.add_conditional_edges(
        "Supervisor",
        lambda state: state.next,
        {
            "WorkflowGuide": "WorkflowGuide",
            "FormAssistant": "FormAssistant", 
            "FormInquirer": "FormInquirer"
        }
    )
    workflow.add_edge("WorkflowGuide", END)
    workflow.add_edge("FormAssistant", END)
    workflow.add_edge("FormInquirer", END)
    
    # Set entry point
    workflow.set_entry_point("Supervisor")    

    return workflow.compile()
