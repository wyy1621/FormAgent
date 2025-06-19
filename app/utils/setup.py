from dotenv import load_dotenv, find_dotenv
import os
import sys

def setup():
    """
    Set up the environment for the application.
    
    This function:
    1. In development mode, loads environment variables from a .env file
    2. In production mode, verifies the presence of required API keys
    3. Configures API keys in the environment
    
    Raises:
        SystemExit: If the .env file is not found or required environment variables are missing
    """
    if os.getenv("ENV", "development").lower() == "development":
      dotenv_path = find_dotenv(usecwd=True)
      if not dotenv_path:
          print("Error: .env file not found in the current directory or parent directories.")
          sys.exit(1)

      load_dotenv(dotenv_path)
    
    # 设置OCR环境
    setup_ocr_environment()

def setup_ocr_environment():
    """
    设置OCR环境变量和配置
    """
    # 创建日志对象
    import logging
    logger = logging.getLogger("ocr_setup")
    logger.setLevel(logging.INFO)
    
    # 检查是否已经设置过环境变量，避免重复初始化
    if os.getenv("OCR_SETUP_COMPLETE"):
        return
    
    try:
        # 检查是否可以导入easyocr
        try:
            import easyocr
            logger.info("EasyOCR已加载，OCR功能可用")
        except ImportError:
            logger.warning("警告: EasyOCR未安装，OCR功能可能无法使用")
            return
        
        # 设置EasyOCR环境变量
        # 默认模型下载路径，避免每次都重新下载模型
        if not os.getenv("EASYOCR_MODULE_PATH"):
            model_dir = os.path.join(os.path.expanduser("~"), ".EasyOCR")
            os.environ["EASYOCR_MODULE_PATH"] = model_dir
            logger.info(f"EasyOCR模型路径设置为: {model_dir}")
        
        # 设置CUDA环境（如果有CUDA）
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("检测到CUDA可用，EasyOCR将使用GPU加速")
                os.environ["EASYOCR_CUDA"] = "1"
            else:
                logger.debug("未检测到CUDA，EasyOCR将使用CPU模式")
                os.environ["EASYOCR_CUDA"] = "0"
        except:
            logger.debug("未检测到PyTorch，EasyOCR将使用CPU模式")
            os.environ["EASYOCR_CUDA"] = "0"
            
        # 标记OCR环境已设置完成
        os.environ["OCR_SETUP_COMPLETE"] = "1"
            
    except Exception as e:
        print(f"设置OCR环境时出错: {str(e)}")
