from app.kernel import ApplicationKernel


def main():
    kernel = ApplicationKernel()

    try:
        kernel.initialize()

        for tool in kernel.registry.list_tool_info():
            print(
                f"{tool['name']} "
                f"v{tool['version']} "
                f"- {tool['description']}"
            )

    finally:
        kernel.shutdown()


if __name__ == "__main__":
    main()


# import logging
# from pathlib import Path

# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import FileResponse
# from fastapi.staticfiles import StaticFiles

# from tools.video_downloader.router import router as video_downloader_router

# # --------------------------------------------------------------------------
# # Suppress status polling logs from uvicorn.access
# # --------------------------------------------------------------------------
# class EndpointLogFilter(logging.Filter):
#     def filter(self, record: logging.LogRecord) -> bool:
#         # Check if record has arguments (record.args holds method, path, etc.)
#         if record.args and len(record.args) >= 3:
#             path = str(record.args[2])
#             # Exclude status polling requests
#             if "/session/" in path and "/status" in path:
#                 return False
#         return True

# # Apply the filter to Uvicorn's access logger
# logging.getLogger("uvicorn.access").addFilter(EndpointLogFilter())
# # --------------------------------------------------------------------------

# BASE_DIR = Path(__file__).resolve().parent
# STATIC_DIR = BASE_DIR / "static"

# app = FastAPI(title="Multi-Tool App")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # Allows extension fetches
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# # Each tool contributes its own router. Adding a new tool later means:
# # 1. new_tool/router.py with its own APIRouter
# # 2. one include_router() line here
# # 3. one card in static/index.html
# # No other part of this file needs to change.
# app.include_router(video_downloader_router)

# app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


# @app.get("/")
# async def home():
#     return FileResponse(STATIC_DIR / "index.html")
