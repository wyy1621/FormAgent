import streamlit as st
import os
import sys
import asyncio
import nest_asyncio
from typing import List
from datetime import datetime
import json
import io
import copy

# 设置Streamlit不自动打开浏览器
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from app.chat_agent.graph import create_chat_graph, ChatAgentState
from app.chat_agent.helpers import is_form_question
from app.chat_agent.excel_helpers import feedback_on_excel_upload, get_excel_agent_system_prompt, extract_excel_sheet_content
from app.utils.setup import setup
from app.utils.llm import clean_llm_response
from app.doc_handlers.excel import parse_excel_form, fill_excel_form
from app.utils.misc import save_file_to_disk
from app.form.update import update_draft_form, extract_form_content, extract_answer_content
from app.form.status import check_if_form_complete
from app.doc_handlers.ocr import extract_text_from_image, can_convert_to_table, merge_tables

setup()

# Patches asyncio to allow nested event loops
nest_asyncio.apply()

DEFAULT_AI_GREETING = """
    Hello! 👋 I'm Form Agent, your spreadsheet assistant. Need help with Excel data? I'm here to assist. Please start by uploading an Excel file.
"""
FORMS_PATH = os.path.join(os.getcwd(), os.getenv("FORMS_PATH"))

# ---------- Streamlit Page Configuration ----------
st.set_page_config(page_title="Form Agent", layout="wide")

# Custom CSS to change button colors
st.markdown("""
<style>
.stFileUploader button:hover,
.stDownloadButton button:hover,
.stButton > button:hover,
.stFileUploader button:active,
.stDownloadButton button:active,
.stButton > button:active {
    border-color: #c9a912;
    color: #f4c707;
}
.stFileUploader button:focus,
.stDownloadButton button:focus,
.stButton > button:focus {
    border-color: #c9a912 !important;
    color: #f4c707 !important;
    outline: 2px solid #c9a912 !important;
}
.stChatInput > div:focus-within {
    border-color: #f4c707 !important;
}
</style>
""", unsafe_allow_html=True)

def reset_session_state():
    """Clear all session state variables"""
    # Reset all session state variables
    for key in list(st.session_state.keys()):
        del st.session_state[key]

# ---------- Initialize Session State ----------
if "main_form_path" not in st.session_state:
    st.session_state.main_form_path = None
if "form_type" not in st.session_state:
    st.session_state.form_type = None  # 'excel' only
if "original_filename" not in st.session_state:
    st.session_state.original_filename = None
if "draft_form" not in st.session_state:
    st.session_state.previous_draft_form = None
    st.session_state.draft_form = None
if "is_form_complete" not in st.session_state:
    st.session_state.is_form_complete = False
if 'chat_graph' not in st.session_state:
    st.session_state.chat_graph = create_chat_graph()
    st.session_state.messages = [
        SystemMessage(content="You are a friendly and helpful assistant responsible for helping a user modify Excel data."),
        AIMessage(content="Hello! 👋 I'm Excel Agent, your spreadsheet assistant. Need help with Excel data? I'm here to assist. Please start by uploading an Excel file.")]

# ---------- Sidebar: File Upload ----------
with st.sidebar:
    st.title("📊 文件上传")
    
    main_form = st.file_uploader(
        "上传Excel或PDF文件 (.xlsx 或 .xls 或 .pdf)",
        type=["xlsx", "xls", ".pdf"],
        key="main_form_uploader",
    )
    if main_form and not st.session_state.main_form_path:
        # Save original filename
        st.session_state.original_filename = main_form.name
        # Save the file to disk
        st.session_state.main_form_path = save_file_to_disk(main_form, FORMS_PATH)
        # Set form type to Excel
        st.session_state.form_type = "excel"
        # The initial draft form is just the parsed form
        st.session_state.draft_form = parse_excel_form(main_form.getvalue())
        st.session_state.previous_draft_form = copy.deepcopy(st.session_state.draft_form)
        
        # Use the specialized Excel feedback function
        feedback = asyncio.run(feedback_on_excel_upload(st.session_state.chat_graph, st.session_state.messages, st.session_state.draft_form))
        
        # Replace messages with the feedback (which includes system prompt)
        st.session_state.messages = feedback
        st.rerun()
    
    # 添加图片上传选项但不进行处理
    if st.session_state.draft_form:
        st.markdown("---")
        st.markdown("### 🖼️ 图片表格识别")
        st.markdown("在右侧聊天窗口底部可以上传图片进行表格识别与合并。")

# ---------- Main Section: Assistant Chat ----------
with st.container():
    col1, col2 = st.columns(2)
    with col1:
        st.title("📊 Form Agent", anchor=False)
    with col2:
        col_a, col_b, col_c = st.columns(3)
        with col_b:
            if st.session_state.draft_form:                # Get the markdown content from the form
                excel_markdown = ""
                for field in st.session_state.draft_form.fields:
                    if field.type == "markdown":
                        excel_markdown = field.value
                        break
                
                if excel_markdown:
                    download_filename, excel_bytes = fill_excel_form(excel_markdown, st.session_state.original_filename)
                    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    help_text = "Download the modified Excel file"
                else:
                    excel_bytes = None
                
                if excel_bytes:
                    st.markdown("<div style='text-align: right;'>", unsafe_allow_html=True)
                    st.download_button(
                        label="⬇️ &nbsp;Download File",
                        data=excel_bytes,
                        file_name=download_filename,
                        mime=mime_type,
                        help=help_text,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

        with col_c:
            st.markdown("<div style='text-align: right;'>", unsafe_allow_html=True)
            if st.button("🔄 &nbsp;Start Over"):
                reset_session_state()
                st.rerun()  
            st.markdown("</div>", unsafe_allow_html=True)

# Add Excel Table Preview Area when Excel file is uploaded
if st.session_state.draft_form:
    excel_markdown = ""
    for field in st.session_state.draft_form.fields:
        if field.type == "markdown":
            excel_markdown = field.value
            break
    
    if excel_markdown:
        st.header("📋 Data Preview")
        
        # 调试输出
        print(f"Excel markdown 内容长度: {len(excel_markdown)}")
        
        # 如果excel_markdown不包含"## Sheet:"前缀，可能是直接的表格内容
        if "## Sheet:" not in excel_markdown and "|" in excel_markdown:
            # 直接显示为单个表格
            st.markdown(excel_markdown)
        else:
            # Extract sheets from the markdown content
            sheets = extract_excel_sheet_content(excel_markdown)
            
            # 调试输出
            print(f"提取的表格数量: {len(sheets)}")
            
            # Create tabs for each sheet
            if len(sheets) > 0:
                tabs = st.tabs(list(sheets.keys()))
                # Display each sheet in its tab
                for i, (sheet_name, sheet_content) in enumerate(sheets.items()):
                    with tabs[i]:                        # 调试输出
                        print(f"表格 {sheet_name} 内容长度: {len(sheet_content)}")
                        
                        # 确保内容包含表格标记
                        if "|" in sheet_content:
                            try:
                                # 尝试渲染表格
                                st.markdown(sheet_content)
                            except Exception as render_err:
                                st.error(f"渲染表格出错: {str(render_err)}")
                                # 尝试显示原始内容
                                st.code(sheet_content)
                        else:
                            st.warning(f"表格 '{sheet_name}' 不包含任何表格内容")
                            st.code(sheet_content)
            else:
                # 没有找到表格，尝试直接显示内容
                if "|" in excel_markdown:
                    st.markdown("### 表格内容（无法识别表单格式，直接显示）")
                    st.markdown(excel_markdown)
                else:
                    st.error("无法解析Excel内容，请检查数据格式。")
        
        st.divider()

# Chat interface
chat_container = st.container(height=620)

# 初始化存储OCR处理结果的会话状态
if "ocr_result" not in st.session_state:
    st.session_state.ocr_result = None
if "ocr_table_preview" not in st.session_state:
    st.session_state.ocr_table_preview = None
if "ocr_processing" not in st.session_state:
    st.session_state.ocr_processing = False
if "ocr_can_convert" not in st.session_state:
    st.session_state.ocr_can_convert = False

# Display chat message history
with chat_container:
    for message in st.session_state.messages:
        if isinstance(message, SystemMessage) or isinstance(message, ToolMessage):
            continue
        elif isinstance(message, AIMessage) and not message.tool_calls:
            with st.chat_message("assistant"):
                content = clean_llm_response(message.content)
                
                # Check if this is an Excel response by looking for <answer> and <form> tags
                answer_content = extract_form_content(content)
                explanation_content = extract_answer_content(content)
                
                if answer_content and explanation_content:
                    # Display the explanation
                    st.write(explanation_content)
                    
                    # Display any tables in the form content using markdown
                    if "<table>" not in answer_content:  # Only if not already HTML
                        st.markdown(answer_content)
                else:
                    # Regular message, display as is
                    st.markdown(content)
        elif isinstance(message, HumanMessage):
            with st.chat_message("user"):
                st.markdown(message.content)
    
    # 显示OCR处理结果
    if st.session_state.ocr_processing:
        with st.chat_message("assistant"):
            with st.spinner("正在处理图片，请稍候..."):
                st.markdown("正在进行OCR识别和表格提取...")
    
    # 显示OCR预览和合并选项
    if st.session_state.ocr_table_preview:
        with st.chat_message("assistant"):
            if st.session_state.ocr_can_convert:
                st.success("✅ 成功从图片中提取表格！")
                st.markdown("### 提取的表格预览")
                st.markdown(st.session_state.ocr_table_preview)
                
                # 合并按钮
                if st.button("合并到当前Excel表格", key="merge_button"):
                    with st.spinner("正在合并表格..."):
                        try:
                            # 获取当前Excel表格的markdown内容
                            excel_markdown = ""
                            for field in st.session_state.draft_form.fields:
                                if field.type == "markdown":
                                    excel_markdown = field.value
                                    break
                            
                            if excel_markdown:
                                # 提取当前活跃的Sheet内容
                                sheets = extract_excel_sheet_content(excel_markdown)
                                first_sheet_name = list(sheets.keys())[0]  # 假设合并到第一个表格
                                first_sheet_content = sheets[first_sheet_name]
                                  # 合并表格 - 使用安全的异步调用方式
                                try:
                                    # 创建事件循环的隔离上下文
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    
                                    # 设置超时，避免长时间阻塞
                                    import contextlib
                                    with contextlib.suppress(asyncio.TimeoutError):
                                        try:
                                            # 调用大模型合并表格
                                            merged_table = loop.run_until_complete(
                                                asyncio.wait_for(merge_tables(first_sheet_content, st.session_state.ocr_table_preview), timeout=40)
                                            )
                                        finally:
                                            loop.close()
                                except Exception as e:
                                    st.error(f"合并表格时发生错误: {str(e)}")
                                    merged_table = first_sheet_content  # 失败时保持原表格不变                                # 检查合并表格是否有效
                                if merged_table and '|' in merged_table:
                                    try:
                                        # 检查是否需要添加Sheet标记
                                        if not merged_table.startswith("## Sheet:") and first_sheet_name:
                                            # 构建带有Sheet标记的内容
                                            updated_content = f"## Sheet: {first_sheet_name}\n\n{merged_table}"
                                        else:
                                            updated_content = merged_table
                                        
                                        # 直接更新表单的markdown字段值
                                        for field in st.session_state.draft_form.fields:
                                            if field.type == "markdown":
                                                field.value = updated_content
                                                print(f"已直接更新表单字段，新内容长度: {len(updated_content)}")
                                                break
                                        
                                        # 打印表单状态以供调试
                                        for field in st.session_state.draft_form.fields:
                                            if field.type == "markdown":
                                                print(f"表单字段类型: {field.type}, 内容长度: {len(field.value) if field.value else 0}")
                                                if "|" in field.value:
                                                    print("表单字段包含表格内容")
                                                else:
                                                    print("警告: 表单字段不包含表格内容")
                                                break
                                                
                                        st.success("表格已成功合并！请在上方Excel数据预览区查看结果。")
                                    except Exception as update_err:
                                        st.error(f"更新表格时出错: {str(update_err)}")
                                        import traceback
                                        print(f"更新表格错误详情: {traceback.format_exc()}")
                                else:
                                    st.error("无法生成有效的合并表格，原表格保持不变。")# 保存当前状态以备回滚
                                st.session_state.previous_draft_form = copy.deepcopy(st.session_state.draft_form)
                                
                                # 简单验证表格内容更新是否成功
                                for field in st.session_state.draft_form.fields:
                                    if field.type == "markdown":
                                        content_length = len(field.value) if field.value else 0
                                        if content_length < 10 or "|" not in field.value:
                                            st.error(f"表格内容更新后为空或无效 (长度: {content_length})")
                                            with st.expander("尝试恢复原始内容"):
                                                # 尝试恢复原始内容
                                                st.session_state.draft_form = copy.deepcopy(st.session_state.previous_draft_form)
                                                st.warning("已尝试恢复原始表格内容")
                                        break
                                
                                # 清除OCR处理状态
                                st.session_state.ocr_result = None
                                st.session_state.ocr_table_preview = None
                                st.session_state.ocr_processing = False
                                st.session_state.ocr_can_convert = False
                                
                                # 添加一条系统消息
                                system_message = AIMessage(content="我已将图片中的表格提取并与当前Excel表格合并，您可以在上方的Excel数据预览区查看结果。")
                                st.session_state.messages.append(system_message)
                                st.rerun()
                        except Exception as e:
                            st.error(f"合并表格时出错：{str(e)}")
            else:
                st.error("❌ 无法将OCR识别的内容转换为表格")
                st.markdown(f"**原因**: {st.session_state.ocr_reason}")
                with st.expander("查看提取的原始文本"):
                    st.text(st.session_state.ocr_result)

# 聊天输入区域和图片上传
if not st.session_state.is_form_complete and st.session_state.draft_form:
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_input = st.chat_input("输入您的问题或指令...")
        if user_input:
            # Add user message to session state
            user_message = HumanMessage(content=user_input)
            
            # Add user message to chat history
            st.session_state.messages.append(user_message)
            
            # Display user message in chat history immediately
            with chat_container:
                with st.chat_message("user"):
                    st.write(user_input)
            
            # 处理用户提示
            # For Excel processing, we don't consider forms as "complete" since users can 
            # continually modify the data. Instead, we always process the request.
            state = ChatAgentState(
                messages=st.session_state.messages, 
                draft_form=st.session_state.draft_form,
                form_filepath=st.session_state.main_form_path
            )
            
            # Process with the graph
            with st.chat_message("assistant"):
                with st.spinner("正在思考..."):
                    try:
                        # With nest_asyncio, this should work even in nested loops
                        result = asyncio.run(st.session_state.chat_graph.ainvoke(state))
                        
                        # Get the latest AI response
                        latest_message = result["messages"][-1]
                          # If this is an Excel form and we got a form update from the AI
                        if st.session_state.form_type == "excel" and isinstance(latest_message, AIMessage):
                            # Check if the AI's response contains form content
                            form_content = extract_form_content(latest_message.content)
                            if form_content:
                                # Update the form with the new content
                                st.session_state.draft_form = update_draft_form(st.session_state.draft_form, latest_message.content)
                                
                                # 添加调试信息
                                print("AI响应更新表格 - 内容长度:", len(form_content))
                                for field in st.session_state.draft_form.fields:
                                    if field.type == "markdown":
                                        if field.value != form_content:
                                            print("警告: 表格内容未成功更新!")
                                        break
                                        
                        # Update session state
                        st.session_state.messages = result["messages"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"处理请求时出错: {e}")
    
    with col2:
        # 图片上传按钮
        image_file = st.file_uploader(
            "上传表格图片",
            type=["jpg", "jpeg", "png", "bmp"],
            key="chat_image_uploader",
            help="上传包含表格的图片进行OCR识别",
            label_visibility="collapsed"
        )
        if image_file and st.session_state.draft_form:
            # 设置处理中状态
            st.session_state.ocr_processing = True
            
            # 保存原始图片文件键，便于后续处理
            current_image_key = image_file.name + "_" + str(hash(image_file.getvalue()))
            if not hasattr(st.session_state, 'last_processed_image') or st.session_state.last_processed_image != current_image_key:
                st.session_state.last_processed_image = current_image_key
                st.rerun()  # 仅当上传新图片时才刷新
            
            # 禁用标准输出和警告，防止EasyOCR输出无关日志
            import os
            import contextlib
            import logging
            import warnings
            
            # 临时禁用所有日志和警告
            logging.disable(logging.CRITICAL)
            warnings.filterwarnings("ignore")
            os.environ["PYTHONWARNINGS"] = "ignore"
            
            try:
                # 消息提示
                with st.spinner("正在处理图片，这可能需要几秒钟..."):
                    # 使用更安全的方式提取图像字节
                    try:
                        image_bytes = image_file.getvalue()
                    except Exception as img_err:
                        raise RuntimeError(f"无法读取图片数据: {str(img_err)}")
                    
                    # 捕获和重定向stdout和stderr
                    with open(os.devnull, 'w') as null_stream:
                        with contextlib.redirect_stdout(null_stream), contextlib.redirect_stderr(null_stream):
                            # 提取图片中的文本
                            extracted_text = extract_text_from_image(image_bytes)
                
                # 恢复日志和警告设置
                logging.disable(logging.NOTSET)
                warnings.resetwarnings()
                
                # 保存OCR结果
                st.session_state.ocr_result = extracted_text
                
                if extracted_text and not extracted_text.startswith("无法") and not extracted_text.startswith("初始化"):
                    # 用更安全的方式处理异步调用
                    try:
                        # 创建事件循环的隔离上下文
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        # 设置超时，避免长时间阻塞
                        with contextlib.suppress(asyncio.TimeoutError):
                            try:
                                # 调用大模型判断是否可转换为表格
                                can_convert, reason, markdown_table = loop.run_until_complete(
                                    asyncio.wait_for(can_convert_to_table(extracted_text), timeout=30)
                                )
                            finally:
                                loop.close()
                    except Exception as e:
                        st.error(f"处理OCR结果时发生错误: {str(e)}")
                        can_convert, reason, markdown_table = False, f"处理错误: {str(e)}", ""
                    
                    st.session_state.ocr_can_convert = can_convert
                    st.session_state.ocr_reason = reason
                    
                    if can_convert and markdown_table:
                        st.session_state.ocr_table_preview = markdown_table
                    else:
                        st.session_state.ocr_table_preview = "无法转换为表格"
                else:
                    st.session_state.ocr_can_convert = False
                    st.session_state.ocr_reason = "未能提取有效文本" if extracted_text else "OCR处理失败"
                    st.session_state.ocr_table_preview = extracted_text if extracted_text else "无法提取文本"
            except Exception as e:
                # 恢复日志和警告设置
                logging.disable(logging.NOTSET)
                warnings.resetwarnings()
                
                # 记录错误信息
                import traceback
                error_details = traceback.format_exc()
                
                # 设置错误状态
                st.session_state.ocr_can_convert = False
                st.session_state.ocr_reason = f"处理错误：{str(e)}"
                st.session_state.ocr_table_preview = "OCR处理失败"
                
                # 显示详细错误信息
                st.error(f"图片处理失败: {str(e)}")
            
            # 完成处理
            st.session_state.ocr_processing = False
            st.rerun()
            
# 如果没有上传Excel文件
elif not st.session_state.draft_form:
    st.chat_input("请先上传Excel文件...", disabled=True)

# 注意：用户输入处理已经在上面的chat_input回调中处理了
