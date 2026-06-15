# -*- coding: utf-8 -*-
"""
금융감독원(FSS) 법규정보 게시판 감시 봇
- '최근 제개정 정보'와 '규정변경예고' 두 페이지를 확인
- 제목에 KEYWORD가 들어간 '새 글'을 텔레그램으로 알림
"""

import json
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────
KEYWORD = "금융투자업규정시행세칙"   # 감시할 제목 키워드

SITES = [
    {
        "name": "최근 제개정 정보",
        "url": "https://www.fss.or.kr/fss/job/lrgRegItnInfo/list.do?menuNo=200488",
    },
    {
        "name": "규정변경예고",
        "url": "https://www.fss.or.kr/fss/job/lrgRegItnPrvntc/list.do?menuNo=200489",
    },
]

STATE_FILE = Path(__file__).with_name("seen.json")   # 본 글 기록 파일

# 텔레그램 정보는 환경변수로 주입 (코드에 직접 적지 않는 걸 권장)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36"
}


# ──────────────────────────────────────────────
# 게시판 파싱
# ──────────────────────────────────────────────
def fetch_posts(site):
    """목록 페이지에서 (제목, 링크) 후보들을 뽑아낸다."""
    r = requests.get(site["url"], headers=HEADERS, timeout=20)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")

    # 본문 영역만 추리기 (없으면 전체)
    main = soup.find(id="mainContents") or soup

    posts = []
    # 게시판은 보통 <table>의 각 행(<tr>)이 글 하나다.
    for tr in main.select("table tr"):
        text = tr.get_text(" ", strip=True)
        if not text:
            continue
        # 행 안에 링크가 있으면 그 텍스트를 제목으로 우선 사용
        link_tag = tr.find("a")
        title = link_tag.get_text(strip=True) if link_tag else text
        if not title:
            continue
        posts.append(title)
    return posts


def make_id(site_name, title):
    """글을 구분하는 고유 키 (사이트명 + 제목)."""
    return f"{site_name}::{title}"


# ──────────────────────────────────────────────
# 상태 파일
# ──────────────────────────────────────────────
def load_seen():
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    STATE_FILE.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ──────────────────────────────────────────────
# 텔레그램 전송
# ──────────────────────────────────────────────
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[경고] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 설정되지 않았습니다.")
        print("보냈을 메시지:\n" + text)
        return
    api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(
        api,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        print("[텔레그램 오류]", resp.status_code, resp.text)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    seen = load_seen()
    first_run = len(seen) == 0
    new_found = False

    for site in SITES:
        try:
            posts = fetch_posts(site)
        except Exception as e:
            print(f"[{site['name']}] 가져오기 실패: {e}")
            continue

        for title in posts:
            if KEYWORD not in title:
                continue
            key = make_id(site["name"], title)
            if key in seen:
                continue

            seen.add(key)
            new_found = True

            # 최초 실행 때는 기존 글까지 한꺼번에 알리지 않도록 '기록만'
            if first_run:
                print(f"[최초 실행/기록] {key}")
                continue

            msg = (
                f"📢 [{site['name']}] 새 글 알림\n\n"
                f"{title}\n\n"
                f"🔗 {site['url']}"
            )
            print(f"[알림 전송] {key}")
            send_telegram(msg)

    save_seen(seen)

    if first_run:
        print("최초 실행 완료: 기존 글을 기록했습니다. 다음 실행부터 새 글만 알립니다.")
    elif not new_found:
        print("새 글 없음.")


if __name__ == "__main__":
    main()
