import os
import sys
import zipfile
import xml.etree.ElementTree as ET
import pypdf

# Reconfigure stdout/stderr to utf-8 to avoid encoding errors on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def extract_text_from_pdf(filepath):
    """Extract text from a PDF file using pypdf."""
    text = ""
    try:
        reader = pypdf.PdfReader(filepath)
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"--- Page {i+1} ---\n{page_text}\n"
        return text.strip()
    except Exception as e:
        print(f"Error parsing PDF {filepath}: {e}")
        return ""

def extract_text_from_hwpx(filepath):
    """Extract text from an HWPX file natively by reading Contents/section0.xml."""
    text_parts = []
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            # HWPX can have multiple sections, let's scan for all section XMLs
            sections = [f for f in z.namelist() if f.startswith("Contents/section") and f.endswith(".xml")]
            # Sort sections numerically (e.g. section0.xml, section1.xml...)
            sections.sort()
            
            for section in sections:
                xml_data = z.read(section)
                root = ET.fromstring(xml_data)
                
                # Extract text from tags ending with 't' (which corresponds to <hp:t> or <t>)
                for elem in root.iter():
                    if elem.tag.endswith('}t') or elem.tag == 't':
                        if elem.text:
                            text_parts.append(elem.text)
                            
        return "\n".join(text_parts).strip()
    except Exception as e:
        print(f"Error parsing HWPX {filepath}: {e}")
        return ""

def extract_text_from_docx(filepath):
    """Extract text from a DOCX file natively by reading word/document.xml."""
    text_parts = []
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            xml_data = z.read("word/document.xml")
            root = ET.fromstring(xml_data)
            
            # DOCX text is enclosed in <w:t> tags
            for elem in root.iter():
                if elem.tag.endswith('}t') or elem.tag == 't':
                    if elem.text:
                        text_parts.append(elem.text)
                        
        return "\n".join(text_parts).strip()
    except Exception as e:
        print(f"Error parsing DOCX {filepath}: {e}")
        return ""

def extract_text(filepath):
    """Detect file type and extract text content."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return ""
        
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext == ".hwpx":
        return extract_text_from_hwpx(filepath)
    elif ext == ".docx":
        return extract_text_from_docx(filepath)
    elif ext == ".hwp":
        print(f"Warning: Binary HWP format ({filepath}) is not natively supported. "
              "Please check if a parallel PDF is available.")
        return ""
    else:
        print(f"Unsupported file format: {ext} for {filepath}")
        return ""

if __name__ == "__main__":
    # Test script locally
    import sys
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        print(f"Extracting text from {test_file}...")
        content = extract_text(test_file)
        print(f"Extracted {len(content)} characters.")
        print("First 500 characters:")
        print(content[:500])
