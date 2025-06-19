import re
from typing import Any, List, Dict
from langgraph.graph.graph import CompiledGraph
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from app.models import DraftForm, FormField

def get_pdf_agent_system_prompt() -> str:
    """
    Returns the system prompt for a general-purpose PDF agent.
    """
    return """You are PDF Agent, a helpful assistant that analyzes text extracted from PDF documents.
    
When users upload PDFs, our system extracts the text content and presents it to you. Your job is to help users understand and utilize this content.

RESPONSE FORMAT:
When working with PDF content, you MUST format your response like this:

<answer>
Your brief explanation about the content extracted from the PDF document.
</answer>

<content>
The structured information from the document, presented clearly.
</content>

IMPORTANT RULES:
1. Present information clearly and concisely
2. If the content includes tables, maintain their structure in your response
3. Do not speculate beyond what is provided in the text
4. When uncertain about text, indicate this with [?]
5. Focus on providing accurate information without excessive analysis

Example response for tabular data:
<answer>
Here is the table content extracted from the PDF:
</answer>

<content>
| Quarter | Revenue | Growth |
|---------|---------|--------|
| Q1 2025 | $2.4M   | 5.2%   |
| Q2 2025 | $2.6M   | 8.3%   |
| Q3 2025 | $2.7M   | 3.8%   |
</content>

Example response for text content:
<answer>
Here is the key information extracted from the PDF:
</answer>

<content>
Document Title: Annual Financial Report
Date: March 15, 2025
Key Points:
1. Total revenue increased by 12% compared to previous year
2. Operating expenses reduced by 3.5% 
3. New market expansion planned for Q3 2025
</content>
"""

def extract_pdf_content(pdf_content):
    """
    Basic organization of text extracted from PDF documents.
    Returns a dictionary with simple categorization of the content.
    """
    if not pdf_content:
        print("警告: extract_pdf_content 收到空内容")
        return {}
        
    # 初始化sections字典
    sections = {}
    
    # 1. 检查是否包含表格格式
    if pdf_content.count('|') > 3:
        sections["Table"] = pdf_content.strip()
        print("检测到表格结构内容")
    
    # 2. 基于标题划分内容
    lines = pdf_content.split('\n')
    
    # 判断是否包含Markdown标题或文档标题格式
    has_headers = any(re.match(r'^#+\s+', line) for line in lines)
    
    if has_headers:
        # 按Markdown标题分段处理
        current_section = "Main"
        section_content = []
        
        for line in lines:
            if re.match(r'^#+\s+', line):  # Markdown 标题
                # 保存之前的部分
                if section_content:
                    content = '\n'.join(section_content)
                    if content.strip():
                        sections[current_section] = content
                
                # 新部分
                current_section = re.sub(r'^#+\s+', '', line).strip()
                section_content = []
            else:
                section_content.append(line)
        
        # 保存最后一个部分
        if current_section and section_content:
            content = '\n'.join(section_content)
            if content.strip():
                sections[current_section] = content
    else:
        # 尝试识别可能的章节标题（全大写或数字开头的行）
        current_section = "Content"
        section_content = []
        
        for line in lines:
            # 检测可能的章节标题
            if (re.match(r'^\d+\.[\s\t]+[A-Z]', line) or  # 数字编号开头
                (line.strip().isupper() and len(line.strip()) > 3 and len(line.strip().split()) <= 5)):  # 短的全大写行
                
                # 保存之前的部分
                if section_content:
                    content = '\n'.join(section_content)
                    if content.strip():
                        sections[current_section] = content
                
                # 新部分
                current_section = line.strip()
                section_content = []
            else:
                section_content.append(line)
        
        # 保存最后一个部分
        if current_section and section_content:
            content = '\n'.join(section_content)
            if content.strip():
                sections[current_section] = content
    
    # 如果未检测到任何部分，使用整体内容
    if not sections:
        sections["Document Content"] = pdf_content.strip()
    
    print(f"extract_pdf_content 从PDF内容中提取了 {len(sections)} 个部分")
    return sections

async def feedback_on_pdf_upload(agent_graph, messages, draft_form):
    """
    Provide feedback when a user uploads a PDF document
    """
    # Create a specialized system message
    system_message = SystemMessage(content=get_pdf_agent_system_prompt())

    # Add the system message to start
    new_messages = [system_message]
      # Extract PDF content from draft form
    pdf_content = ""
    for field in draft_form.fields:
        if field.type == "markdown":
            pdf_content = field.value
            break
    
    # Create the welcome message
    pdf_sections = extract_pdf_content(pdf_content)
    section_count = len(pdf_sections)
    
    # 检测是否存在表格
    has_table = any("Table" in key for key in pdf_sections.keys())
    
    # 评估文本长度
    total_text_length = sum(len(pdf_sections[section]) for section in pdf_sections)
    
    welcome_message = f"""我已处理您上传的PDF文档。

PDF内容提取结果:
- 识别内容部分: {section_count}个
- 总字符数: {total_text_length}
{f'- 包含表格数据' if has_table else ''}

您可以要求我:
1. 提取文档中的关键信息
2. 整理表格数据 {f"(已检测到表格)" if has_table else "(如果存在)"}
3. 总结文档内容

您想了解这份PDF文档中的哪些内容？"""

    # Add the welcome message
    new_messages.append(AIMessage(content=welcome_message))
    
    return new_messages
