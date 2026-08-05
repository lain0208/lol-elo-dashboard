import os
import requests
from dotenv import load_dotenv

# .env 파일에서 API 키 불러오기
load_dotenv(override=True)
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

# 💡 여기에 본인의 라이엇 닉네임과 태그를 적어주세요! (예: Hide on bush / KR1)
GAME_NAME = "Lain"
TAG_LINE = "KR1"

def get_recent_matches():
    if not RIOT_API_KEY:
        print("❌ API 키를 찾을 수 없습니다. .env 파일을 확인해주세요.")
        return

    print(f"🔍 [{GAME_NAME}#{TAG_LINE}] 님의 최근 매치 검색을 시작합니다...\n")

    # 1. 닉네임으로 PUUID(고유 식별자) 조회
    account_url = f"https://asia.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{GAME_NAME}/{TAG_LINE}"
    acc_res = requests.get(account_url, headers=HEADERS)
    
    if acc_res.status_code != 200:
        print(f"❌ 계정 조회 실패 (상태 코드: {acc_res.status_code}). 닉네임과 태그를 확인하세요.")
        return
        
    puuid = acc_res.json().get("puuid")

    # 2. PUUID를 바탕으로 최근 매치 ID 5개 가져오기
    match_url = f"https://asia.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=5"
    match_res = requests.get(match_url, headers=HEADERS)
    
    if match_res.status_code == 200:
        match_ids = match_res.json()
        print("✅ 최근 플레이한 5개의 진짜 매치 ID입니다:")
        for i, mid in enumerate(match_ids, 1):
            print(f"  {i}. {mid}")
        print("\n👉 복사해서 seed_data.py의 test_match_id 값에 붙여넣고 다시 실행해 보세요!")
    else:
        print(f"❌ 매치 ID 불러오기 실패 (상태 코드: {match_res.status_code})")

if __name__ == "__main__":
    get_recent_matches()