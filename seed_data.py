import os
import json
import requests
import oracledb
from dotenv import load_dotenv
from db_conn import get_db_connection

# .env 환경변수 강제 새로고침
load_dotenv(override=True)

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
HEADERS = {"X-Riot-Token": RIOT_API_KEY}

def get_match_data(match_id):
    url = f"https://asia.api.riotgames.com/lol/match/v5/matches/{match_id}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 401:
        print(f"❌ API 키 만료 또는 권한 없음 (401). 새 키를 .env에 적용하세요.")
    else:
        print(f"❌ 매치 데이터를 가져오지 못했습니다. 상태 코드: {response.status_code}")
    return None

def seed_match_to_db(match_id):
    match_data = get_match_data(match_id)
    if not match_data:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 💥 핵심 해결책: 오라클 클라우드의 강제 병렬 처리 끄기 (ORA-12838 원천 차단)
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")

    info = match_data.get("info", {})
    participants = info.get("participants", [])

    # [1] MATCHES 데이터 준비 (1건)
    game_creation = info.get("gameCreation")
    game_duration = info.get("gameDuration", 0)
    game_mode = info.get("gameMode", "CLASSIC")
    participant_count = len(participants)
    winning_team = 100
    for team in info.get("teams", []):
        if team.get("win"):
            winning_team = team.get("teamId")
            break

    # [2] 10명 데이터를 담을 빈 리스트(바구니) 준비
    users_batch = []
    participants_batch = []
    raw_batch = []

    for p in participants:
        puuid = p.get("puuid")
        summoner_name = f"{p.get('riotIdGameName', p.get('summonerName'))}#{p.get('riotIdTagline', 'KR1')}"
        
        kda = 0.0
        if p.get("deaths", 0) == 0:
            kda = float(p.get("kills", 0) + p.get("assists", 0))
        else:
            kda = round((p.get("kills", 0) + p.get("assists", 0)) / p.get("deaths", 1), 2)

        users_batch.append((puuid, summoner_name))
        
        participants_batch.append((
            match_id, puuid, p.get("teamId"), p.get("teamPosition"), p.get("championName"),
            p.get("kills", 0), p.get("deaths", 0), p.get("assists", 0), kda,
            p.get("totalDamageDealtToChampions", 0), p.get("totalDamageTaken", 0), p.get("totalHeal", 0),
            p.get("goldEarned", 0), p.get("totalMinionsKilled", 0), p.get("neutralMinionsKilled", 0),
            p.get("visionScore", 0), p.get("pentaKills", 0), p.get("challenges", {}).get("soloKills", 0),
            p.get("magicDamageDealtToChampions", 0), p.get("physicalDamageDealtToChampions", 0), p.get("trueDamageDealtToChampions", 0),
            p.get("largestMultiKill", 0), p.get("timeCCingOthers", 0), p.get("damageDealtToObjectives", 0),
            p.get("damageDealtToTurrets", 0), p.get("damageSelfMitigated", 0), p.get("wardsPlaced", 0),
            p.get("wardsKilled", 0), p.get("visionWardsBoughtInGame", 0), 1 if p.get("firstBloodKill", 0) else 0,
            1 if p.get("firstBloodAssist", 0) else 0, 1 if p.get("firstTowerKill", 0) else 0, 1 if p.get("firstTowerAssist", 0) else 0,
            p.get("item0", 0), p.get("item1", 0)
        ))
        
        raw_batch.append((match_id, puuid, json.dumps(p, ensure_ascii=False)))

    print("🚀 데이터를 묶어서(Batch) 오라클 DB로 전송합니다...")

    try:
        # [3] 단 4번의 통신으로 모든 데이터 일괄 전송
        cursor.execute("""
            INSERT INTO MATCHES (MATCH_ID, GAME_CREATION, GAME_DURATION, WINNING_TEAM, GAME_MODE, PARTICIPANT_COUNT)
            VALUES (:1, TO_TIMESTAMP('1970-01-01 00:00:00', 'YYYY-MM-DD HH24:MI:SS') + NUMTODSINTERVAL(:2 / 1000, 'SECOND'), :3, :4, :5, :6)
        """, (match_id, game_creation, game_duration, winning_team, game_mode, participant_count))
        
        cursor.executemany("""
            MERGE INTO USERS u
            USING (SELECT :1 AS PUUID, :2 AS SUMMONER_NAME FROM DUAL) src
            ON (u.PUUID = src.PUUID)
            WHEN MATCHED THEN UPDATE SET u.SUMMONER_NAME = src.SUMMONER_NAME
            WHEN NOT MATCHED THEN INSERT (PUUID, SUMMONER_NAME, ELO_RATING, WINS, LOSSES) 
            VALUES (src.PUUID, src.SUMMONER_NAME, 1200, 0, 0)
        """, users_batch)

        cursor.executemany("""
            INSERT INTO MATCH_PARTICIPANTS (
                MATCH_ID, PUUID, TEAM_ID, POSITION, CHAMPION_NAME, KILLS, DEATHS, ASSISTS, KDA,
                TOTAL_DAMAGE_DEALT, TOTAL_DAMAGE_TAKEN, TOTAL_HEAL, GOLD_EARNED, TOTAL_MINIONS_KILLED, NEUTRAL_MINIONS_KILLED,
                VISION_SCORE, PENTA_KILLS, SOLO_KILLS, MAGIC_DAMAGE_DEALT, PHYSICAL_DAMAGE_DEALT, TRUE_DAMAGE_DEALT,
                LARGEST_MULTI_KILL, TIME_CCING_OTHERS, DAMAGE_DEALT_TO_OBJECTIVES, DAMAGE_DEALT_TO_TURRETS, DAMAGE_SELF_MITIGATED, WARDS_PLACED,
                WARDS_KILLED, CONTROL_WARDS_PLACED, FIRST_BLOOD_KILL, FIRST_BLOOD_ASSIST, FIRST_TOWER_KILL, FIRST_TOWER_ASSIST,
                ITEM_0, ITEM_1
            ) VALUES (
                :1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13, :14, :15, :16, :17, :18,
                :19, :20, :21, :22, :23, :24, :25, :26, :27, :28, :29, :30, :31, :32, :33, :34, :35
            )
        """, participants_batch)

        cursor.executemany("""
            INSERT INTO MATCH_PARTICIPANT_RAW (MATCH_ID, PUUID, RAW_DATA)
            VALUES (:1, :2, :3)
        """, raw_batch)

        # 모든 작업이 성공하면 마지막에 딱 한 번만 저장 확정!
        conn.commit()
        print(f"✅ 매치 [{match_id}] 데이터 초고속 삽입 완료!")

    except oracledb.DatabaseError as e:
        conn.rollback()
        error_obj, = e.args
        print(f"❌ DB INSERT 중 오류 발생: {error_obj.message}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print(f"🔑 적용된 API 키: [{RIOT_API_KEY[:9]}...]")
    test_match_id = "KR_8322458588" 
    seed_match_to_db(test_match_id)