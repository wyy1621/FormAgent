import io
import os
import cv2
import numpy as np
import logging
from PIL import Image
from app.utils.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
import threading

# 配置日志
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("ocr")

# EasyOCR读取器实例 - 使用全局单例模式
_reader = None
_reader_lock = threading.Lock()  # 添加线程锁确保初始化时线程安全

def get_reader(languages=['en', 'ch_sim']):
    """
    获取或初始化EasyOCR读取器 (单例模式)
    
    Args:
        languages: 识别的语言列表，默认为英文和简体中文
        
    Returns:
        EasyOCR Reader实例
    """
    global _reader
    
    # 已初始化则直接返回
    if _reader is not None:
        return _reader
    
    # 使用线程锁确保只有一个线程能够初始化读取器
    with _reader_lock:
        # 双重检查锁定模式，确保只初始化一次
        if _reader is not None:
            return _reader
            
        # 第一次调用时初始化
        try:
            # 关闭所有警告和调试输出
            import warnings
            warnings.filterwarnings("ignore")
            os.environ["PYTHONWARNINGS"] = "ignore"
            
            # 抑制EasyOCR的输出信息
            with open(os.devnull, 'w') as f:
                import contextlib
                import sys
                with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                    # 延迟导入EasyOCR以避免模块级别的日志输出
                    import easyocr
                    
                    # 检测CUDA可用性但捕获所有错误
                    gpu_available = False
                    try:
                        # 禁用PyTorch警告
                        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128"
                        os.environ["PYTHONWARNINGS"] = "ignore::UserWarning"
                        
                        import torch
                        gpu_available = torch.cuda.is_available()
                    except Exception as e:
                        logger.warning(f"检测GPU失败: {str(e)}")
                    
                    # 初始化读取器 - 使用保守设置
                    _reader = easyocr.Reader(
                        languages, 
                        gpu=gpu_available, 
                        verbose=False,
                        detector=True,  # 使用默认检测器
                        quantize=False,  # 不进行量化以避免torch错误
                        cudnn_benchmark=False  # 禁用cudnn基准以提高稳定性
                    )
                    
                    # 只记录一次初始化状态
                    logger.info(f"EasyOCR已初始化 (GPU模式: {gpu_available})")
        except Exception as e:
            logger.error(f"初始化EasyOCR失败: {str(e)}")
            return None
    return _reader

def preprocess_image(image):
    """
    预处理图像以提高OCR精度
    
    Args:
        image: numpy数组格式的图像
        
    Returns:
        预处理后的图像
    """
    # 转换为RGB (EasyOCR需要RGB图像)
    if len(image.shape) == 2 or image.shape[2] == 1:  # 灰度图
        img_rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:  # BGR图像
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # 图像增强处理
    # 1. 调整亮度和对比度
    alpha = 1.2  # 对比度
    beta = 10    # 亮度
    adjusted = cv2.convertScaleAbs(img_rgb, alpha=alpha, beta=beta)
    
    # 2. 降噪
    denoised = cv2.fastNlMeansDenoisingColored(adjusted, None, 10, 10, 7, 21)
    
    return denoised

def extract_text_from_image(image_data):
    """
    从图像中提取文本
    
    Args:
        image_data: 图像数据（字节或文件路径）
        
    Returns:
        str: 提取的文本
    """
    try:
        # 临时禁用所有日志输出
        import logging
        logging.disable(logging.CRITICAL)
        
        # 获取EasyOCR读取器 - 使用异常安全的方式
        try:
            reader = get_reader()
            if reader is None:
                logging.disable(logging.NOTSET)  # 恢复日志
                return "初始化OCR引擎失败，无法进行文字识别"
        except Exception as e:
            logging.disable(logging.NOTSET)  # 恢复日志
            logger.error(f"获取OCR读取器失败: {str(e)}")
            return f"初始化OCR引擎失败: {str(e)}"
            
        # 从字节数据加载图像
        if isinstance(image_data, bytes):
            try:
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    logging.disable(logging.NOTSET)  # 恢复日志
                    return "无法解析图像数据，请确保上传的是有效的图片文件"
            except Exception as img_err:
                logging.disable(logging.NOTSET)  # 恢复日志
                logger.error(f"解析图像数据失败: {str(img_err)}")
                return f"无法解析图像: {str(img_err)}"
        else:
            # 假设是文件路径
            if not os.path.exists(image_data):
                logging.disable(logging.NOTSET)  # 恢复日志
                return f"图片文件不存在: {image_data}"
            try:
                img = cv2.imread(image_data)
                if img is None:
                    logging.disable(logging.NOTSET)  # 恢复日志
                    return f"无法读取图片文件: {image_data}"
            except Exception as file_err:
                logging.disable(logging.NOTSET)  # 恢复日志
                logger.error(f"读取图片文件失败: {str(file_err)}")
                return f"无法读取图片: {str(file_err)}"
        
        # 预处理图像 - 捕获可能的异常
        try:
            processed_img = preprocess_image(img)
        except Exception as preproc_err:
            logging.disable(logging.NOTSET)  # 恢复日志
            logger.error(f"图像预处理失败: {str(preproc_err)}")
            # 如果预处理失败，使用原始图像
            processed_img = img
            
        # 使用EasyOCR识别文本 - 捕获可能的异常
        try:
            # 将输出重定向到空设备
            with open(os.devnull, 'w') as f:
                import contextlib
                import sys
                with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                    # 尝试进行OCR识别
                    results = reader.readtext(processed_img)
        except Exception as ocr_err:
            logging.disable(logging.NOTSET)  # 恢复日志
            logger.error(f"OCR识别失败: {str(ocr_err)}")
            return f"OCR处理失败: {str(ocr_err)}"
        
        # 提取识别的文本并组合
        extracted_text = ""
        for (bbox, text, prob) in results:
            if prob > 0.3:  # 忽略置信度过低的结果
                extracted_text += text + " "
                # 低置信度的结果可能需要换行
                if prob < 0.5:
                    extracted_text += "\n"
        
        # 恢复日志
        logging.disable(logging.NOTSET)
        
        # 返回结果，如果为空则返回提示信息
        final_text = extracted_text.strip()
        return final_text if final_text else "未能识别出任何文本，请尝试更清晰的图片"
            
    except Exception as e:
        # 恢复日志
        logging.disable(logging.NOTSET)
        logger.error(f"OCR处理出现未预期错误: {str(e)}")
        return f"图像处理发生错误: {str(e)}"

async def can_convert_to_table(text):
    """
    让大模型判断OCR提取的文本是否可以转换为表格
    
    Args:
        text: OCR提取的文本
        
    Returns:
        tuple: (可以转换为表格?, 原因, 转换后的markdown表格)
    """
    try:
        # 如果文本为空或过短，直接返回
        if not text or len(text) < 10:
            return False, "文本内容过少，无法识别表格结构", ""
            
        # 创建提示
        prompt = f"""作为数据格式化专家，请分析以下OCR提取的文本，并判断是否可以将其转换为结构化表格。

文本内容:
```
{text}
```

任务要求:
1. 仔细分析文本是否包含表格结构(行和列、分隔符、数据对齐、表头等)
2. 如果可以识别出表格结构，尝试将文本转换为规范的markdown表格
3. 考虑OCR可能的识别错误，适当进行修正，确保表格格式正确
4. 如果转换成功，确保表格具有良好的格式和对齐方式

请严格按照以下格式回答:

<flag>True或False</flag>
<reason>详细说明判断原因</reason>

如果可以转换为表格(<flag>True</flag>)，请额外提供:
<markdown_table>
| 列1 | 列2 | ...
| --- | --- | ...
| 数据1 | 数据2 | ...
</markdown_table>
"""
        
        # 调用LLM（包含错误处理）
        try:
            llm = get_llm("CHAT_LLM", temperature=0.0)
            messages = [HumanMessage(content=prompt)]
            response = await llm.ainvoke(messages)
            response_content = response.content
        except Exception as llm_error:
            logger.error(f"调用LLM失败: {str(llm_error)}")
            return False, f"分析处理失败: {str(llm_error)}", ""
        
        # 解析回应
        flag = False
        reason = "未提供有效判断"
        markdown_table = ""
          # 提取flag（使用更健壮的正则表达式）
        import re
        flag_match = re.search(r'<flag>(.*?)</flag>', response_content, re.DOTALL | re.IGNORECASE)
        
        if flag_match:
            flag_text = flag_match.group(1).strip().lower()
            flag = (flag_text == 'true')
        
        # 提取reason
        reason_match = re.search(r'<reason>(.*?)</reason>', response_content, re.DOTALL)
        if reason_match:
            reason = reason_match.group(1).strip()
        
        # 提取markdown_table
        if flag:
            table_match = re.search(r'<markdown_table>(.*?)</markdown_table>', response_content, re.DOTALL)
            if table_match:
                markdown_table = table_match.group(1).strip()
        
        # 返回结果
        return (flag, reason, markdown_table)
    except Exception as e:
        logger.error(f"处理表格转换时发生错误: {str(e)}")
        return False, f"表格格式分析失败: {str(e)}", ""
    if flag_match:
        flag_text = flag_match.group(1).strip().lower()
        flag = (flag_text == 'true')
    
    # 提取reason
    reason_match = re.search(r'<reason>(.*?)</reason>', response_content, re.DOTALL)
    if reason_match:
        reason = reason_match.group(1).strip()
    
    # 提取markdown_table
    if flag:
        table_match = re.search(r'<markdown_table>(.*?)</markdown_table>', response_content, re.DOTALL)
        if table_match:
            markdown_table = table_match.group(1).strip()
    
    return (flag, reason, markdown_table)

async def merge_tables(existing_table, new_table):
    """
    让大模型合并两个表格
    
    Args:
        existing_table: 现有的markdown表格
        new_table: 新的markdown表格(来自OCR)
        
    Returns:
        str: 合并后的markdown表格
    """
    try:
        # 如果两个表格中有一个为空，则返回非空的那个
        if not existing_table or existing_table.strip() == '':
            return new_table
        if not new_table or new_table.strip() == '':
            return existing_table
            
        # 创建详细的提示，指导大模型如何合并表格
        prompt = f"""作为数据整合专家，请将以下两个markdown表格智能合并成一个表格。

现有Excel表格:
```
{existing_table}
```

OCR识别出的新表格:
```
{new_table}
```

合并要求:
1. 保留现有Excel表格的所有数据和列结构
2. 智能分析两个表格的结构关系，识别相同或相似的列
3. 将OCR表格的数据按照合适的方式添加到现有表格中:
   - 如果OCR表格包含新行，添加这些行
   - 如果OCR表格包含新列，适当扩展表格结构
   - 如果OCR表格包含重复数据，避免重复添加
4. 处理OCR可能的识别错误，合理修正数据格式和内容
5. 确保最终表格的markdown格式正确，包括表头分隔行(---|---|...)
6. 确保合并后的表格列对齐整齐，便于可视化

请直接返回完整的合并后markdown表格，不需要解释合并过程或决策理由。
结果应该是规范的markdown表格格式，可以直接在markdown中渲染。
"""
        
        # 调用LLM，温度设为低值以获得更确定性的结果
        try:
            llm = get_llm("CHAT_LLM", temperature=0.1)
            messages = [HumanMessage(content=prompt)]
            response = await llm.ainvoke(messages)
            merged_table = response.content.strip()            # 验证合并结果是否是有效的markdown表格
            if '|' not in merged_table or not merged_table.strip():
                logger.warning("合并结果不是有效的markdown表格，将返回原始表格")
                return existing_table
                
            # 处理可能包含代码块的情况
            import re
            if "```" in merged_table:
                # 尝试从代码块中提取markdown表格内容
                code_pattern = r"```(?:markdown)?(.*?)```"
                code_matches = re.findall(code_pattern, merged_table, re.DOTALL)
                if code_matches:
                    # 使用找到的最大代码块内容
                    merged_table = max(code_matches, key=len).strip()
            
            # 确保结果是有效的markdown表格（至少有表头和分隔行）
            lines = merged_table.strip().split('\n')
            valid_table = False
            
            # 检查是否有合法的markdown表格结构
            if len(lines) >= 2:
                # 检查第一行是否包含 | 分隔的列
                if '|' in lines[0]:
                    # 检查第二行是否是分隔行
                    if len(lines) >= 2 and '---' in lines[1] and '|' in lines[1]:
                        valid_table = True
            
            # 如果不是有效表格，返回原始表格
            if not valid_table:
                logger.warning("合并结果不是有效的markdown表格，将返回原始表格")
                return existing_table
            
            # 返回合并后的表格
            return merged_table
        except Exception as e:
            logger.error(f"调用LLM合并表格失败: {str(e)}")
            return existing_table  # 失败时返回原表格
            
    except Exception as e:
        logger.error(f"合并表格过程中发生错误: {str(e)}")
        return existing_table  # 出错时返回原始表格
