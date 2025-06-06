unzip ai-assist-main.zip
cd ai-assist-main
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


upload file to files directory
python3 pdf_processing.py 


uvicorn chat:app --host 0.0.0.0 --port 8000 --http httptools

Get Summary
curl "http://localhost:8000/summary/?query=What%20is%20the%20main%20topic?"
Stream Response


curl -N "http://localhost:8000/summary/?query=Explain%20quantum%20computing
