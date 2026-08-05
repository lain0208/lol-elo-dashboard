import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from db_conn import get_db_connection

# .env 환경 변수 로드
load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")

def fetch_and_save_match(match_id: str) -> bool:
    """주어진 매치 ID의 데이터를 라이엇 API에서 가져와 DB에 저장하는 함수"""
    if not RIOT_API_KEY:
        print("❌ RIOT_API_KEY가 설정되지 않았습니다.")
        return False

    headers = {
        "X-Riot-Token": RIOT_API_KEY
    }

    # 1. 라이엇 API 호출
    url = f"https://asia.api.riotgames.com/lol/match/v5/matches/{match_id}"
    print(f"🔍 매치 데이터 수집 중... ({match_id})")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"❌ 매치 데이터 수집 실패: {response.status_code} - {response.text}")
        return False

    match_data = response.json()
    info = match_data['info']

    # 게임 모드 및 생성 시간
    game_mode = info.get('gameMode', 'UNKNOWN')
    game_creation_ms = info.get('gameCreation', 0)
    game_creation = datetime.fromtimestamp(game_creation_ms / 1000.0)
    game_duration = info.get('gameDuration', 0)

    # 승리 팀 찾기
    winning_team = 100
    for team in info.get('teams', []):
        if team.get('win'):
            winning_team = team.get('teamId')
            break

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 2. 매치가 이미 존재하는지 확인 (중복 저장 방지)
        cursor.execute("SELECT 1 FROM MATCHES WHERE MATCH_ID = :1", (match_id,))
        if cursor.fetchone():
            print(f"⚠️ 매치 {match_id}는 이미 DB에 존재합니다.")
            return False

        # 3. MATCHES 테이블 저장
        cursor.execute("""
            INSERT INTO MATCHES (MATCH_ID, GAME_CREATION, GAME_DURATION, WINNING_TEAM, GAME_MODE)
            VALUES (:1, :2, :3, :4, :5)
        """, (match_id, game_creation, game_duration, winning_team, game_mode))

        # 4. 참가자 데이터 파싱 및 저장
        participants = info.get('participants', [])
        for p in participants:
            puuid = p.get('puuid')
            
            # 닉네임 + 태그라인 안전하게 가져오기
            riot_name = p.get('riotIdGameName')
            riot_tag = p.get('riotIdTagline')
            if riot_name and riot_tag:
                summoner_name = f"{riot_name}#{riot_tag}"
            else:
                summoner_name = p.get('summonerName', 'Unknown')

            team_id = p.get('teamId')
            champion_name = p.get('championName')
            kills = p.get('kills', 0)
            deaths = p.get('deaths', 0)
            assists = p.get('assists', 0)
            total_damage = p.get('totalDamageDealtToChampions', 0)
            gold_earned = p.get('goldEarned', 0)

            # 4-1. USERS 테이블 MERGE (신규 유저면 등록, 기존 유저면 이름만 갱신)
            cursor.execute("""
                MERGE INTO USERS u
                USING (SELECT :1 AS PUUID, :2 AS SUMMONER_NAME FROM DUAL) src
                ON (u.PUUID = src.PUUID)
                WHEN MATCHED THEN
                    UPDATE SET SUMMONER_NAME = src.SUMMONER_NAME
                WHEN NOT MATCHED THEN
                    INSERT (PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING, WINS, LOSSES)
                    VALUES (src.PUUID, src.SUMMONER_NAME, '미등록', 1200, 0, 0)
            """, (puuid, summoner_name))

            # 4-2. MATCH_PARTICIPANTS 저장
            cursor.execute("""
                INSERT INTO MATCH_PARTICIPANTS
                (MATCH_ID, PUUID, TEAM_ID, CHAMPION_NAME, KILLS, DEATHS, ASSISTS, TOTAL_DAMAGE, GOLD_EARNED)
                VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
            """, (match_id, puuid, team_id, champion_name, kills, deaths, assists, total_damage, gold_earned))

            # 4-3. MATCH_PARTICIPANT_RAW 저장 (JSON 통째로 보관)
            raw_json = json.dumps(p)
            cursor.execute("""
                INSERT INTO MATCH_PARTICIPANT_RAW (MATCH_ID, PUUID, RAW_DATA)
                VALUES (:1, :2, :3)
            """, (match_id, puuid, raw_json))

        # 정상 처리 시 커밋
        conn.commit()
        print(f"✅ 매치 {match_id} DB 저장 완료!")
        return True

    except Exception as e:
        conn.rollback()
        print(f"❌ DB 저장 오류: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

# 터미널에서 스크립트를 직접 실행할 때 동작하는 부분
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        fetch_and_save_match(sys.argv[1])
    else:
        print("사용법: python seed_data.py <KR_Match_ID>")
