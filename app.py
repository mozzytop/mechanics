# app.py — entrypoint for Hugging Face Spaces' Gradio SDK.
#
# ZeroGPU requires:
#   1. A @spaces.GPU-decorated function bound to a Gradio event handler
#   2. The server to be started via demo.launch() (not raw uvicorn.run()),
#      because ZeroGPU's watchdog hooks into Gradio's launch lifecycle
#
# On HF Spaces, we:
#   - Create a minimal hidden Gradio Blocks with a @spaces.GPU placeholder
#   - Call demo.launch() to start the server (satisfies ZeroGPU)
#   - Add our FastAPI routes to Gradio's internal FastAPI app afterward
#
# Locally (where spaces/gradio aren't installed), we just run the
# FastAPI app with uvicorn as usual:
#     uvicorn main:app --reload

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

    # Launch Gradio — this starts the server on port 7860 and satisfies
    # ZeroGPU's startup check. prevent_thread_lock=True returns control
    # so we can add our FastAPI routes to Gradio's internal app.
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        prevent_thread_lock=True,
    )

    # Gradio's internal FastAPI app is now available as demo.app.
    # Add our routes, static files, and initialize the database so all
    # existing endpoints (/, /codes, /garage, /static/*) work exactly
    # as before — served through Gradio's server on port 7860.
    from fastapi.staticfiles import StaticFiles

    from app.database import init_db
    from app.routers import codes, garage, lookup

    demo.app.mount("/static", StaticFiles(directory="app/static"), name="static")
    demo.app.include_router(lookup.router)
    demo.app.include_router(codes.router)
    demo.app.include_router(garage.router)

    init_db()

    # Keep the process alive — Gradio's server runs in a background thread.
    import threading
    threading.Event().wait()

except ImportError:
    # Local dev — no spaces/gradio installed, just run FastAPI with uvicorn.
    if __name__ == "__main__":
        import uvicorn

        from main import app

        uvicorn.run(app, host="0.0.0.0", port=7860)

