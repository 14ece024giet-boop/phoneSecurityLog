import uvicorn
import os
import sys

# Add server directory to pythonpath
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))

if __name__ == "__main__":
    print("[+] Starting Phone Security Cloud Server on http://127.0.0.1:8000 ...")
    print("[+] Security Dashboard available at: http://127.0.0.1:8000/dashboard")
    print("[+] API Documentation at: http://127.0.0.1:8000/docs")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, app_dir="server")

