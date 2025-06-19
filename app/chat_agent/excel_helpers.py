import re
from typing import Any, List, Dict
from langgraph.graph.graph import CompiledGraph
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from app.models import DraftForm, FormField

def get_excel_agent_system_prompt() -> str:
    """
    Returns the system prompt for the Excel agent.
    """
    return """You are Excel Agent, a helpful assistant specialized in understanding and modifying Excel data.
    
When users share Excel data with you (presented in markdown format), your job is to help them analyze, modify, and enhance their data based on their requests.

CRITICAL RESPONSE FORMAT:
When making changes to Excel data, you MUST format your response like this:

<answer>
Your explanation of what changes you made to the Excel data and why. Be clear and concise.
</answer>

<form>
The complete updated Excel data in markdown format. Include ALL columns and rows, not just the modifications.
</form>

IMPORTANT RULES:
1. ALWAYS maintain the exact table structure (columns and rows).
2. Make requested changes precisely.
3. CRITICAL: Include EVERY SINGLE ROW from the original data in your response, even when sorting or filtering. Never delete any rows unless explicitly requested.
4. When sorting data, ensure the row count matches exactly with the original data.
5. Preserve Excel formatting in the markdown tables.
6. Maintain header rows exactly as they were in the original.
7. NEVER delete columns unless explicitly requested.
8. If calculating formulas, show the results directly (not the formula).
9. Always verify that your response contains the same number of rows as the original data.

Examples of valid responses:
1. Adding a row:
<answer>
I've added a new row for project "X123" with the requested details.
</answer>
<form>
## Sheet: Projects

| Project ID | Name        | Budget | Status    |
|:-----------|:------------|:-------|:----------|
| A101       | Website     | 5000   | Completed |
| B202       | Mobile App  | 12000  | In Progress |
| X123       | Analytics   | 8500   | Planning  |
</form>

2. Modifying values:
<answer>
I've updated the Budget for Mobile App from 12000 to 15000 as requested.
</answer>
<form>
## Sheet: Projects

| Project ID | Name        | Budget | Status    |
|:-----------|:------------|:-------|:----------|
| A101       | Website     | 5000   | Completed |
| B202       | Mobile App  | 15000  | In Progress |
</form>
"""

def extract_excel_sheet_content(markdown_content):
    """
    Parse the markdown content to extract Excel sheets.
    Returns a dictionary where keys are sheet names and values are the sheet content.
    """
    if not markdown_content:
        print("警告: extract_excel_sheet_content 收到空内容")
        return {}
        
    # 检查是否是直接的表格内容（没有Sheet标记但包含表格标记）
    if "## Sheet:" not in markdown_content and "|" in markdown_content:
        print("检测到直接的表格内容，创建默认Sheet")
        return {"Sheet1": markdown_content.strip()}
    
    sheets = {}
    current_sheet = None
    sheet_content = []
    
    lines = markdown_content.split('\n')
    for line in lines:
        if line.startswith('## Sheet:'):
            # If we already have a sheet, save it before moving to the next
            if current_sheet:
                content = '\n'.join(sheet_content)
                if content.strip():  # 只存储非空内容
                    sheets[current_sheet] = content
            
            # Start a new sheet
            current_sheet = line.replace('## Sheet:', '').strip()
            if not current_sheet:  # 如果没有名称，使用默认名称
                current_sheet = f"Sheet{len(sheets) + 1}"
            sheet_content = []
        elif current_sheet:
            sheet_content.append(line)
    
    # Don't forget to add the last sheet
    if current_sheet and sheet_content:
        content = '\n'.join(sheet_content)
        if content.strip():  # 只存储非空内容
            sheets[current_sheet] = content
    
    # 如果没有找到任何表格，但内容中有表格标记，创建默认表格
    if not sheets and "|" in markdown_content:
        print("未找到Sheet标记，但检测到表格内容，创建默认Sheet")
        sheets["Sheet1"] = markdown_content.strip()
    
    print(f"extract_excel_sheet_content 提取了 {len(sheets)} 个表格")
    return sheets

async def feedback_on_excel_upload(agent_graph, messages, draft_form):
    """
    Provide feedback when a user uploads an Excel file
    """
    # Create a specialized system message
    system_message = SystemMessage(content=get_excel_agent_system_prompt())

    # Add the system message to start
    new_messages = [system_message]
      # Extract Excel content from draft form
    excel_content = ""
    for field in draft_form.fields:
        if field.type == "markdown":
            excel_content = field.value
            break
    
    # Create the welcome message with data summary
    excel_sheets = extract_excel_sheet_content(excel_content)
    sheet_count = len(excel_sheets)
    sheet_names = list(excel_sheets.keys())
    
    welcome_message = f"""I've loaded your Excel file. Here's a summary:

- Number of sheets: {sheet_count}
- Sheet names: {', '.join(sheet_names)}

Your data is ready for analysis or modification. You can ask me to:

1. Analyze the data (find trends, calculate summaries, etc.)
2. Modify the data (add/edit/delete rows or columns)
3. Format or restructure the data
4. Perform calculations on the data

What would you like to do with this Excel data?"""

    # Add the welcome message
    new_messages.append(AIMessage(content=welcome_message))
    
    return new_messages
