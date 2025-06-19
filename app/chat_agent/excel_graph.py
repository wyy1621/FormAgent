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
from app.utils.llm import get_llm
from app.chat_agent.excel_helpers import get_excel_agent_system_prompt
from app.models import DraftForm

@dataclass
class ExcelAgentState:
    messages: Annotated[List[BaseMessage], operator.add]
    draft_form: DraftForm = None

def create_excel_chat_graph():
    """
    Create a graph for the Excel chat agent.
    """
    # Initialize LLM
    llm = get_llm("CHAT_LLM", temperature=0.0)
    
    # Define the graph
    graph = StateGraph(ExcelAgentState)
      # Define the Excel node
    async def excel_agent_node(state: ExcelAgentState) -> Dict[str, Any]:
        # 获取系统提示
        SYSTEM_PROMPT = get_excel_agent_system_prompt()
        
        # 获取最新的Excel表格数据
        excel_content = ""
        if state.draft_form:
            for field in state.draft_form.fields:
                if field.type == "markdown":
                    excel_content = field.value
                    break
        
        # 创建一个包含最新表格数据的系统消息
        latest_data_prompt = f"""
Remember to always work with the most current data when responding:
    
<current_excel_data>
{excel_content}
</current_excel_data>

Ensure your response maintains ALL rows from the data above unless explicitly asked to delete.
"""
        
        # 创建完整上下文
        context = []
        
        # 添加系统提示
        context.append(SystemMessage(content=SYSTEM_PROMPT))
        
        # 添加对话历史
        context.extend(state.messages)
        
        # 添加最新表格数据提示
        context.append(SystemMessage(content=latest_data_prompt))
        
        # 获取模型响应
        response = await llm.ainvoke(context)
        
        # Return the response
        return {"messages": [response]}
    
    # Add the node to the graph
    graph.add_node("excel_agent", excel_agent_node)
    
    # Set the entry point
    graph.set_entry_point("excel_agent")
    
    # Any message should trigger the excel agent
    graph.add_edge("excel_agent", END)
    
    # Compile the graph
    compiled_graph = graph.compile()
    
    return compiled_graph
