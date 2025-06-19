import PyPDF2
import io
import streamlit as st
import os
from app.models import DraftForm

def parse_pdf_form(form_filepath: str) -> DraftForm:
    """
    Parse a PDF form and return the data as a dictionary in the required format.
    """
    fields = []
    checkbox_groups = {}  # Dictionary to group checkboxes
    
    try:
        with open(os.path.join(os.getcwd(), form_filepath), "rb") as f:
            reader = PyPDF2.PdfReader(f)
            if hasattr(reader, "get_fields") and callable(getattr(reader, "get_fields")):
                pdf_fields = reader.get_fields()
            else:
                pdf_fields = None
                
            if pdf_fields:
                # First pass: collect all checkboxes
                for field_name, field in pdf_fields.items():
                    field_type = field.get("/FT")
                    if field_type == "/Btn":
                        # Extract base name for checkbox group (remove any numeric suffix)
                        base_name = ''.join(c for c in field_name if not c.isdigit())
                        if base_name not in checkbox_groups:
                            checkbox_groups[base_name] = []
                        checkbox_groups[base_name].append({
                            "name": field_name,
                            "value": field.get("/V", "/Off"),
                            "description": field.get("/TU", "")
                        })
                    else:
                        # Handle non-checkbox fields
                        type_str = "dropdown" if field_type == "/Ch" else "text"
                        options = []
                        if type_str == "dropdown":
                            opts = field.get("/Opt")
                            if opts:
                                options = [str(opt) for opt in opts] if isinstance(opts, list) else [str(opts)]
                        
                        # Check if it's a list box (multiple selection dropdown)
                        if field.get("/Ff", 0) & 0x20000:  # 0x20000 is the flag for multiple selection
                            type_str = "list_box"
                        
                        fields.append({
                            "label": field_name,
                            "description": field.get("/TU", ""),
                            "type": type_str,
                            "docId": None,
                            "value": field.get("/V", ""),
                            "options": options,
                            "lastProcessed": "",
                            "lastSurveyed": ""
                        })
                
                # Second pass: add grouped checkboxes
                for base_name, checkboxes in checkbox_groups.items():
                    fields.append({
                        "label": base_name,
                        "description": checkboxes[0]["description"],
                        "type": "checkbox_group",
                        "docId": None,
                        "value": [cb["value"] for cb in checkboxes],
                        "options": [cb["name"] for cb in checkboxes],
                        "lastProcessed": "",
                        "lastSurveyed": ""
                    })
    except Exception as e:
        raise Exception(f"Error parsing PDF form: {str(e)}")
        
    return {
        "formFileName": form_filepath,
        "lastSaved": "",
        "fields": fields
    }


def fill_pdf_form(pdf_path: str, draft_form: DraftForm) -> bytes:
    """
    Fill the PDF form with the provided data and return the filled PDF as bytes.
    Handles various types of PDF form fields including:
    - Text fields (/Tx)
    - Checkboxes (/Btn)
    - Radio buttons (/Btn)
    - Dropdown lists (/Ch)
    - List boxes (/Ch with multiple selection)
    - Formatted fields
    """
    try:
        # Read the original PDF
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            writer = PyPDF2.PdfWriter()
            
            # Copy all pages to the writer
            for page in reader.pages:
                writer.add_page(page)
            
            # Copy the form fields to the writer
            if "/AcroForm" in reader.trailer["/Root"]:
                writer._root_object.update({
                    PyPDF2.generic.NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]
                })
            
            # Create a mapping of field names to their values
            field_values = {}
            for field in draft_form["fields"]:
                label = field["label"]
                value = field["value"]
                field_type = field["type"]
                
                # Handle different field types
                # TODO: Add support for checkbox groups and list boxes
                # if field_type == "checkbox_group":
                #     # For checkbox groups, we need to map each checkbox individually
                #     if isinstance(value, list):
                #         for i, checkbox_value in enumerate(value):
                #             checkbox_name = field["options"][i] if i < len(field["options"]) else f"{label}_{i+1}"
                #             field_values[checkbox_name] = checkbox_value
                # elif field_type == "list_box":
                #     # For list boxes, ensure we have a list of values
                #     field_values[label] = value if isinstance(value, list) else [value]
                # else:
                # For other fields, use the value as is
                field_values[label] = value
            
            # Update the writer's form fields
            # TODO: Will this work for forms with more than one page?
            writer.update_page_form_field_values(writer.pages[0], field_values)
            
            # Write to bytes buffer
            output_buffer = io.BytesIO()
            writer.write(output_buffer)
            output_buffer.seek(0)
            
            return output_buffer.getvalue()
            
    except Exception as e:
        st.error(f"Error filling PDF form: {str(e)}")
        raise Exception(f"Error filling PDF form: {str(e)}")
