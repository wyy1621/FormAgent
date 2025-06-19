import os
from streamlit.runtime.uploaded_file_manager import UploadedFile

def save_file_to_disk(file: UploadedFile, path: str) -> str:
    """
    Save a file to disk and return the path.
    """
    os.makedirs(path, exist_ok=True)
    filepath = os.path.join(path, file.name)
    with open(filepath, "wb") as f:
        f.write(file.read())
    return filepath