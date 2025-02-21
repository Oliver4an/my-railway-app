import requests
import re
import json
import groq  # 使用 Groq API 取代 OpenAI API
import os
from flask import Flask, request

app = Flask(__name__)


GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")


# Notion API Headers
headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def get_page_content(page_id):
    """ 讀取 Notion Page 內的內容 """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    response = requests.get(url, headers=headers)
    data = response.json()

    print("🔍 Notion API 回應:", data)  # Debug API 回傳的內容

    if "results" not in data:
        print("❌ 'results' 不存在，API 回傳錯誤！")
        return None

    content = []
    for block in data["results"]:
        print("📌 Block 內容:", block)  # Debug: 檢查每個 Block

        if block["type"] == "paragraph":
            # 檢查 rich_text 是否為空
            if not block["paragraph"]["rich_text"]:
                print("⚠️ 該段落沒有內容，跳過！")
                continue

            content.append(block["paragraph"]["rich_text"][0]["text"]["content"])

    return "\n".join(content)  # 合併為完整文章



def correct_grammar(text):
    """ 使用 Groq LLaMA 3 / Mixtral 修正文法，並拆分回應 """
    client = groq.Client(api_key=GROQ_API_KEY)

    prompt = f"""
    這是我的英文短文，請幫我：
    1️⃣ 修正所有文法錯誤，並輸出為「[修正文] 修正後的短文」。
    2️⃣ 根據托福考試評分標準，提供「[錯誤分析] 錯誤分析」。
    3️⃣ 提供「[高分建議] 如何提升文章品質」並提出具體改進建議及更自然的詞彙或句型,每個建議至少提供一個例句。
    
    我的文章：
    {text}
    """

    response = client.chat.completions.create(
        model="mixtral-8x7b-32768",  # ✅ Groq 支援的模型
        messages=[{"role": "system", "content": "You are a helpful assistant."},
                  {"role": "user", "content": prompt}]
    )

    gpt_response = response.choices[0].message.content.strip().split("\n\n")

    print("🔍 Groq 回應內容:", gpt_response)  # ✅ Debug 看看結果

    if len(gpt_response) < 3:
        return "錯誤：Groq 回應格式異常", "", ""

    corrected_text = gpt_response[0]  # 修正後短文
    error_analysis = gpt_response[1]  # 錯誤分析
    high_score_tips = gpt_response[2]  # 高分建議

    return corrected_text, error_analysis, high_score_tips 
    
def extract_section(text, section_name):
    """ 解析 GPT 回應，提取指定標題的內容 """
    pattern = rf"{section_name}([\s\S]+?)(?=\n\[|\Z)"  # 匹配標題後面的內容
    match = re.search(pattern, text)

    if match:
        return match.group(1).strip()
    return "⚠️ 無法解析此部分"

def clean_text(text):
    """ 移除 [錯誤分析] [修正文] [高分建議] 這類標題 """
    return re.sub(r"\[.*?\]", "", text).strip()  # 🔥 移除方括號內的內容

def update_notion_page(row_page_id, corrected_text, error_analysis, high_score_tips):
    """ 更新 Notion Database 內 **特定 row** 的內容 """

    # 🔥 先清理標題，確保寫入 Notion 前沒有 [錯誤分析] 這類字
    corrected_text = clean_text(corrected_text)
    error_analysis = clean_text(error_analysis)
    high_score_tips = clean_text(high_score_tips)

    print("✅ 修正後短文:", corrected_text)
    print("✅ 錯誤分析:", error_analysis)
    print("✅ GPT 高分建議:", high_score_tips)

    url = f"https://api.notion.com/v1/pages/{row_page_id}"

    notion_data = {
        "properties": {
            "GPT 修正後短文": {"rich_text": [{"text": {"content": corrected_text}}]},  # ✅ 修正文
            "錯誤分析 ": {"rich_text": [{"text": {"content": error_analysis}}]},  # ✅ 錯誤分析
            "GPT 高分建議": {"rich_text": [{"text": {"content": high_score_tips}}]}  # ✅ 高分建議
        }
    }

    response = requests.patch(url, headers=headers, json=notion_data)
    print("🔍 Notion API 更新回應:", response.status_code, response.text)  # ✅ Debug API

    
@app.route('/trigger-python', methods=['GET', 'POST'])
def trigger_python():
    text_page_id = request.args.get('text_page_id')  # 讀取短文庫的 Page ID
    row_page_id = request.args.get('row_page_id')    # 讀取 Notion Database 的 row ID

    if not text_page_id or not row_page_id:
        return "❌ 缺少必要的 Page ID", 400

    # 讀取 Notion Page 內容（短文庫）
    content = get_page_content(text_page_id)
    if not content:
        return "❌ 短文庫內沒有內容", 400
    print("📌 原始文章內容:", content)

    # 送 GPT 批改，獲取 3 個回應
    corrected_text, error_analysis, high_score_tips = correct_grammar(content)

    # 回寫 Notion Database（對應的 row）
    update_notion_page(row_page_id, corrected_text, error_analysis, high_score_tips)

    # 自動關閉視窗並跳回 Notion
    return '''
    <html>
    <script>
        function goToNotion() {
            window.location.href = "notion://";  // 嘗試開啟 Notion App

            // 延遲 3 秒後關閉網頁，確保有時間按「開啟 Notion」
            setTimeout(() => { 
                window.close();  
            }, 3000);  // 3 秒後關閉，時間可調整
        }
    </script>

    <body>
        ✅ Flask 批改完成！結果已回寫到 Notion！
        <br><br>
        <a id="notion-link" href="notion://" onclick="goToNotion()">👉 點這裡回 Notion</a>
    </body>
    </html>
    ''', 200
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
