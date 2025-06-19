import re
from typing import Any, List, Dict
from langgraph.graph.graph import CompiledGraph
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from app.chat_agent.graph import ChatAgentState
from app.models import DraftForm, FormField

def is_form_question(message: str) -> bool:
    """
    Check if the message is a question about a form field.
    The message should be of the form: [fields left: <number>] <question_text>
    """
    pattern = r'^\[fields left: \d+\].*\?$'
    return bool(re.match(pattern, message))

async def trigger_chat_agent_response(agent_graph: CompiledGraph, messages: List[BaseMessage], human_message: str, **kwargs: Any) -> str:
    """
    Trigger the chat agent to respond to a human message.
    """
    user_message = HumanMessage(content=human_message)
    # Append user message to the messages list
    messages.append(user_message)
    state = ChatAgentState(messages=messages, **kwargs)
    result = await agent_graph.ainvoke(state)
    return result

async def feedback_on_file_upload(agent_graph: CompiledGraph, messages: List[BaseMessage], draft_form: DraftForm) -> List[AIMessage]:
    """
    Provide the user with feedback on the file they uploaded.
    Guide the user to next steps.
    """
    result = await trigger_chat_agent_response(
            agent_graph,
            [],
            "How many empty fields are there in the form?", 
            draft_form=draft_form
        )
    # Get the last message from the result
    empty_fields_response = result["messages"][-1]
    next_steps_response = AIMessage(content="Do you have any supporting documents related to the form?\nIf so, now would be a good time to upload them. I'll do my best to prefill the form with the information from the supporting documents.")
    
    return [empty_fields_response, next_steps_response]

async def feedback_on_support_docs_update(agent_graph: CompiledGraph, fields_changes: Dict[str, List[FormField]]) -> List[AIMessage]:
    """
    Provide the user with feedback on the support docs they uploaded and any fields that were prefilled.
    Guide the user to next steps.
    """
    ack_response = AIMessage(content="Thank you for uploading a support document.")

    prefilled_fields_total = len(fields_changes["prefilled_fields"])
    empty_fields_total = len(fields_changes["empty_fields"])
    if prefilled_fields_total > 0:        
        prefilled_message = "PREFILLED FIELDS:\n\n"
        for field in fields_changes["prefilled_fields"]:
            prefilled_message += f"{field['label']} was assigned a value of \"{field['value']}\"\n\n"
        
        empty_message = f"EMPTY FIELDS:\n\n"
        for i, field in enumerate(fields_changes["empty_fields"]):
            if i == empty_fields_total - 1:
                empty_message += f"{field['label']}."
            else:
                empty_message += f"{field['label']}, "
        prefilled_fields_response = AIMessage(content=f"{prefilled_message}\n{empty_message}")
    else:
        prefilled_fields_response = AIMessage(content="I could not find any information in the support document to prefill the form.")

    next_steps_response = AIMessage(content="Do you have more support documents to upload or should we move on to filling out the form?")
    
    return [ack_response, prefilled_fields_response, next_steps_response]