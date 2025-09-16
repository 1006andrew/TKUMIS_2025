# uvicorn app:app --host 127.0.0.1 --port 8000 --reload

# ngrok http 8000 啟動

from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import json
import requests
import logging
from opencc import OpenCC
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from openai import OpenAI

# 初始化 FastAPI
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 中文簡繁轉換
cc_t2s = OpenCC('t2s')
cc_s2t = OpenCC('s2t')

# 接收前端問題的格式


class QuestionRequest(BaseModel):
    question: str

# 讀取 JSON 並轉為文本段落


def read_json_text(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_json_entries(data):
    chunks = []
    for entry in data:
        block = f"膚質類型：{entry['skin_type']}\n"
        for c in entry.get("recommended_courses", []):
            block += f"療程：{c['name']}\n功效：{'、'.join(c.get('goals', []))}\n"
        for p in entry.get("products", []):
            block += f"產品：{p['name']}（{p['step']}）\n特色：{'；'.join(p.get('features', []))}\n"
        block += f"推薦話術：{entry.get('reply_template', '')}"
        chunks.append(block)
    return chunks


def embed_chunks(chunks, model):
    return model.encode(chunks)


def retrieve_top_k_chunks(query, chunks, embeddings, embed_model, k=3):
    query_embedding = embed_model.encode([query])
    sims = cosine_similarity(query_embedding, embeddings)[0]
    top_indices = np.argsort(sims)[-k:][::-1]
    return [chunks[i] for i in top_indices]


def query_ollama(context, question, model_name="llama3.1:8b"):
    messages = [{"role": "system", "content": """你是一位經驗豐富、溫柔且親切的皮膚護理顧問，擅長提供專業且易懂的建議。 請嚴格根據【參考資料】和使用者最新的問題，來生成你的回答。 你的回答必須遵循以下規則： 1. **結構化與簡潔性**：回答必須以條列式呈現（使用 1. 2. 3. ...）。 2. **內容來源**：回答內容**嚴格限於【參考資料】內**，不得憑空創造任何不存在的產品、療程或資訊。 3. **回答模式**： - **當使用者詢問產品或療程類型（例如：美白、保濕）時**： - 列出相關產品或療程的**名稱**即可。 - 例如： 美白： 1. 煥白透亮臉部課程 2. 嫩白無暇精華液 3. ... - **當使用者詢問具體的產品或療程（例如：某某課程有什麼特色？）時**： - 詳細列出該產品或療程的**重點特色**，每項不超過三點。 - 例如： 煥白透亮臉部課程： 1. 有效改善肌膚暗沉，恢復光澤。 2. 提升肌膚水潤度，減少細紋。 3. 舒緩敏感肌膚。 4. **語言與格式**：所有回答都必須使用**繁體中文**，並且**不包含任何開場白或結語**。 """}, {"role": "user", "content": f""" 【參考資料】 {context} 【使用者最新問題】 {question} """}]
    try:
        res = requests.post("http://localhost:11434/api/chat", json={
            "model": model_name,
            "messages": messages,
            "stream": False
        })
        res.raise_for_status()
        return res.json()["message"]["content"]
    except Exception as e:
        logging.error(f"Ollama 錯誤：{e}")
        return f"⚠️ 發生錯誤：{str(e)}"

def query_openai(context, question, model_name="gpt-4o-mini"):
    """
    使用 OpenAI ChatCompletion API 進行回答
    """
    messages = [
        {
            "role": "system",
            "content": """
                    你是一位經驗豐富、溫柔且親切的皮膚護理顧問，
                    擅長提供專業且易懂的建議。
                    請嚴格根據【參考資料】和使用者最新的問題，來生成你的回答。
                    你的回答必須遵循以下規則：
                    1. **結構化與簡潔性**：回答必須以條列式呈現（使用 1. 2. 3. ...）。
                    2. **內容來源**：回答內容**嚴格限於【參考資料】內**，不得憑空創造任何不存在的產品、療程或資訊。
                    3. **回答模式**：
                        - **當使用者詢問產品或療程類型（例如：美白、保濕）時**：
                            - 列出相關產品或療程的**名稱**即可。
                        - **當使用者詢問具體的產品或療程（例如：某某課程有什麼特色？）時**：
                            - 詳細列出該產品或療程的**重點特色**，每項不超過三點。
                    4. **語言與格式**：所有回答都必須使用**繁體中文**，並且**不包含任何開場白或結語**。
        """
        },
        {
            "role": "user",
            "content": f"【參考資料】 {context}\n【使用者最新問題】 {question}"
        }
    ]

    try:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"OpenAI API 錯誤：{e}")
        return f"⚠️ OpenAI API 發生錯誤：{str(e)}"

# 預載模型與資料
print("🔄 載入資料與模型...")
data = read_json_text("skincare_data.json")
chunks = flatten_json_entries(data)
embed_model = SentenceTransformer("all-MiniLM-L6-v2")
chunk_embeddings = embed_chunks(chunks, embed_model)
print("✅ 初始化完成！")

# 📌 前端首頁


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 📌 查詢 API（供 JS 使用）


@app.post("/chat")
def chat(request: QuestionRequest):
    question_trad = request.question
    question_simp = cc_t2s.convert(question_trad)

    # 檢索相關內容
    top_chunks = retrieve_top_k_chunks(
        question_simp, chunks, chunk_embeddings, embed_model)
    context = "\n---\n".join(top_chunks)

    # 查詢 Ollama
    answer_simp = query_ollama(context, question_trad)
    answer_trad = cc_s2t.convert(answer_simp)

    return {"answer": answer_trad}

from pyngrok import ngrok

if __name__ == "__main__":
    import uvicorn
    # # 開一個 ngrok 通道
    # public_url = ngrok.connect(8000)
    # print("🌍 Public URL:", public_url)
    # 啟動 FastAPI
    uvicorn.run(app, host="0.0.0.0", port=8000)