from typing import Dict, List, TypedDict, Annotated, Union
import os
from datetime import datetime
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage
from app.utils.llm import clean_llm_response, get_llm

general_system_message = """
    You are a helpful assistant that judges an answer provided to a field in a form. 
    You are given information about the form field, all the fields in the form and the answer provided by the user.
    You must:
    - Determine if the answer is realistic and reasonable.
    - Determine if the answer is consistent with the context of the form.
    - Determine if the answer is consistent with the other fields in the form.
    """

# Define the state schema
class AgentState(TypedDict):
    form_fields: List[Dict]
    unanswered_field: Dict
    answer: str
    valid: bool
    answered_field: Dict

# Factory function to create AgentState with system message
def create_agent_state(form_fields: List[Dict] = None, unanswered_field: Dict = None, answer: str = "") -> AgentState:
    return AgentState(form_fields=form_fields, unanswered_field=unanswered_field, answer=answer)

async def judge_answer(state: AgentState):
    """
    Given a form field, the goal is to judge the answer provided by the user.
    """
    form_fields = state["form_fields"]
    unanswered_field = state["unanswered_field"]
    answer = state["answer"]
    
    PROMPT = f"""
    {general_system_message}

    <form-fields>
        {form_fields}
    </form-fields>
    
    <unanswered-field>
        <label>{unanswered_field["label"]}</label>
        <description>{unanswered_field["description"]}</description>
        <type>{unanswered_field["type"]}</type>
    </unanswered-field>

    <user-answer>
        {answer}
    </user-answer>    Return a boolean value indicating if the answer is valid. /no_think
    """
    
    model = get_llm("ANSWER_JUDGE_LLM", temperature=0.0)
    response = await model.ainvoke(PROMPT)
    valid = clean_llm_response(response.content).lower() == "true"
    return {"valid": valid}

def add_answered_field(state: AgentState):
    """
    Add answered field to the state.
    """
    answered_field = state["unanswered_field"].copy()

    answered_field["lastSurveyed"] = datetime.now().isoformat()
    answered_field["valid"] = state["valid"]

    if state["valid"]:
        answered_field["value"] = state["answer"]
    else:
        answered_field["retries"] += 1
    
    return {"answered_field": answered_field}

# Build the graph
def build_graph() -> StateGraph:    
    # Create the workflow graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("judge_answer", judge_answer)
    workflow.add_node("add_answered_field", add_answered_field)

    workflow.set_entry_point("judge_answer")
    workflow.add_edge("judge_answer", "add_answered_field")
    workflow.add_edge("add_answered_field", END)

    return workflow.compile()
