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
from app.chat_agent.pdf_helpers import get_pdf_agent_system_prompt
from app.models import DraftForm

@dataclass
class PdfAgentState:
    messages: Annotated[List[BaseMessage], operator.add]
    draft_form: DraftForm = None

def create_pdf_chat_graph():
    """
    Create a graph for the PDF chat agent.
    """
    # Initialize LLM
    llm = get_llm("CHAT_LLM", temperature=0.0)
    
    # Define the graph
    graph = StateGraph(PdfAgentState)
      # Define the PDF node
    async def pdf_agent_node(state: PdfAgentState) -> Dict[str, Any]:
        # 获取系统提示
        SYSTEM_PROMPT = get_pdf_agent_system_prompt()
        
        # 获取最新的PDF内容数据
        pdf_content = ""
        if state.draft_form:
            for field in state.draft_form.fields:
                if field.type == "markdown":
                    pdf_content = field.value
                    break
          # 创建一个包含PDF内容的简洁系统消息
        latest_data_prompt = f"""
Below is the text content extracted from a PDF document:

<pdf_content>
{pdf_content}
</pdf_content>

Remember to:
1. Focus on presenting this content clearly
2. Maintain table structure if tables are present
3. Present information in the <content> section of your response
"""
        
        # 创建完整上下文
        context = []
        
        # 添加系统提示
        context.append(SystemMessage(content=SYSTEM_PROMPT))
        
        # 添加对话历史
        context.extend(state.messages)
        
        # 添加最新PDF数据提示
        context.append(SystemMessage(content=latest_data_prompt))
        
        # 获取模型响应
        response = await llm.ainvoke(context)
        
        # Return the response
        return {"messages": [response]}
    
    # Add the node to the graph
    graph.add_node("pdf_agent", pdf_agent_node)
    
    # Set the entry point
    graph.set_entry_point("pdf_agent")
    
    # Any message should trigger the PDF agent
    graph.add_edge("pdf_agent", END)
    
    # Compile the graph
    compiled_graph = graph.compile()
    
    return compiled_graph
