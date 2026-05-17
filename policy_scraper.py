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
HTML_FILE = "index.html"

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
                    "content": """
당신은 통신, 주파수(Spectrum), 방송, IT 정책 분야 전문 번역가입니다.

[번역 원칙]
1. 영어 원문 전체를 한국어로 완전 번역합니다.
2. 절대 요약, 생략, 재구성, bullet 변환하지 않습니다.
3. 기사/리포트/정책 보고서에 적합한 자연스러운 한국어 문체로 번역합니다.
4. 직역보다 의미 전달과 업계 용어 일관성을 우선합니다.
5. 인용문, 숫자, 날짜, MHz/GHz, %, 기간, 회사명, 기관명은 정확히 유지합니다.

[용어 규칙]
- reserve price = 최저입찰가
- coverage obligations = 망 구축 의무
- regional operators = 지역 사업자
- nationwide operators = 전국 사업자
- licences/licensees = 주파수 이용권 / 이용권자
- deployment = 망 구축
- auction = 경매
- spectrum = 주파수
- spectrum allocation = 주파수 할당
- fourth operator = 제4 사업자

[출력 규칙]
- 번역문만 출력합니다.
- 설명, 주석, '다음은 번역입니다' 같은 문구를 절대 추가하지 않습니다.
"""
                },
                {
            "role": "user",
            "content": f"다음 영문 기사 전문을 한국어 기사체로 번역하세요.\n\n{text}"
                }
            ],
            temperature=0.2,
            max_tokens=16000,
            top_p=1
        )
        time.sleep(1)
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
# 5. HTML 목록형 대시보드 렌더링 (새 창 열기 버전)
# ==========================================
def generate_html_dashboard(db_data):
    rows_html = ""
    hidden_contents = "" # 새 창에 띄울 본문 데이터를 숨겨둘 변수
    
    for idx, item in enumerate(db_data):
        # 줄바꿈 처리
        sum_ko = item['summary_ko'].replace('\n', '<br>')
        txt_en = item['full_text_en'].replace('\n', '<br><br>')
        txt_ko = item['full_text_ko'].replace('\n', '<br><br>')
        
        # 1. 목록 행 (클릭 시 openNewWindow 함수 실행)
        rows_html += f"""
        <tr class="item-row" onclick="openNewWindow('article-{idx}')">
            <td class="col-date">{item['date'][:16]}</td>
            <td class="col-title">
                <strong>{item['title_ko']}</strong><br>
                <span class="en-title">{item['title_en']}</span>
            </td>
            <td class="col-summary">{sum_ko}</td>
        </tr>
        """
        
        # 2. 새 창에 띄울 내용 (화면에는 보이지 않게 display:none 으로 숨겨둠)
        # 새 창에서도 예쁘게 보이도록 인라인 스타일(style)을 적용했습니다.
        hidden_contents += f"""
        <div id="article-{idx}" style="display: none;">
            <div style="max-width: 900px; margin: 0 auto; font-family: 'Malgun Gothic', sans-serif; color: #333; line-height: 1.7;">
                <h2 style="color: #2c3e50; border-bottom: 2px solid #34495e; padding-bottom: 10px; line-height: 1.4;">{item['title_ko']}</h2>
                <p style="color: #7f8c8d; font-size: 0.9em; margin-bottom: 30px;">발행일: {item['date']}</p>
                
                <div style="background: #f8fafc; padding: 25px; border-radius: 8px; border: 1px solid #cbd5e1; margin-bottom: 30px;">
                    <span style="background-color: #2980b9; color: white; padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">🇰🇷 한국어 번역 본문</span>
                    <div style="margin-top: 15px; font-size: 1.05em; color: #1a202c;">{txt_ko}</div>
                </div>
                
                <div style="background: #ffffff; padding: 25px; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <span style="background-color: #7f8c8d; color: white; padding: 5px 12px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">🇬🇧 영문 원본 본문</span>
                    <div style="margin-top: 15px; font-size: 0.95em; color: #4a5568;">{txt_en}</div>
                </div>
            </div>
        </div>
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
            
            /* 목록 호버 시 클릭할 수 있다는 시각적 효과 부여 */
            .item-row {{ cursor: pointer; transition: background 0.2s; }}
            .item-row:hover {{ background-color: #e2e8f0; }}
            .item-row:hover .col-title strong {{ color: #2980b9; text-decoration: underline; }}
        </style>
        <script>
            // 클릭 시 새 창(새 탭)을 열고 숨겨둔 본문을 그려주는 마법의 함수
            function openNewWindow(articleId) {{
                var content = document.getElementById(articleId).innerHTML;
                var newWin = window.open('', '_blank');
                newWin.document.open();
                newWin.document.write('<html><head><title>기사 상세 본문</title></head><body style="background-color: #f4f6f9; padding: 40px;">' + content + '</body></html>');
                newWin.document.close();
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
                        <th class="col-title">기사 제목 (클릭하면 새 창에서 열립니다)</th>
                        <th class="col-summary">핵심 요약</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
        
        <div id="hidden-data">
            {hidden_contents}
        </div>
    </body>
    </html>
    """
    
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_template)
    print(f"✅ 대시보드 업데이트 완료! '{HTML_FILE}' 파일이 생성되었습니다.")

if __name__ == "__main__":
    update_dashboard()
