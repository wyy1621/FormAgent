import re
from app.models import DraftForm

def extract_form_content(message: str) -> str:
    """
    Extract form content from a message that uses the <form></form> tags.
    """
    try:
        # 首先尝试提取<form>标签中的内容
        form_pattern = re.compile(r'<form>(.*?)</form>', re.DOTALL)
        match = form_pattern.search(message)
        if match:
            content = match.group(1).strip()
            print(f"从<form>标签中提取内容成功，长度: {len(content)}")
            return content
            
        # 如果没有<form>标签，尝试查找markdown表格格式
        if '|' in message and '---' in message:
            # 可能是直接的markdown表格，尝试提取
            lines = message.strip().split('\n')
            table_start = None
            for i, line in enumerate(lines):
                if '|' in line:
                    # 找到第一行包含'|'的行
                    table_start = i
                    break
                    
            if table_start is not None:
                # 找到了表格的开始，接下来确定结束位置
                table_end = len(lines)
                for i in range(table_start + 1, len(lines)):
                    if '|' not in lines[i] and i > table_start + 2:  # 确保至少包含表头和一行数据
                        table_end = i
                        break
                
                # 提取表格内容
                table_content = '\n'.join(lines[table_start:table_end])
                if '|' in table_content and len(table_content) > 10:  # 确保提取的确实是表格
                    print(f"从消息中直接提取表格成功，长度: {len(table_content)}")
                    return table_content
        
        return ""
    except Exception as e:
        print(f"提取表格内容时出错: {str(e)}")
        return ""

def extract_answer_content(message: str) -> str:
    """
    Extract the answer content from a message that uses the <answer></answer> tags.
    """
    answer_pattern = re.compile(r'<answer>(.*?)</answer>', re.DOTALL)
    match = answer_pattern.search(message)
    if match:
        return match.group(1).strip()
    return ""

def update_draft_form(draft_form: DraftForm, message: str) -> DraftForm:
    """
    Update the draft form with the Excel content in markdown format.
    For Excel files, we look for <form></form> tags in the message to
    extract the updated markdown content.
    """
    try:
        # 首先检查是否有表单内容可以提取
        form_content = extract_form_content(message)
        if not form_content or "|" not in form_content:
            print("警告: 未提取到有效的表格内容，表单不会被更新")
            return draft_form
            
        print(f"提取到表格内容，长度: {len(form_content)}")
        
        # 检查是否是Excel表单(有markdown字段)
        markdown_field_index = None
        for i, field in enumerate(draft_form.fields):
            if field.type == "markdown":
                markdown_field_index = i
                break
                
        if markdown_field_index is None:
            print("错误: 表单中没有markdown字段，无法更新Excel内容")
            return draft_form
        
        # 获取原始内容并进行验证
        original_content = draft_form.fields[markdown_field_index].value
        if original_content:
            # 验证表格行数是否减少（仅用于排序等不应删除行的操作）
            original_rows = sum(1 for line in original_content.strip().split("\n") if "|" in line)
            new_rows = sum(1 for line in form_content.strip().split("\n") if "|" in line)
            
            # 打印行数比较
            print(f"原始表格行数: {original_rows}, 更新后表格行数: {new_rows}")
            
            if new_rows < original_rows:
                print("警告：更新后的表格行数少于原始表格，可能有数据丢失！")
            
        # 更新表单字段
        draft_form.fields[markdown_field_index].value = form_content
        print(f"表单已更新，新内容长度: {len(form_content)}")
        
        return draft_form
        
    except Exception as e:
        print(f"更新表单时发生错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return draft_form  # 出错时返回原始表单
            
    # If no markdown field is found, use the original behavior for other form types
    if not any(field.type == "markdown" for field in draft_form.fields):
        for i, field in enumerate(draft_form.fields):
            # Check for the first unanswered field
            if field.value == "" and field.type == "text":
                draft_form.fields[i].value = message
                break
                
    return draft_form
