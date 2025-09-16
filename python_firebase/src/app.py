# python -m fastapi dev src/app.py --port 8000
# http://127.0.0.1:8000/admin/clients
# http://127.0.0.1:8000/skintest

# src/app.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web.routes import router as web_router
from src.admin.router import router as admin_router, mount_static as mount_admin_static
from src.api.chatbot import setup as setup_chatbot
from src.api.auth_google.router import router as google_auth_router
from src.api.skintest.router import router as skintest_router
from src.api.auth import router as auth_router
from src.api.personal_page.router import router as personal_page_router
from src.api.booking.router import router as bookings_router

app = FastAPI(title="Python Firebase Project")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載 Chatbot（含啟動時載入 embedding）
setup_chatbot(app)

# 靜態資源
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")
mount_admin_static(app)     # /admin-static

# 掛載 API router
app.include_router(skintest_router)
app.include_router(auth_router)
app.include_router(google_auth_router)
app.include_router(admin_router)
app.include_router(personal_page_router)   # ✅ 一定要在 web_router 之前
app.include_router(bookings_router)

# 設定模板 (HTML)
templates = Jinja2Templates(directory="src/web/templates")

@app.get("/skintest")
async def skintest_page(request: Request):
    return templates.TemplateResponse("skintest/index.html", {"request": request})

# 健康檢查
@app.get("/health")
def health():
    return {"status": "ok"}

# 前台兜底路由
app.include_router(web_router)    # ✅ 放最後