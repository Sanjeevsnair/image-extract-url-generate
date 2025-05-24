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
import threading

# Configure page
st.set_page_config(layout="wide")
st.title("📄 PDF Image URL Extractor")

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
        max-width: 100%;
        height: auto;
        max-height: 300px;
        object-fit: contain;
        border-radius: 8px;
        background: white;
        padding: 5px;
    }
    .stButton>button {
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
    .progress-text {
        font-size: 0.9em;
        color: #666;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# Constants
IMG_API_KEY = '93b5e89f0e0c87640ebe7ec6df835a55'  # Replace with your actual key
MAX_MEMORY_MB = 512  # Render free tier memory limit
CHUNK_SIZE = 3  # Pages to process at a time

# Session management
def init_session():
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.extracted_images = []
        st.session_state.image_urls = {}
        st.session_state.uploaded_file = None
        st.session_state.processing = False
        st.session_state.current_page = 0

# Storage management
def create_session_folder():
    session_folder = f"extracted_images_{st.session_state.session_id}"
    if not os.path.exists(session_folder):
        os.makedirs(session_folder)
    return session_folder

def cleanup_session():
    try:
        if 'session_folder' in st.session_state and os.path.exists(st.session_state.session_folder):
            shutil.rmtree(st.session_state.session_folder, ignore_errors=True)
        temp_pdf = f"temp_{st.session_state.get('session_id', 'unknown')}.pdf"
        if os.path.exists(temp_pdf):
            os.remove(temp_pdf)
    except:
        pass

def get_folder_size(folder_path):
    if not os.path.exists(folder_path):
        return 0
    return sum(os.path.getsize(os.path.join(dirpath, filename)) 
           for dirpath, dirnames, filenames in os.walk(folder_path) 
           for filename in filenames) / (1024 * 1024)

# Image processing
def process_page(page, page_num, extract_folder):
    images = []
    imageHelper = PdfImageHelper()
    imageInfos = imageHelper.GetImagesInfo(page)
    
    for i, imageInfo in enumerate(imageInfos):
        try:
            img_path = f"{extract_folder}/Page_{page_num+1}_Image_{i+1}.png"
            imageInfo.Image.Save(img_path)
            
            # Optimize image size
            with Image.open(img_path) as img:
                img.thumbnail((800, 800))  # Resize but maintain aspect ratio
                img.save(img_path, optimize=True, quality=85)
            
            images.append(img_path)
        except Exception as e:
            st.warning(f"Skipped image {i+1} on page {page_num+1}: {str(e)}")
    
    return images

# Keep-alive for Render
def keep_alive():
    while st.session_state.get('keep_alive', True):
        time.sleep(15)
        st.experimental_rerun()

# Initialize
init_session()
EXTRACT_FOLDER = create_session_folder()
st.session_state.session_folder = EXTRACT_FOLDER
atexit.register(cleanup_session)

# Start keep-alive thread
if 'keep_alive_thread' not in st.session_state:
    st.session_state.keep_alive = True
    st.session_state.keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    st.session_state.keep_alive_thread.start()

# Display storage info
folder_size = get_folder_size(EXTRACT_FOLDER)
if folder_size > 0:
    st.markdown(f"""
    <div class='storage-info'>
        💾 <strong>Current session storage:</strong> {folder_size:.2f} MB
        <br>📁 <strong>Session folder:</strong> {EXTRACT_FOLDER}
        <br>🧹 <strong>Auto-cleanup:</strong> Enabled when session ends
    </div>
    """, unsafe_allow_html=True)

# File uploader
if st.session_state.uploaded_file is None:
    st.subheader("Step 1: Upload PDF")
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], 
                                   help="Upload the PDF containing images you want to extract")
    
    if uploaded_file:
        # Quick validation of file size
        if len(uploaded_file.getvalue()) > 10 * 1024 * 1024:  # 10MB limit
            st.error("File too large for free tier (max 10MB)")
        else:
            st.session_state.uploaded_file = uploaded_file
            st.rerun()
else:
    # Display file info
    st.success(f"✅ File uploaded: {st.session_state.uploaded_file.name}")
    
    # Save the uploaded file temporarily
    temp_pdf_path = f"temp_{st.session_state.session_id}.pdf"
    with open(temp_pdf_path, "wb") as f:
        f.write(st.session_state.uploaded_file.getbuffer())
    
    try:
        # Load PDF document
        doc = PdfDocument()
        doc.LoadFromFile(temp_pdf_path)
        total_pages = doc.Pages.Count
        
        # Extraction options
        st.subheader("Step 2: Extraction Options")
        col1, col2 = st.columns(2)
        
        with col1:
            extraction_mode = st.radio(
                "Extraction mode:",
                ["Extract from all pages", "Extract from specific pages"],
                index=0,
                horizontal=True
            )
        
        with col2:
            if extraction_mode == "Extract from specific pages":
                page_options = list(range(1, total_pages + 1))
                pages_to_extract = st.multiselect(
                    "Select pages to extract from:",
                    options=page_options,
                    default=page_options[0] if page_options else []
                )
                pages_to_extract = [p - 1 for p in pages_to_extract]
            else:
                pages_to_extract = list(range(total_pages))
        
        # Start processing
        if st.button("🚀 Extract Images", type="primary", disabled=st.session_state.processing):
            if not pages_to_extract:
                st.warning("Please select at least one page to extract images from.")
            else:
                st.session_state.processing = True
                st.session_state.extracted_images = []
                st.session_state.pages_to_process = pages_to_extract
                st.session_state.current_page = 0
                st.rerun()
        
        # Processing in chunks
        if st.session_state.processing and st.session_state.current_page < len(st.session_state.pages_to_process):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Process a chunk of pages
            end_idx = min(st.session_state.current_page + CHUNK_SIZE, len(st.session_state.pages_to_process))
            current_chunk = st.session_state.pages_to_process[st.session_state.current_page:end_idx]
            
            for idx, page_num in enumerate(current_chunk):
                progress = (st.session_state.current_page + idx) / len(st.session_state.pages_to_process)
                progress_bar.progress(progress)
                status_text.text(f"Processing page {page_num+1} of {len(st.session_state.pages_to_process)}...")
                
                try:
                    page = doc.Pages.get_Item(page_num)
                    new_images = process_page(page, page_num, EXTRACT_FOLDER)
                    st.session_state.extracted_images.extend(new_images)
                except Exception as e:
                    st.warning(f"Error processing page {page_num+1}: {str(e)}")
            
            st.session_state.current_page = end_idx
            
            # Check if processing is complete
            if st.session_state.current_page >= len(st.session_state.pages_to_process):
                st.session_state.processing = False
                status_text.success(f"✅ Extraction complete! Found {len(st.session_state.extracted_images)} images")
                time.sleep(1)
                st.rerun()
            else:
                time.sleep(0.5)  # Small delay between chunks
                st.rerun()
        
        # Display results
        if st.session_state.extracted_images:
            st.subheader(f"Step 3: Extracted Images ({len(st.session_state.extracted_images)} found)")
            
            # Display in a responsive grid
            cols = st.columns(3)
            for i, img_path in enumerate(st.session_state.extracted_images):
                with cols[i % 3]:
                    with st.container():
                        st.markdown(f"<div class='image-card'>", unsafe_allow_html=True)
                        
                        # Image display
                        if os.path.exists(img_path):
                            st.image(img_path, use_column_width=True)
                        else:
                            st.error("Image not found")
                        
                        # File info
                        st.caption(f"📄 Page {img_path.split('_')[1]} - Image {img_path.split('_')[3].split('.')[0]}")
                        
                        # URL generation
                        if img_path not in st.session_state.image_urls:
                            if st.button(f"🌐 Get URL", key=f"btn_{i}"):
                                with st.spinner("Uploading to ImgBB..."):
                                    try:
                                        with open(img_path, "rb") as img_file:
                                            response = requests.post(
                                                "https://api.imgbb.com/1/upload",
                                                params={"key": IMG_API_KEY},
                                                files={"image": img_file}
                                            )
                                        
                                        if response.status_code == 200:
                                            result = response.json()
                                            if result.get("success"):
                                                st.session_state.image_urls[img_path] = result["data"]["url"]
                                                st.rerun()
                                    except Exception as e:
                                        st.error(f"Upload failed: {str(e)}")
                        
                        # Display URL if exists
                        if img_path in st.session_state.image_urls:
                            url = st.session_state.image_urls[img_path]
                            st.markdown("<div class='url-box'>", unsafe_allow_html=True)
                            st.markdown("**🔗 Permanent URL:**")
                            st.code(url, language="text")
                            st.markdown(f"[Open in new tab]({url})")
                            st.markdown("</div>", unsafe_allow_html=True)
                        
                        st.markdown("</div>", unsafe_allow_html=True)
            
            # Management buttons
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔄 Process Another PDF", type="secondary"):
                    cleanup_session()
                    st.session_state.extracted_images = []
                    st.session_state.image_urls = {}
                    st.session_state.uploaded_file = None
                    st.session_state.processing = False
                    st.rerun()
            
            with col2:
                if st.button("🧹 Clean Current Session", type="secondary"):
                    cleanup_session()
                    st.session_state.extracted_images = []
                    st.session_state.image_urls = {}
                    st.session_state.processing = False
                    st.success("Session cleaned up!")
                    time.sleep(1)
                    st.rerun()
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.session_state.processing = False
    finally:
        if 'doc' in locals():
            doc.Dispose()

# Add footer
st.markdown("---")
st.markdown("""
<small>Optimized for Render's free tier. Images are automatically cleaned up when the session ends.</small>
""", unsafe_allow_html=True)