import pandas as pd
import io
import os
from datetime import datetime
from app.models import DraftForm, FormField

def excel_to_markdown(excel_data):
    """
    Convert Excel file data to markdown format
    
    Args:
        excel_data: Excel file data in bytes
        
    Returns:
        str: Markdown representation of the Excel file
    """
    try:
        # Read Excel data
        excel_file = io.BytesIO(excel_data)
        
        # Get all sheet names - with error handling for openpyxl issues
        try:
            # Try first with default engine (openpyxl)
            xlsx = pd.ExcelFile(excel_file)
        except TypeError:
            # If that fails, try explicitly with openpyxl and data_only=True
            excel_file.seek(0)  # Reset file pointer
            xlsx = pd.ExcelFile(excel_file, engine="openpyxl", engine_kwargs={"data_only": True})
        except Exception as e:
            # If openpyxl fails completely, try with xlrd engine if possible
            excel_file.seek(0)  # Reset file pointer
            try:
                xlsx = pd.ExcelFile(excel_file, engine="xlrd")
            except:
                # Last resort - create a basic sheet with error message
                return "## Sheet: Error\n\n| Error |\n|-------|\n| Failed to read Excel file. File may be corrupted or in an unsupported format. |\n\n"
        
        sheet_names = xlsx.sheet_names
        markdown_content = ""
        
        # Process each sheet
        for sheet_name in sheet_names:
            try:
                # Try reading with same engine as ExcelFile
                df = pd.read_excel(excel_file, sheet_name=sheet_name, engine=xlsx.engine)
                
                # Add sheet name as header
                markdown_content += f"## Sheet: {sheet_name}\n\n"
                
                # Convert dataframe to markdown table
                markdown_table = df.to_markdown(index=False)
                markdown_content += markdown_table + "\n\n"
            except Exception as e:
                markdown_content += f"## Sheet: {sheet_name}\n\n| Error |\n|-------|\n| Failed to read sheet: {str(e)} |\n\n"
        
        return markdown_content
    
    except Exception as e:
        # Global error handler
        return f"## Error Reading Excel\n\n| Error |\n|-------|\n| {str(e)} |\n\n"

def markdown_to_excel(markdown_content):
    """
    Convert markdown format back to Excel file
    
    Args:
        markdown_content: Markdown representation of Excel data
        
    Returns:
        io.BytesIO: Excel file data as BytesIO object
    """
    # Initialize output Excel file
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    # Parse markdown content by sheets
    sheets = markdown_content.split('## Sheet: ')
    
    # Skip the first empty element if it exists
    sheets = [s for s in sheets if s.strip()]
    
    for sheet_content in sheets:
        # Extract sheet name and table content
        lines = sheet_content.strip().split('\n')
        sheet_name = lines[0].strip()
        
        # Find where the table starts (first line with |)
        table_start = 0
        for i, line in enumerate(lines[1:], 1):
            if '|' in line:
                table_start = i
                break
        
        # Extract table content
        table_content = '\n'.join(lines[table_start:])
        
        # Convert markdown table to dataframe
        try:            # 分析表格内容，确定表头和分隔行
            lines = table_content.strip().split('\n')
            if len(lines) < 2:  # 至少需要表头和一行数据
                raise ValueError("Table too small, missing header or data")
                
            # 如果是标准Markdown表格，第二行通常是分隔行（包含 ----- 或 :----: 等格式）
            is_markdown_table = False
            if len(lines) >= 3:
                second_line = lines[1]
                # 检查第二行是否是分隔符行（包含连字符和冒号，但没有字母数字字符）
                if ('---' in second_line or ':--' in second_line) and not any(c.isalnum() for c in second_line if c not in '|:-'):
                    is_markdown_table = True
            
            if is_markdown_table:
                # 使用正确的方法读取标准Markdown表格
                try:
                    # 尝试方法1：使用header=0指定第一行为表头
                    df = pd.read_table(
                        io.StringIO(table_content),
                        sep='|',
                        header=0,  # 指定第一行为表头
                        skiprows=[1],  # 只跳过分隔符行
                        skipinitialspace=True
                    ).iloc[:, 1:-1]  # 移除首尾空列
                    
                    # 检查是否成功读取了表头
                    if df.columns.tolist() == list(range(len(df.columns))):
                        # 如果表头还是默认的数字，尝试方法2
                        raise ValueError("Failed to read headers correctly")
                except:
                    # 尝试方法2：手动处理
                    # 分别提取表头行和数据行
                    header_row = lines[0].strip('|').split('|')
                    header_row = [h.strip() for h in header_row]
                    
                    # 提取数据行（跳过表头和分隔行）
                    data_lines = lines[2:]
                    data_content = '\n'.join(data_lines)
                    
                    # 读取数据部分
                    df_data = pd.read_table(
                        io.StringIO(data_content),
                        sep='|',
                        header=None,
                        skipinitialspace=True
                    ).iloc[:, 1:-1]  # 移除首尾空列
                    
                    # 设置正确的列名
                    if not df_data.empty and len(header_row) >= df_data.shape[1]:
                        # 确保列头与数据列数匹配
                        df_data.columns = header_row[1:len(df_data.columns)+1]
                        df = df_data
                    else:
                        # 如果标头与数据不匹配，需要进行调整
                        df = pd.read_table(
                            io.StringIO(table_content),
                            sep='|',
                            header=None,
                            skipinitialspace=True
                        ).iloc[:, 1:-1]
                        
                        # 使用第一行作为标题，并跳过第二行（分隔符）
                        if len(df) >= 2:
                            df.columns = df.iloc[0]
                            df = df.iloc[2:]  # 跳过标题行和分隔符行
                            df = df.reset_index(drop=True)  # 重置索引
            else:
                # 如果不是标准Markdown表格，尝试基本处理
                df = pd.read_table(
                    io.StringIO(table_content),
                    sep='|',
                    header=None,
                    skipinitialspace=True
                ).iloc[:, 1:-1]
                
                # 假设第一行是表头
                if not df.empty:
                    df.columns = df.iloc[0]
                    df = df.iloc[1:]
                    df = df.reset_index(drop=True)
                  # 确保DataFrame有正确的列名（不是默认的数值索引）
            if df.columns.dtype.kind == 'i':  # 如果列名是整数索引
                # 尝试从表格内容中提取正确的标题
                for line in lines:
                    if '|' in line and '-' not in line:  # 找到不是分隔符的行作为标题
                        header_candidates = [col.strip() for col in line.strip('|').split('|')]
                        if len(header_candidates) == len(df.columns):
                            df.columns = header_candidates
                            break
              # 确保数据类型正确（有时pandas会把所有列都当作字符串）
            for col in df.columns:
                # 尝试转换为数值型，使用新的推荐方法避免FutureWarning
                try:
                    # 尝试将列转换为数值，如果失败则保留原值
                    numeric_values = pd.to_numeric(df[col], errors='coerce')
                    # 只在成功转换的情况下更新列值
                    mask = ~pd.isna(numeric_values)
                    if mask.any():
                        df.loc[mask, col] = numeric_values[mask]
                except Exception:
                    pass
                    
            # 写入Excel文件
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        except Exception as e:
            print(f"Error converting sheet {sheet_name}: {str(e)}")
            # If there's an error, add an empty sheet
            pd.DataFrame().to_excel(writer, sheet_name=sheet_name, index=False)
    
    writer.close()
    output.seek(0)
    return output

def parse_excel_form(excel_data) -> DraftForm:
    """
    Parse an Excel file and return the data as a DraftForm structure
    
    Args:
        excel_data: Excel file content in bytes
        
    Returns:
        DraftForm: Structured representation of the Excel file
    """
    # Convert to markdown for analysis
    markdown_content = excel_to_markdown(excel_data)
    
    # Create a basic structure
    form_name = "excel_form_" + datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Create a field for the markdown content
    fields = [
        FormField(
            label="Excel Content",
            description="Excel sheet data in markdown format",
            type="markdown",
            docId=None,
            value=markdown_content,
            options=[],
            lastProcessed=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            lastSurveyed=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    ]
    
    # Create the draft form
    draft_form = DraftForm(
        formFileName=form_name,
        lastSaved=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        fields=fields
    )
    
    return draft_form

def fill_excel_form(markdown_content, original_filename="excel_form.xlsx"):
    """
    Generate an Excel file from markdown content
    
    Args:
        markdown_content: Markdown representation of Excel data
        original_filename: Original filename to use for the output Excel file
        
    Returns:
        tuple: Filename and Excel file as BytesIO object
    """
    # Convert markdown to Excel
    excel_data = markdown_to_excel(markdown_content)
    
    # Add timestamp to the filename for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{os.path.splitext(original_filename)[0]}_{timestamp}.xlsx"
    
    return filename, excel_data

def markdown_to_df(markdown_table):
    """
    将markdown表格转换为pandas DataFrame
    
    Args:
        markdown_table: markdown格式的表格文本
        
    Returns:
        pandas.DataFrame: 转换后的DataFrame
    """
    # 确保输入是包含表格的字符串
    if not markdown_table or '|' not in markdown_table:
        raise ValueError("输入文本不是有效的markdown表格格式")
        
    try:
        # 分析表格内容，确定表头和分隔行
        lines = markdown_table.strip().split('\n')
        if len(lines) < 2:  # 至少需要表头和一行数据
            raise ValueError("表格太小，缺少表头或数据")
            
        # 如果是标准Markdown表格，第二行通常是分隔行
        is_markdown_table = False
        if len(lines) >= 3:
            second_line = lines[1]
            # 检查第二行是否是分隔符行（包含连字符和冒号，但没有字母数字字符）
            if ('---' in second_line or ':--' in second_line) and not any(c.isalnum() for c in second_line if c not in '|:-'):
                is_markdown_table = True
        
        if is_markdown_table:
            try:
                # 尝试直接读取markdown表格
                df = pd.read_table(
                    io.StringIO(markdown_table),
                    sep='|',
                    header=0,
                    skiprows=[1],
                    skipinitialspace=True
                ).iloc[:, 1:-1]  # 移除首尾空列
                
                # 检查是否成功读取了表头
                if df.columns.tolist() == list(range(len(df.columns))):
                    # 如果表头还是默认的数字，尝试手动处理
                    raise ValueError("无法正确读取表头")
            except:
                # 手动处理表格
                # 提取表头行
                header_row = lines[0].strip('|').split('|')
                header_row = [h.strip() for h in header_row]
                
                # 提取数据行（跳过表头和分隔行）
                data_lines = lines[2:]
                data_content = '\n'.join(data_lines)
                
                # 读取数据部分
                df_data = pd.read_table(
                    io.StringIO(data_content),
                    sep='|',
                    header=None,
                    skipinitialspace=True
                ).iloc[:, 1:-1]  # 移除首尾空列
                
                # 设置正确的列名
                if not df_data.empty and len(header_row) >= df_data.shape[1]:
                    # 确保列头与数据列数匹配
                    df_data.columns = header_row[1:len(df_data.columns)+1]
                    df = df_data
                else:
                    raise ValueError(f"表头行({len(header_row)})与数据列数({df_data.shape[1]})不匹配")
        else:
            # 非标准markdown表格，尝试常规分隔读取
            df = pd.read_table(
                io.StringIO(markdown_table),
                sep='|',
                skipinitialspace=True
            ).iloc[:, 1:-1]  # 移除首尾空列
        
        # 转换数值类型
        for col in df.columns:
            # 尝试转换为数值类型，使用coerce模式并创建掩码
            numeric_mask = pd.to_numeric(df[col], errors='coerce').notnull()
            if numeric_mask.any():  # 如果有任何成功转换的值
                # 只对能成功转换为数值的单元格执行转换
                df.loc[numeric_mask, col] = pd.to_numeric(df.loc[numeric_mask, col])
        
        return df
    
    except Exception as e:
        # 如果转换失败，返回带错误信息的简单DataFrame
        error_df = pd.DataFrame({"Error": [f"无法解析Markdown表格: {str(e)}"]})
        return error_df
