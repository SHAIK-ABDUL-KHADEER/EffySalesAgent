import os
import uuid
import chromadb
import concurrent.futures
from pypdf import PdfReader
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
import re

# Define paths
PDF_FOLDER = r"C:\Users\birap\freelancing_projects\ollama\files"
CHROMA_DB_PATH = "./chroma_db"

# Ensure folder exists
os.makedirs(PDF_FOLDER, exist_ok=True)

# Initialize ChromaDB
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
embedding_func = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = chroma_client.get_or_create_collection("documents", embedding_function=embedding_func)

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(pdf_path)
        text = "\n\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
        return text.strip() if text else None
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return None

def chunk_text(text, chunk_size=500):
    """Splits large text into smaller chunks."""
    words = re.findall(r'\S+', text)
    return [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

def process_single_pdf(pdf_file):
    """Process a single PDF file and store it in ChromaDB."""
    pdf_path = os.path.join(PDF_FOLDER, pdf_file)
    print(f"Processing: {pdf_file}")

    text = extract_text_from_pdf(pdf_path)
    if not text:
        print(f"Skipping {pdf_file}, no text extracted.")
        return None

    chunks = chunk_text(text)
    doc_ids = [str(uuid.uuid4()) for _ in range(len(chunks))]
    metadatas = [{"filename": pdf_file, "chunk_index": i} for i in range(len(chunks))]

    collection.add(ids=doc_ids, documents=chunks, metadatas=metadatas)
    print(f"Added {len(chunks)} chunks from {pdf_file} to ChromaDB.")

def process_pdfs():
    """Process all PDFs in the folder using multithreading."""
    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.endswith(".pdf")]
    
    if not pdf_files:
        print("No PDF files found in the folder.")
        return

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_single_pdf, pdf_files)

if __name__ == "__main__":
    process_pdfs()
    print("All PDFs processed successfully!")
