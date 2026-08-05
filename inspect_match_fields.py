import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
MATCH_API_HOST = "https://asia.api.riotgames.com"
ACCOUNT_API_HOST = "https://asia.api.riotgames.com"

def get_puuid(game_name: str, tag_line: str):
    url = f"{ACCOUNT_API_HOST}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}?api_key={RIOT_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json().get("puuid")
    print(f"❌ 유저 조회 실패 ({res.status_code}): {res.text}")
    return None

def get_recent_match_id(puuid: str):
    url = f"{MATCH_API_HOST}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=1&api_key={RIOT_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        matches = res.json()
        if matches:
            return matches[0]
    print(f"❌ 매치 ID 조회 실패 ({res.status_code}): {res.text}")
    return None

def get_match_detail(match_id: str):
    url = f"{MATCH_API_HOST}/lol/match/v5/matches/{match_id}?api_key={RIOT_API_KEY}"
    res = requests.get(url)
    if res.status_code == 200:
        return res.json()
    print(f"❌ 매치 상세 조회 실패 ({res.status_code}): {res.text}")
    return None

def inspect_match_data():
    # 본인 계정이나 확인하고 싶은 소환사 ID 입력
    GAME_NAME = "Lain"
    TAG_LINE = "KR1"

    print(f"🔍 {GAME_NAME}#{TAG_LINE} 소환사의 최근 매치 데이터를 수집합니다...")
    puuid = get_puuid(GAME_NAME, TAG_LINE)
    if not puuid:
        return

    match_id = get_recent_match_id(puuid)
    if not match_id:
        return

    print(f"📌 매치 ID [{match_id}] 상세 데이터를 라이엇 API로부터 수신 중...")
    data = get_match_detail(match_id)
    if not data:
        return

    # 1. 전체 매치 JSON 데이터 파일로 추출
    json_filename = "sample_match.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 원본 데이터 전체가 [{json_filename}] 파일로 저장되었습니다!")

    info = data.get("info", {})
    participants = info.get("participants", [])

    print("\n========================================================")
    print(" 📊 [1] MATCHES (경기 기본 정보) 사용 가능 필드 목록")
    print("========================================================")
    for key in info.keys():
        if key != "participants" and key != "teams":
            print(f" - {key}: {info[key]}")

    if participants:
        p1 = participants[0]
        print("\n========================================================")
        print(f" 👤 [2] MATCH_PARTICIPANTS (참가자 성적) 제공되는 전체 필드 ({len(p1.keys())}개)")
        print("========================================================")
        
        # 보기 쉽게 그룹별로 분류하여 출력
        categories = {
            "🆔 기본 정보": ["puuid", "riotIdGameName", "riotIdTagline", "summonerName", "championName", "championId", "teamId", "individualPosition", "teamPosition", "win"],
            "⚔️ 전투/KDA": ["kills", "deaths", "assists", "doubleKills", "tripleKills", "quadraKills", "pentaKills", "firstBloodKill", "largestKillStreak"],
            "💥 피해량(딜량)": ["totalDamageDealtToChampions", "physicalDamageDealtToChampions", "magicDamageDealtToChampions", "trueDamageDealtToChampions", "damageDealtToObjectives", "damageDealtToTurrets"],
            "🛡️ 받은 딜량/탱킹": ["totalDamageTaken", "physicalDamageTaken", "magicDamageTaken", "trueDamageTaken", "damageSelfMitigated"],
            "💚 회복/보호막": ["totalHeal", "totalHealsOnTeammates", "totalDamageShieldedOnTeammates"],
            "💰 골드/CS": ["goldEarned", "goldSpent", "totalMinionsKilled", "neutralMinionsKilled", "champLevel"],
            "👁️ 시야/와드": ["visionScore", "wardsPlaced", "wardsKilled", "visionWardsBoughtInGame"],
            "🎒 아이템/스펠": ["item0", "item1", "item2", "item3", "item4", "item5", "item6", "summoner1Id", "summoner2Id"]
        }

        printed_keys = set()
        for cat_name, key_list in categories.items():
            print(f"\n{cat_name}:")
            for k in key_list:
                if k in p1:
                    print(f"  • {k}: {p1[k]}")
                    printed_keys.add(k)

        # 위 대표 그룹에 속하지 않은 나머지 지표들 출력
        other_keys = [k for k in p1.keys() if k not in printed_keys and not isinstance(p1[k], (dict, list))]
        print(f"\n📌 기타 세부 수치 필드 ({len(other_keys)}개):")
        for k in sorted(other_keys):
            print(f"  • {k}: {p1[k]}")

if __name__ == "__main__":
    inspect_match_data()