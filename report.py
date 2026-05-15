import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from datetime import datetime
import json
import os
import time

# ==========================================
# 1. 설정 및 OpenAI 연동
# ==========================================
RSS_URL = "https://www.policytracker.com/feed/"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# 🔥 발급받은 OpenAI API 키를 입력하세요.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# 누적 데이터를 저장할 파일명
DB_FILE = "policy_db.json"
# 최종 생성될 HTML 대시보드 파일명
HTML_FILE = "PolicyTracker_Dashboard.html"

# ==========================================
# 2. 데이터베이스(JSON) 관리 함수
# ==========================================
def load_db():
    """기존에 저장된 기사 목록을 불러옵니다."""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_db(data):
    """기사 목록을 파일로 저장합니다."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ==========================================
# 3. GPT 번역 함수
# ==========================================
def gpt_translate(text):
    if not text or len(text.strip()) == 0:
        return "본문이 없습니다."
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "당신은 통신, 주파수(Spectrum), IT 정책 분야의 전문 번역가입니다. "
                               "다음 영문을 한국어로 자연스럽게 번역하되, 전문 용어를 정확하게 반영하세요. "
                               "글자 수가 길어도 절대 요약하거나 중략하지 말고 전체를 번역하세요."
                },
                {"role": "user", "content": text}
            ],
            temperature=0.3
        )
        time.sleep(1) # API 과부하 방지
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 번역 중 오류 발생: {e}"

# ==========================================
# 4. 메인 실행 로직 (새 기사 확인 및 업데이트)
# ==========================================
def update_dashboard():
    print(f"[{datetime.now()}] 새로운 기사 업데이트를 시작합니다...")
    
    # 1. 기존 데이터 불러오기
    db = load_db()
    existing_titles = [item['title_en'] for item in db]
    
    # 2. RSS 피드 가져오기
    res = requests.get(RSS_URL, headers=HEADERS)
    if res.status_code != 200:
        print("페이지를 불러오는데 실패했습니다.")
        return

    soup = BeautifulSoup(res.content, 'xml')
    articles = soup.find_all('item')
    
    new_articles = []
    
    # 3. 새로운 기사만 걸러서 번역하기
    for art in articles:
        title_en = art.title.text.strip() if art.title else "제목 없음"
        
        # 이미 수집된 기사면 패스 (새로운 것만 찾음)
        if title_en in existing_titles:
            continue
            
        print(f"✨ [새로운 기사 발견] 번역 중... : {title_en}")
        date_raw = art.pubDate.text.strip() if art.pubDate else "날짜 없음"
        
        desc_tag = art.description
        summary_en = BeautifulSoup(desc_tag.text, 'html.parser').text.strip() if desc_tag else "요약 없음"
        
        content_tag = art.find('content:encoded')
        full_text_en = BeautifulSoup(content_tag.text, 'html.parser').text.strip() if content_tag else summary_en
        
        # GPT 번역 실행
        title_ko = gpt_translate(title_en)
        summary_ko = gpt_translate(summary_en)
        full_text_ko = gpt_translate(full_text_en)
        
        # 데이터 딕셔너리로 묶기
        article_data = {
            "title_en": title_en,
            "title_ko": title_ko,
            "date": date_raw,
            "summary_en": summary_en,
            "summary_ko": summary_ko,
            "full_text_en": full_text_en,
            "full_text_ko": full_text_ko
        }
        new_articles.append(article_data)

    if not new_articles:
        print("✅ 새로 추가된 기사가 없습니다. 최신 상태입니다.")
    else:
        # 4. 새로운 기사를 목록의 맨 앞에(최상단) 추가하고 저장
        db = new_articles + db 
        save_db(db)
        print(f"✅ {len(new_articles)}개의 새 기사가 DB에 추가되었습니다.")

    # 5. HTML 대시보드 화면 생성
    generate_html_dashboard(db)

# ==========================================
# 5. HTML 목록형 대시보드 렌더링
# ==========================================
def generate_html_dashboard(db_data):
    rows_html = ""
    for idx, item in enumerate(db_data):
        # 줄바꿈 처리
        sum_ko = item['summary_ko'].replace('\n', '<br>')
        txt_en = item['full_text_en'].replace('\n', '<br><br>')
        txt_ko = item['full_text_ko'].replace('\n', '<br><br>')
        
        rows_html += f"""
        <tr class="item-row" onclick="toggleDetails('detail-{idx}')">
            <td class="col-date">{item['date'][:16]}</td>
            <td class="col-title">
                <strong>{item['title_ko']}</strong><br>
                <span class="en-title">{item['title_en']}</span>
            </td>
            <td class="col-summary">{sum_ko}</td>
        </tr>
        <tr id="detail-{idx}" class="detail-row" style="display: none;">
            <td colspan="3">
                <div class="content-wrapper">
                    <div class="content-box">
                        <div class="box-label ko-label">🇰🇷 한국어 번역 본문</div>
                        {txt_ko}
                    </div>
                    <div class="content-box">
                        <div class="box-label en-label">🇬🇧 영문 원본 본문</div>
                        {txt_en}
                    </div>
                </div>
            </td>
        </tr>
        """

    html_template = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>PolicyTracker 동향 대시보드</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; background: #f4f6f9; padding: 30px; color: #333; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ color: #2c3e50; border-bottom: 3px solid #34495e; padding-bottom: 10px; margin-bottom: 30px; }}
            
            table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
            th, td {{ padding: 15px 20px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
            th {{ background-color: #34495e; color: white; font-size: 1.05em; }}
            
            .col-date {{ width: 15%; font-size: 0.85em; color: #7f8c8d; }}
            .col-title {{ width: 40%; font-size: 1.05em; }}
            .col-summary {{ width: 45%; font-size: 0.95em; color: #555; }}
            
            .en-title {{ font-size: 0.85em; color: #95a5a6; display: block; margin-top: 5px; }}
            
            /* 목록 호버 및 클릭 액션 */
            .item-row {{ cursor: pointer; transition: background 0.2s; }}
            .item-row:hover {{ background-color: #f8fafc; }}
            
            /* 세부 본문 영역 */
            .detail-row {{ background-color: #f1f5f9; }}
            .content-wrapper {{ display: flex; gap: 20px; padding: 10px; }}
            .content-box {{ flex: 1; background: white; padding: 25px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 0.95em; line-height: 1.7; }}
            
            .box-label {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 0.85em; margin-bottom: 15px; color: white; }}
            .ko-label {{ background-color: #2980b9; }}
            .en-label {{ background-color: #7f8c8d; }}
        </style>
        <script>
            // 클릭 시 세부 내용을 열고 닫는 자바스크립트 함수
            function toggleDetails(rowId) {{
                var row = document.getElementById(rowId);
                if (row.style.display === "none") {{
                    row.style.display = "table-row";
                }} else {{
                    row.style.display = "none";
                }}
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>📡 PolicyTracker 주간 누적 동향 목록</h1>
            <table>
                <thead>
                    <tr>
                        <th class="col-date">발행일</th>
                        <th class="col-title">기사 제목 (클릭하여 본문 보기)</th>
                        <th class="col-summary">핵심 요약</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"✅ 대시보드 업데이트 완료! '{HTML_FILE}' 파일을 열어보세요.")

if __name__ == "__main__":
    update_dashboard()