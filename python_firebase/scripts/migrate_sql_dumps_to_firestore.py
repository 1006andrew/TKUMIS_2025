#!/usr/bin/env python3

# python -m scripts.migrate_sql_dumps_to_firestore
# https://console.cloud.google.com/firestore

"""
直接從 MySQL dump 文字檔 (INSERT INTO ... VALUES ...) 解析後灌入 Firestore。
不需連 MySQL DB。

預設會讀專案根目錄下的：
- natural_beauty_client.sql
- natural_beauty_product.sql
- natural_beauty_user_purchase_record.sql

你也可以用參數指定檔案路徑：
python scripts/migrate_sql_dumps_to_firestore.py \
  --client-sql data/natural_beauty_client.sql \
  --product-sql data/natural_beauty_product.sql \
  --upr-sql data/natural_beauty_user_purchase_record.sql
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from datetime import datetime, date
from typing import List, Any, Dict, Tuple

from google.cloud import firestore
from src.firebase.init_firebase import get_db

BATCH_SIZE = 400  # Firestore 單批上限 500，預留空間

# ---------- SQL 解析工具 ----------

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _split_records(values_blob: str) -> List[str]:
    """
    將 "(...),(...) ,(...)" 這種 values 片段拆成每一筆 "(...)"
    使用狀態機以避免在字串中的逗號誤切。
    回傳不含外層空白的片段字串（仍含左右括號）。
    """
    parts = []
    buf = []
    depth = 0
    in_str = False
    esc = False

    for ch in values_blob:
        buf.append(ch)

        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
            elif ch == "'":
                in_str = False
        else:
            if ch == "'":
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    # 結束一筆
                    parts.append("".join(buf).strip())
                    buf = []
            elif ch == ",":
                # 只有在 depth==0 時才是多筆之間的逗號
                if depth == 0:
                    buf = []

    return parts

def _split_fields(record_blob: str) -> List[str]:
    """
    將單筆 "(a,'b',NULL,3.14)" 內容拆成欄位
    回傳的每個元素仍是字串 literal（含或不含引號），後續再做型別轉換。
    """
    assert record_blob.startswith("(") and record_blob.endswith(")"), "record blob must be like '(...)'"
    s = record_blob[1:-1]  # 去掉外層括號

    fields = []
    buf = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
            elif ch == "'":
                in_str = False
        else:
            if ch == "'":
                in_str = True
                buf.append(ch)
            elif ch == ",":
                fields.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
    if buf:
        fields.append("".join(buf).strip())
    return fields

def mysql_unescape(s: str) -> str:
    """
    還原 MySQL 字串常見跳脫：\\0 \\b \\n \\r \\t \\Z \\\\ \\' \\"
    不做任何 re-encode / decode，保留原 UTF-8 內容。
    """
    mapping = {
        r"\0": "\x00",
        r"\b": "\b",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
        r"\Z": "\x1a",
        r"\\": "\\",
        r"\'": "'",
        r"\"": '"',
    }
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            two = s[i:i+2]
            if two in mapping:
                out.append(mapping[two])
                i += 2
                continue
        out.append(s[i])
        i += 1
    return "".join(out)

def _parse_literal(lit: str):
    """
    '文字' -> str（用 mysql_unescape 還原跳脫）
    NULL   -> None
    其他   -> int/float（失敗就保持字串）
    """
    # NULL
    if lit.upper() == "NULL":
        return None

    # 單引號字串
    if len(lit) >= 2 and lit[0] == "'" and lit[-1] == "'":
        body = lit[1:-1]          # 去引號
        body = mysql_unescape(body)
        return body               # ★ 不再做 unicode_escape 等再解碼

    # 數字
    try:
        return float(lit) if "." in lit else int(lit)
    except ValueError:
        return lit



def extract_values(sql: str, table_name: str) -> List[List[Any]]:
    """
    從整份 SQL 文字中，找到 INSERT INTO `table_name` VALUES (...) 的所有段落，
    解析後回傳每一筆的欄位 list。
    """
    results: List[List[Any]] = []
    needle = f"INSERT INTO `{table_name}` VALUES"
    start = 0
    while True:
        idx = sql.find(needle, start)
        if idx == -1:
            break
        # 從 needle 後面開始，找到結尾的 ';'
        semi = sql.find(";", idx)
        if semi == -1:
            raise ValueError(f"INSERT statement for {table_name} not terminated by ';'")
        values_blob = sql[idx + len(needle):semi].strip()
        # 移除開頭可能的空白
        # 解析每一筆
        records = _split_records(values_blob)
        for rec in records:
            fields = _split_fields(rec)
            parsed = [_parse_literal(f) for f in fields]
            results.append(parsed)
        start = semi + 1
    return results

# ---------- 專案資料模型對應 ----------

def rows_from_client_sql(sql_text: str) -> List[Dict[str, Any]]:
    """
    client: (client_id, name, gender, age, username, password)
    -> Firestore: clients/{client_id}
    """
    out = []
    for fields in extract_values(sql_text, "client"):
        (client_id, name, gender, age, username, password) = fields
        out.append({
            "id": str(client_id),
            "name": str(name),
            "gender": str(gender),
            "age": int(age),
            "username": str(username),
            "password": str(password),
        })
    return out

def rows_from_product_sql(sql_text: str) -> List[Dict[str, Any]]:
    """
    product: (product_id, order_no, product_name, description, price_min, price_max)
    -> Firestore: products/{product_id}
    """
    out = []
    for fields in extract_values(sql_text, "product"):
        (pid, order_no, product_name, description, price_min, price_max) = fields
        out.append({
            "id": str(pid),
            "order_no": str(order_no),
            "product_name": str(product_name),
            "description": (None if description is None else str(description)),
            "price_min": float(price_min),
            "price_max": (None if price_max is None else float(price_max)),
        })
    return out

def rows_from_upr_sql(sql_text: str) -> List[Dict[str, Any]]:
    """
    user_purchase_record:
    (record_id, client_id, product_id, order_date, quantity, amount)
    -> Firestore: purchase_records/{record_id}
    """
    out = []
    for fields in extract_values(sql_text, "user_purchase_record"):
        (rid, cid, pid, order_date, qty, amount) = fields
        # order_date 可能是 'YYYY-MM-DD' 字串
        if isinstance(order_date, str):
            y, m, d = [int(x) for x in order_date.split("-")]
            dt = datetime(y, m, d)
        elif isinstance(order_date, date):
            dt = datetime(order_date.year, order_date.month, order_date.day)
        else:
            raise ValueError(f"Unsupported date literal: {order_date!r}")

        out.append({
            "id": str(rid),
            "client_id": int(cid),
            "product_id": int(pid),
            "order_date": dt,  # Firestore 會存成 Timestamp
            "quantity": int(qty),
            "amount": float(amount),
        })
    return out

# ---------- Firestore 寫入 ----------

def batch_upsert(db: firestore.Client, collection: str, rows: List[Dict[str, Any]]):
    now = datetime.utcnow()
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i:i + BATCH_SIZE]
        batch = db.batch()
        for row in chunk:
            doc_id = row["id"]
            data = dict(row)
            data.pop("id", None)
            # 打上時間欄位
            data.setdefault("created_at", now)
            data["updated_at"] = now
            ref = db.collection(collection).document(doc_id)
            batch.set(ref, data, merge=True)
        batch.commit()
        print(f"[{collection}] committed {i + len(chunk)}/{len(rows)}")

def migrate_from_sql_texts(client_sql: str, product_sql: str, upr_sql: str):
    db = get_db()

    print("Parsing client dump ...")
    clients = rows_from_client_sql(client_sql)
    print(f"found {len(clients)} clients")
    batch_upsert(db, "clients", clients)

    print("Parsing product dump ...")
    products = rows_from_product_sql(product_sql)
    print(f"found {len(products)} products")
    batch_upsert(db, "products", products)

    print("Parsing user_purchase_record dump ...")
    uprs = rows_from_upr_sql(upr_sql)
    print(f"found {len(uprs)} purchase records")
    batch_upsert(db, "purchase_records", uprs)

# =================================================================================================================================
def clear_collection(db, collection: str, batch_size: int = 500):
    print(f"Clearing collection: {collection}")
    ref = db.collection(collection)
    docs = ref.limit(batch_size).stream()
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    if deleted:
        clear_collection(db, collection, batch_size)

    # parser = argparse.ArgumentParser(...)
    # parser.add_argument("--reset", action="store_true", help="清空 collection 後再重新寫入")
    # args = parser.parse_args()

    # db = get_db()
    # if args.reset:
    #     for col in ["clients", "products", "purchase_records"]:
    #         clear_collection(db, col)
# =================================================================================================================================

def main():
    script_dir = Path(__file__).resolve().parent
    # print("script_dir :",script_dir)
    file_path1 = script_dir / "natural_beauty_client.sql"
    # print("file_path1 :",file_path1)
    file_path2 = script_dir / "natural_beauty_product.sql"
    file_path3 = script_dir / "natural_beauty_user_purchase_record.sql"

    # 讀檔
    client_sql = read_text(file_path1)
    product_sql = read_text(file_path2)
    upr_sql = read_text(file_path3)

    migrate_from_sql_texts(client_sql, product_sql, upr_sql)
    print("Migration completed successfully.")


if __name__ == "__main__":
    main()
    # script_dir = Path(__file__).resolve().parent
    # txt = (script_dir / "natural_beauty_client.sql").read_text(encoding="utf-8")
    # print(rows_from_client_sql(txt)[0])
