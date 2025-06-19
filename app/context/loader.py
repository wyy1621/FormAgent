from typing import List, Dict
from datetime import datetime
from app.context.document_loaders import word_document_loader, pdf_document_loader, text_document_loader, excel_document_loader
from app.models import SupportDoc
import logging

async def load_file_into_context(filepath: str) -> SupportDoc:
    """
    Load the content of a supporting document into a data structure in memory
    """
    logging.info(f"Loading {filepath} into context ...")
    
    try:
        if filepath.endswith(".docx"):
            support_doc = word_document_loader(filepath)
        elif filepath.endswith(".pdf"):
            support_doc = pdf_document_loader(filepath)
        elif filepath.endswith(".txt"):
            support_doc = text_document_loader(filepath)
        elif filepath.endswith((".xlsx", ".xls")):
            support_doc = excel_document_loader(filepath)
        else:
            logging.warning(f"Unsupported file type: {filepath}")
            return None
            
        if support_doc and support_doc.get("content"):
            logging.info(f"Successfully loaded document. Loaded {len(support_doc['content'])} characters")
        else:
            logging.warning(f"Warning: No content extracted from {filepath}")
            
    except Exception as e:
        logging.error(f"Error loading document {filepath}: {str(e)}")
        return None

    return support_doc