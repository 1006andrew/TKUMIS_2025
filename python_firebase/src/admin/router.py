from __future__ import annotations
from fastapi import APIRouter, Request, Depends, Form, Query, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette import status
from pathlib import Path

# 用你現有的 Repos
from src.api.db.repos import ClientsRepo, ProductsRepo, PurchaseRecordsRepo
from src.firebase.admin_service import set_admin

router = APIRouter(prefix="/admin", tags=["admin"])

# 建立這個模組自己的模板與靜態路徑
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 讓 main/app 掛載靜態時能使用（見下方 app.py 設定）
def mount_static(app):
    app.mount("/admin-static", StaticFiles(directory=str(STATIC_DIR)), name="admin-static")

# ====== 儀表板 ======
@router.get("")
def dashboard(req: Request):
    return templates.TemplateResponse("admin/index.html", {"request": req})

@router.get("/clients")
def list_clients(req: Request, limit: int = 20, cursor_after: str | None = None):
    data = ClientsRepo().list(limit=limit, cursor_after=cursor_after)
    return templates.TemplateResponse("admin/clients_list.html", {
        "request": req,
        "items": data["items"],
        "next_cursor": data["next_cursor"],
        "limit": limit,
    })

from fastapi.responses import JSONResponse
import json

# ✅ 新增：回傳 JSON 給前端 (Angular 用)
@router.get("/clients/json")
def list_clients_json(limit: int = 50, cursor_after: str | None = None):
    try:
        data = ClientsRepo().list(limit=limit, cursor_after=cursor_after)
        items = data["items"]

        # 🔥 Firestore Timestamp → str
        for item in items:
            for key, value in item.items():
                if hasattr(value, "isoformat"):
                    item[key] = value.isoformat()

        return JSONResponse(content=items, media_type="application/json")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/clients/{cid}")
def get_client(req: Request, cid: str):
    doc = ClientsRepo().get_by_id(cid)
    if not doc:
        raise HTTPException(404, "Client not found")
    return templates.TemplateResponse("admin/detail.html", {"request": req, "title": f"Client {cid}", "doc": doc})

@router.post("/clients/{cid}/delete")
def delete_client(cid: str):
    ClientsRepo().delete_one(cid)
    return RedirectResponse(url="/admin/clients", status_code=status.HTTP_303_SEE_OTHER)

# ====== Products ======
@router.get("/products")
def list_products(req: Request, limit: int = 20, cursor_after: str | None = None):
    data = ProductsRepo().list(limit=limit, cursor_after=cursor_after)
    return templates.TemplateResponse("admin/products_list.html", {
        "request": req,
        "items": data["items"],
        "next_cursor": data["next_cursor"],
        "limit": limit,
    })

@router.get("/products/{pid}")
def get_product(req: Request, pid: str):
    doc = ProductsRepo().get_by_id(pid)
    if not doc:
        raise HTTPException(404, "Product not found")
    return templates.TemplateResponse("admin/detail.html", {"request": req, "title": f"Product {pid}", "doc": doc})

@router.post("/products/{pid}/delete")
def delete_product(pid: str):
    ProductsRepo().delete_one(pid)
    return RedirectResponse(url="/admin/products", status_code=status.HTTP_303_SEE_OTHER)

# ====== Purchase Records ======
@router.get("/records")
def list_records(
    req: Request,
    client_id: int | None = Query(default=None, description="可選：依 client_id 篩選"),
    limit: int = 20,
    cursor_after: str | None = None,
):
    repo = PurchaseRecordsRepo()
    if client_id:
        data = repo.list_by_client(client_id=client_id, limit=limit, cursor_after=cursor_after)
    else:
        # 若沒指定 client_id，就列出最近的（這裡簡單用未過濾版本）
        data = repo.query(repo.col, order_by="order_date", direction="DESC", limit=limit, cursor_after=cursor_after)
    return templates.TemplateResponse("admin/records_list.html", {
        "request": req,
        "items": data["items"],
        "next_cursor": data["next_cursor"],
        "limit": limit,
        "client_id": client_id,
    })

@router.get("/records/{rid}")
def get_record(req: Request, rid: str):
    doc = PurchaseRecordsRepo().get_by_id(rid)
    if not doc:
        raise HTTPException(404, "Record not found")
    return templates.TemplateResponse("admin/detail.html", {"request": req, "title": f"Record {rid}", "doc": doc})

@router.post("/records/{rid}/delete")
def delete_record(rid: str):
    PurchaseRecordsRepo().delete_one(rid)
    return RedirectResponse(url="/admin/records", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/promote/{uid}")
async def promote_admin(uid: str):
    result = set_admin(uid)
    return {"status": "success", **result}