import streamlit as st
from spire.pdf.common import *
from spire.pdf import *
import os
import requests
import base64
import shutil
import time
from io import BytesIO
from PIL import Image
import atexit
import uuid

# Configure page
st.set_page_config(layout="wide")
st.title("📄 PDF Image URL")

# Custom CSS for better styling
st.markdown("""
<style>
    .image-card {
        border-radius: 10px;
        padding: 15px;
        background: #f8f9fa;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        transition: transform 0.2s;
    }
    .image-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    .image-container {
        display: flex;
        justify-content: center;
        margin-bottom: 10px;
    }
    .uniform-image {
        width: 300px;
        height: 300px;
        object-fit: contain;
        border-radius: 8px;
        background: white;
        padding: 5px;
    }
    .stButton>button {
        width: 100%;
        border-radius: 5px;
    }
    .url-box {
        background: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin-top: 10px;
        word-break: break-all;
    }
    .storage-info {
        background: #e3f2fd;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 15px;
        border-left: 4px solid #2196f3;
    }
</style>
""", unsafe_allow_html=True)

# Storage management functions
def create_session_folder():
    """Create a unique session folder for this app instance"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    
    session_folder = f"extracted_images_{st.session_state.session_id}"
    if not os.path.exists(session_folder):
        os.makedirs(session_folder)
    return session_folder

def cleanup_old_folders():
    """Clean up old extraction folders from previous sessions"""
    try:
        current_time = time.time()
        base_dir = "."
        
        for item in os.listdir(base_dir):
            if item.startswith("extracted_images_") and os.path.isdir(item):
                # Check if folder is older than 1 hour (3600 seconds)
                folder_age = current_time - os.path.getctime(item)
                if folder_age > 3600:  # 1 hour
                    shutil.rmtree(item, ignore_errors=True)
                    
        # Also clean up any temp PDF files
        for item in os.listdir(base_dir):
            if item.startswith("temp_") and item.endswith(".pdf"):
                file_age = current_time - os.path.getctime(item)
                if file_age > 3600:  # 1 hour
                    os.remove(item)
                    
    except Exception as e:
        # Silent cleanup - don't break the app if cleanup fails
        pass

def cleanup_current_session():
    """Clean up current session files"""
    try:
        if 'session_folder' in st.session_state and os.path.exists(st.session_state.session_folder):
            shutil.rmtree(st.session_state.session_folder, ignore_errors=True)
        
        # Clean up temp PDF
        temp_pdf_path = f"temp_{st.session_state.get('session_id', 'unknown')}.pdf"
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
    except Exception as e:
        pass

def get_folder_size(folder_path):
    """Get the size of a folder in MB"""
    if not os.path.exists(folder_path):
        return 0
    
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
            except OSError:
                pass
    return total_size / (1024 * 1024)  # Convert to MB

# Initialize session state
if 'extracted_images' not in st.session_state:
    st.session_state.extracted_images = []
if 'image_urls' not in st.session_state:
    st.session_state.image_urls = {}
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None

# Clean up old folders on app start
cleanup_old_folders()

# Create session folder
EXTRACT_FOLDER = create_session_folder()
st.session_state.session_folder = EXTRACT_FOLDER

# Register cleanup function to run on app exit
atexit.register(cleanup_current_session)

# Get ImgBB API key
IMG_API_KEY = '93b5e89f0e0c87640ebe7ec6df835a55'

if not IMG_API_KEY:
    st.error("🔑 ImgBB API key not found. Please set it in secrets.toml or environment variables.")
    st.stop()

# Display storage info
folder_size = get_folder_size(EXTRACT_FOLDER)
if folder_size > 0:
    st.markdown(f"""
    <div class='storage-info'>
        💾 <strong>Current session storage:</strong> {folder_size:.2f} MB
        <br>📁 <strong>Session folder:</strong> {EXTRACT_FOLDER}
        <br>🧹 <strong>Auto-cleanup:</strong> Enabled (removes old files after 1 hour)
    </div>
    """, unsafe_allow_html=True)

# File uploader
if st.session_state.uploaded_file is None:
    with st.container():
        st.subheader("Step 1: Upload PDF")
        uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], 
                                       accept_multiple_files=False,
                                       help="Upload the PDF containing images you want to extract")
        if uploaded_file:
            st.session_state.uploaded_file = uploaded_file
            st.rerun()
else:
    # Display file info
    st.success(f"✅ File uploaded: {st.session_state.uploaded_file.name}")
    
    # Save the uploaded file temporarily with unique name
    temp_pdf_path = f"temp_{st.session_state.session_id}.pdf"
    with open(temp_pdf_path, "wb") as f:
        f.write(st.session_state.uploaded_file.getbuffer())
    
    try:
        # Create PDF document object
        doc = PdfDocument()
        doc.LoadFromFile(temp_pdf_path)
        
        # Only extract images if we haven't done so yet
        if not st.session_state.extracted_images:
            with st.container():
                st.subheader("Step 2: Extraction Options")
                col1, col2 = st.columns(2)
                
                with col1:
                    extraction_mode = st.radio(
                        "Extraction mode:",
                        ["Extract from all pages", "Extract from specific pages"],
                        horizontal=True
                    )
                
                with col2:
                    if extraction_mode == "Extract from specific pages":
                        page_options = list(range(1, doc.Pages.Count + 1))
                        pages_to_extract = st.multiselect(
                            "Select pages to extract from:",
                            options=page_options,
                            default=page_options[0] if page_options else []
                        )
                        pages_to_extract = [p - 1 for p in pages_to_extract]
                    else:
                        pages_to_extract = list(range(doc.Pages.Count))
                
                # Replace your extraction code with this more robust version
                if st.button("🚀 Extract Images", type="primary"):
                    if not pages_to_extract:
                        st.warning("Please select at least one page to extract images from.")
                    else:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        extracted_images = []
        
                        try:
                            for idx, page_num in enumerate(pages_to_extract):
                                status_text.text(f"Processing page {page_num+1}/{len(pages_to_extract)}...")
                                progress_bar.progress((idx + 1) / len(pages_to_extract))
                
                                page = doc.Pages.get_Item(page_num)
                                imageInfos = PdfImageHelper().GetImagesInfo(page)
                
                                for i, imageInfo in enumerate(imageInfos):
                                    try:
                                        image_filename = f"{EXTRACT_FOLDER}/Page_{page_num+1}_Image_{i+1}.png"
                                        imageInfo.Image.Save(image_filename)
                                        extracted_images.append(image_filename)
                                    except Exception as img_error:
                                        st.warning(f"Skipped image {i+1} on page {page_num+1}: {str(img_error)}")
                                        continue
            
                            st.session_state.extracted_images = extracted_images
                            status_text.success(f"✅ Successfully extracted {len(extracted_images)} images!")
                            time.sleep(1)
                            st.rerun()
            
                        except Exception as e:
                            status_text.error(f"❌ Extraction failed: {str(e)}")
                        finally:
                            progress_bar.empty()
                            
        # Display results if we have extracted images
        if st.session_state.extracted_images:
            st.subheader(f"Step 3: Extracted Images ({len(st.session_state.extracted_images)} found)")
            
            # Update storage info
            folder_size = get_folder_size(EXTRACT_FOLDER)
            st.info(f"💾 Current storage usage: {folder_size:.2f} MB")
            
            # Display images in a responsive grid
            cols = st.columns(3)
            for i, img_path in enumerate(st.session_state.extracted_images):
                with cols[i % 3]:
                    with st.container():
                        st.markdown(f"<div class='image-card'>", unsafe_allow_html=True)
                        
                        # Image display with consistent size
                        st.markdown("<div class='image-container'>", unsafe_allow_html=True)
                        if os.path.exists(img_path):
                            st.image(img_path, use_container_width=False, width=300)
                        else:
                            st.error("Image file not found")
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # File info
                        st.caption(f"📄 Page {img_path.split('_')[1]} - Image {img_path.split('_')[3].split('.')[0]}")
                        
                        # Upload button
                        if st.button(f"🌐 Generate URL", key=f"btn_{i}"):
                            if os.path.exists(img_path):
                                with st.spinner("Uploading to ImgBB..."):
                                    try:
                                        with open(img_path, "rb") as img_file:
                                            img_data = img_file.read()
                                        
                                        img_b64 = base64.b64encode(img_data).decode()
                                        payload = {
                                            "key": IMG_API_KEY,
                                            "image": img_b64,
                                            "name": os.path.basename(img_path),
                                            "expiration": 0
                                        }
                                        
                                        response = requests.post(
                                            "https://api.imgbb.com/1/upload",
                                            data=payload
                                        )
                                        
                                        if response.status_code == 200:
                                            result = response.json()
                                            if result.get("success"):
                                                st.session_state.image_urls[img_path] = result["data"]["url"]
                                                st.rerun()
                                            else:
                                                st.error("Upload failed")
                                        else:
                                            st.error(f"API error: {response.status_code}")
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
                            else:
                                st.error("Image file not found")
                        
                        # Display URL if exists
                        if img_path in st.session_state.image_urls:
                            url = st.session_state.image_urls[img_path]
                            st.markdown("<div class='url-box'>", unsafe_allow_html=True)
                            st.markdown("**🔗 Permanent URL:**")
                            st.code(url, language="text")
                            st.markdown(f"[Open in new tab]({url})")
                            st.markdown("</div>", unsafe_allow_html=True)
                        
                        st.markdown("</div>", unsafe_allow_html=True)
            
            # Storage management buttons
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🧹 Clean Current Session", type="secondary"):
                    cleanup_current_session()
                    st.session_state.extracted_images = []
                    st.session_state.image_urls = {}
                    st.success("✅ Current session cleaned up!")
                    time.sleep(1)
                    st.rerun()
            
            with col2:
                if st.button("🔄 Process Another PDF", type="secondary"):
                    cleanup_current_session()
                    st.session_state.extracted_images = []
                    st.session_state.image_urls = {}
                    st.session_state.uploaded_file = None
                    st.rerun()
            
            with col3:
                if st.button("🗑️ Clean All Old Files", type="secondary"):
                    cleanup_old_folders()
                    st.success("✅ Old files cleaned up!")
                    time.sleep(1)
                    st.rerun()
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
    finally:
        if 'doc' in locals():
            doc.Dispose()
        # Don't automatically remove temp PDF here - let it be cleaned up by the scheduled cleanup