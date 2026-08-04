# app.py — entrypoint for Hugging Face Spaces' Gradio SDK.
#
# We're not actually using Gradio's UI. The Gradio SDK is just a
# convenient, free, non-Docker way to run an arbitrary Python web server on
# Spaces (Docker Spaces now require a verified payment method, even though
# CPU-basic usage itself is free). Spaces with the Gradio SDK run
# `python app.py` and expect the server on port 7860, so this file just
# boots our existing FastAPI app (from main.py) with uvicorn on that port.
#
# Run locally the normal way instead (this file is only needed for the
# Spaces deployment):
#     uvicorn main:app --reload

import uvicorn

from main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
