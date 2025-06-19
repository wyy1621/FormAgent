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
from app.chat_agent.ocr_helpers import get_ocr_agent_system_prompt
from app.models import DraftForm

@dataclass
class OcrAgentState:
    messages: Annotated[List[BaseMessage], operator.add]
    draft_form: DraftForm = None

def create_ocr_chat_graph():
    """
    Create a graph for the OCR chat agent.
    """
    # Initialize LLM
    llm = get_llm("CHAT_LLM", temperature=0.0)
    
    # Define the graph
    graph = StateGraph(OcrAgentState)
      # Define the OCR node
    async def ocr_agent_node(state: OcrAgentState) -> Dict[str, Any]:
        # 获取系统提示
        SYSTEM_PROMPT = get_ocr_agent_system_prompt()
          # 获取最新的图片OCR识别数据
        ocr_content = ""
        image_metadata = {}
        
        if state.draft_form:
            for field in state.draft_form.fields:
                if field.type == "markdown":
                    ocr_content = field.value
                    break
                elif field.type == "image_metadata" and field.value:
                    # 处理可能存在的图片元数据
                    try:
                        image_metadata = field.value
                    except:
                        print("无法解析图片元数据")
        
        # 尝试从元数据中提取有用信息
        img_width = image_metadata.get('width', 'unknown')
        img_height = image_metadata.get('height', 'unknown')
        img_format = image_metadata.get('format', 'unknown')
        img_source = image_metadata.get('source', 'uploaded image')
          # 创建一个包含OCR数据的简洁系统消息
        latest_data_prompt = f"""
Below is the text extracted from an image using OCR technology:

<ocr_content>
{ocr_content}
</ocr_content>

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
        
        # 添加最新OCR数据提示
        context.append(SystemMessage(content=latest_data_prompt))
        
        # 获取模型响应
        response = await llm.ainvoke(context)
        
        # Return the response
        return {"messages": [response]}
    
    # Add the node to the graph
    graph.add_node("ocr_agent", ocr_agent_node)
    
    # Set the entry point
    graph.set_entry_point("ocr_agent")
    
    # Any message should trigger the OCR agent
    graph.add_edge("ocr_agent", END)
    
    # Compile the graph
    compiled_graph = graph.compile()
    
    return compiled_graph
