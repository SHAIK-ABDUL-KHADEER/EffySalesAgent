from flask import Flask, render_template, request, send_from_directory, session
import openai
import chromadb
import re
import time
import google.generativeai as genai
from functools import lru_cache
import edge_tts
import asyncio
import os
import uuid
import logging
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Setup logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not OPENAI_API_KEY:
    logger.error("OpenAI API key is missing")
    raise ValueError("OPENAI_API_KEY not set in environment")
if not GEMINI_API_KEY:
    logger.error("Gemini API key is missing")
    raise ValueError("GEMINI_API_KEY not set in environment")

openai.api_key = OPENAI_API_KEY

# Setup ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")
try:
    collection = chroma_client.get_collection("documents")
except Exception as e:
    logger.warning(f"ChromaDB collection not found, creating new one: {str(e)}")
    collection = chroma_client.create_collection("documents")

# Setup folder for audio files
AUDIO_FOLDER = "static/audio"
os.makedirs(AUDIO_FOLDER, exist_ok=True)

def fix_broken_words(text: str) -> str:
    return re.sub(r'(\b\w+)\s+(\w+\b)', r'\1\2', text)

@lru_cache(maxsize=100)
def fetch_context_from_chroma(query: str) -> str:
    if not query.strip():
        logger.warning("Empty query received")
        return "No query provided."

    try:
        results = collection.query(query_texts=[query], n_results=5)
        documents = results.get("documents", [[]])[0]
        scores = results.get("distances", [[]])[0]

        if not documents:
            logger.info("No documents found in ChromaDB for query")
            return "No relevant documents found."

        context = "\n\n".join(
            f"Document {i+1} (Relevance: {1 - score:.2f}):\n{doc}"
            for i, (doc, score) in enumerate(zip(documents, scores)) if score < 0.8
        )
        return context if context else "No highly relevant documents found."
    except Exception as e:
        logger.error(f"ChromaDB query error: {str(e)}")
        return "Error fetching context from database."

async def generate_tts_audio(text: str) -> str:
    try:
        if not text.strip():
            logger.warning("Empty text for TTS")
            return ""
        voice = "en-US-JennyNeural"
        output_file = os.path.join(AUDIO_FOLDER, f"{uuid.uuid4()}.mp3")
        communicate = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
        await communicate.save(output_file)
        logger.info(f"TTS audio generated: {output_file}")
        return os.path.basename(output_file)
    except Exception as e:
        logger.error(f"Edge TTS error: {str(e)}")
        return ""

async def get_chat_response_openai(context: str, query: str, conversation_history: list) -> tuple:
    cleaned_context = fix_broken_words(context)
    try:
        messages = [
            {"role": "system", "content": (
                "You are Effy Assistant, a helpful and concise AI for sales queries. "
                "Provide accurate, conversational responses in 3–4 sentences. "
                "Use the provided context and conversation history to maintain coherence."
            )},
            *conversation_history,
            {"role": "user", "content": (
                f"### Context:\n{cleaned_context}\n\n"
                f"### Query:\n{query}"
            )}
        ]
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=200
        )
        answer = response.choices[0].message["content"].strip()
        audio_file = await generate_tts_audio(answer)
        logger.info("OpenAI response generated successfully")
        return answer, audio_file
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return f"Error: OpenAI API failed - {str(e)}", ""

async def get_chat_response_gemini(context: str, query: str, conversation_history: list) -> tuple:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")

        chat_history = '\n'.join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
        prompt = f"""
        You are Effy Assistant, a helpful and concise AI for sales queries.
        Respond in 3–4 well-structured, conversational sentences.
        Use the following context and conversation history to maintain coherence:

        Context:
        {context}

        Conversation History:
        {chat_history}

        Question:
        {query}
        """

        response = model.generate_content(prompt)
        answer = response.text.strip()
        audio_file = await generate_tts_audio(answer)
        logger.info("Gemini response generated successfully")
        return answer, audio_file
    except Exception as e:
        logger.error(f"Gemini API error: {str(e)}")
        return f"Error: Gemini API failed - {str(e)}", ""

@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

@app.route("/cleanup_audio", methods=["GET"])
def cleanup_audio():
    try:
        for file in os.listdir(AUDIO_FOLDER):
            file_path = os.path.join(AUDIO_FOLDER, file)
            if os.path.isfile(file_path) and file.endswith(".mp3"):
                os.remove(file_path)
        logger.info("Audio files cleaned up")
        return "Audio files cleaned up."
    except Exception as e:
        logger.error(f"Audio cleanup error: {str(e)}")
        return f"Error cleaning up audio: {str(e)}"

@app.route("/", methods=["GET", "POST"])
async def index():
    answer = ""
    user_query = ""
    model_choice = "openai"
    response_time = 0
    audio_file = ""

    if 'conversation_history' not in session:
        session['conversation_history'] = []

    try:
        for file in os.listdir(AUDIO_FOLDER):
            file_path = os.path.join(AUDIO_FOLDER, file)
            if os.path.isfile(file_path) and file.endswith(".mp3"):
                os.remove(file_path)
        logger.info("Old audio files cleaned up before new request")
    except Exception as e:
        logger.error(f"Audio cleanup error: {str(e)}")

    if request.method == "POST":
        user_query = request.form["query"].strip()
        model_choice = request.form["model"]
        logger.info(f"Received query: {user_query}, model: {model_choice}")

        if not user_query:
            answer = "Please provide a valid query."
            logger.warning("Empty query submitted")
        else:
            context = fetch_context_from_chroma(user_query)
            start_time = time.time()

            session['conversation_history'].append({"role": "user", "content": user_query})
            if len(session['conversation_history']) > 10:
                session['conversation_history'] = session['conversation_history'][-10:]

            if model_choice == "gemini":
                answer, audio_file = await get_chat_response_gemini(context, user_query, session['conversation_history'])
            else:
                answer, audio_file = await get_chat_response_openai(context, user_query, session['conversation_history'])

            session['conversation_history'].append({"role": "assistant", "content": answer})
            session.modified = True

            end_time = time.time()
            response_time = round(end_time - start_time, 2)
            logger.info(f"Response generated in {response_time} seconds")

    return render_template("chat.html", answer=answer, user_query=user_query, model_choice=model_choice, response_time=response_time, audio_file=audio_file)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)