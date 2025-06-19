import re
from typing import Any, List, Dict
from langgraph.graph.graph import CompiledGraph
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from app.models import DraftForm, FormField

def get_ocr_agent_system_prompt() -> str:
    """
    Returns the system prompt for a general-purpose OCR agent that processes text extracted from images.
    """
    return """You are OCR Agent, a helpful assistant that analyzes text extracted from images using OCR technology.
    
When users upload images, our system performs OCR to extract text visible in those images and presents it to you. Your job is to help users understand and utilize this text data.

RESPONSE FORMAT:
When working with OCR data, you MUST format your response like this:

<answer>
Your brief explanation about the text content extracted from the image.
</answer>

<content>
The structured information from the image, presented clearly.
</content>

IMPORTANT RULES:
1. Present information clearly and concisely
2. If the content appears to be a table, maintain its structure in your response
3. Do not speculate beyond what is provided in the OCR text
4. Fix obvious OCR errors when possible
5. When uncertain about text, indicate this with [?]

Example response for tabular data:
<answer>
Here is the table content extracted from the image:
</answer>

<content>
| Product | Quantity | Price |
|---------|----------|-------|
| Apple   | 5        | $2.50 |
| Banana  | 3        | $1.50 |
| Orange  | 4        | $2.00 |
</content>

Example response for text content:
<answer>
Here is the text content extracted from the image:
</answer>

<content>
Meeting Agenda:
1. Project Status Update
2. Budget Review
3. Timeline Discussion
4. Next Steps
</content>
"""

def extract_ocr_content(ocr_content):
    """
    Basic organization of text extracted from images via OCR.
    Returns a dictionary with simple categorization of the content.
    """
    if not ocr_content:
        print("警告: extract_ocr_content 收到空内容")
        return {}
        
    # 初始化sections字典
    sections = {}
    
    # 1. 检查是否包含表格格式
    if ocr_content.count('|') > 3:
        sections["Table"] = ocr_content.strip()
        print("检测到表格结构内容")
    
    # 2. 基于段落和结构划分内容
    lines = ocr_content.split('\n')
    
    # 判断是否包含Markdown标题
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
        # 简单区分段落
        paragraphs = []
        current_para = []
        
        for line in lines:
            if not line.strip() and current_para:
                paragraphs.append('\n'.join(current_para))
                current_para = []
            elif line.strip():
                current_para.append(line)
        
        # 添加最后一个段落
        if current_para:
            paragraphs.append('\n'.join(current_para))
        
        # 根据段落数量进行处理
        if len(paragraphs) <= 3:
            # 段落较少，直接作为内容存储
            sections["Content"] = ocr_content.strip()
        else:
            # 段落较多，进行分段
            for i, para in enumerate(paragraphs):
                sections[f"Paragraph {i+1}"] = para
    
    # 如果未检测到任何部分，使用整体内容
    if not sections:
        sections["Text Content"] = ocr_content.strip()
    
    print(f"extract_ocr_content 从OCR内容中提取了 {len(sections)} 个部分")
    return sections

async def feedback_on_ocr_upload(agent_graph, messages, draft_form):
    """
    Provide feedback when a user uploads an image for OCR text extraction
    """
    # Create a specialized system message
    system_message = SystemMessage(content=get_ocr_agent_system_prompt())

    # Add the system message to start
    new_messages = [system_message]
      # Extract OCR content from draft form
    ocr_content = ""
    for field in draft_form.fields:
        if field.type == "markdown":
            ocr_content = field.value
            break
    
    # Create the welcome message
    ocr_sections = extract_ocr_content(ocr_content)
    section_count = len(ocr_sections)
    
    # 检测是否存在表格
    has_table = any("Table" in key for key in ocr_sections.keys())
    
    # 评估文本长度
    total_text_length = sum(len(ocr_sections[section]) for section in ocr_sections)
    
    welcome_message = f"""我已从上传的图片中提取了文本。

OCR提取结果概要:
- 提取内容部分: {section_count}个
- 总字符数: {total_text_length}
{f'- 包含表格数据' if has_table else ''}

您可以要求我:
1. 提取文本中的关键信息
2. 整理表格数据 (如果存在)
3. 总结文本内容

您想了解这些OCR文本的什么内容？"""

    # Add the welcome message
    new_messages.append(AIMessage(content=welcome_message))
    
    return new_messages
