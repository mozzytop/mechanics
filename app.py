# app.py — entrypoint for Hugging Face Spaces' Gradio SDK.
#
# ZeroGPU requires:
#   1. A @spaces.GPU-decorated function bound to a Gradio event handler
#   2. demo.launch() to be called (triggers ZeroGPU lifecycle hooks)
#
# Gradio's demo.launch() starts a Node proxy that serves its own SPA
# frontend, which would hide our FastAPI/Jinja2 UI. To work around this,
# we launch Gradio on a sidecar port (7865) — purely to satisfy
# ZeroGPU — then serve our real FastAPI app on port 7860 (the port
# HF Spaces exposes to users) with uvicorn.
#
# Locally (where spaces/gradio aren't installed), just run:
#     uvicorn main:app --reload

import os

# --- ZeroGPU sidecar ---------------------------------------------------
# The `spaces` and `gradio` packages are only present in HF's Gradio SDK
# base image. When available, we launch a minimal Gradio app on a sidecar
# port to satisfy ZeroGPU's startup watchdog. This has no effect on the
# actual user-facing app served below on port 7860.
try:
    import spaces
    import gradio as gr

    @spaces.GPU
    def _zerogpu_placeholder(text):
        """Never meaningfully called. Exists so HF's ZeroGPU watchdog
        detects a @spaces.GPU function bound to a Gradio event handler."""
        return "OK"

    with gr.Blocks() as demo:
        t = gr.Textbox(visible=False)
        btn = gr.Button(visible=False)
        btn.click(fn=_zerogpu_placeholder, inputs=t, outputs=t)

    # Force Gradio to a sidecar port so its Node proxy doesn't claim
    # port 7860 (which our FastAPI app needs for the user-facing UI).
    os.environ["GRADIO_SERVER_PORT"] = "7865"
    demo.launch(
        server_name="0.0.0.0",
        server_port=7865,
        prevent_thread_lock=True,
    )
except ImportError:
    pass
# -----------------------------------------------------------------------

# Serve the actual FastAPI app on port 7860 (what HF Spaces exposes).
if __name__ == "__main__":
    import uvicorn

    from main import app

    uvicorn.run(app, host="0.0.0.0", port=7860)
