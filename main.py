import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from itertools import combinations
import uvicorn
from db_conn import get_db_connection

# 자동화 스크립트 임포트
from seed_data import seed_match_to_db
from elo_calculator import recalculate_all_elo

app = FastAPI(title="LoL ELO Dashboard API")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

# --- 자동 수집 API ---
class MatchSyncRequest(BaseModel):
    match_id: str

@app.post("/api/matches/sync")
def sync_new_match(req: MatchSyncRequest):
    match_id = req.match_id.strip()
    if not match_id.upper().startswith("KR_"):
        match_id = f"KR_{match_id}"
        
    try:
        print(f"\n🔄 [웹 요청 수신] 매치 {match_id} 수집 시작...")
        seed_match_to_db(match_id)
        recalculate_all_elo()
        return {"status": "success", "message": f"매치 {match_id} 업데이트 완료!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"수집 오류: {str(e)}")

# --- 🚀 [NEW] 5:5 팀 자동 밸런싱 API ---
class TeamBalanceRequest(BaseModel):
    puuids: List[str]

@app.post("/api/team-balance")
def calculate_team_balance(req: TeamBalanceRequest):
    """10명의 PUUID를 받아 가장 공평한 5:5 팀을 구성합니다."""
    if len(req.puuids) != 10:
        raise HTTPException(status_code=400, detail="정확히 10명을 선택해야 합니다.")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 10명의 ELO 점수 가져오기
        format_strings = ','.join([':{}'.format(i+1) for i in range(len(req.puuids))])
        query = f"SELECT PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING FROM USERS WHERE PUUID IN ({format_strings})"
        cursor.execute(query, req.puuids)
        users = cursor.fetchall()

        if len(users) != 10:
            raise HTTPException(status_code=400, detail="일부 유저를 DB에서 찾을 수 없습니다.")

        # 계산을 쉽게 하기 위해 딕셔너리로 변환
        user_list = []
        for u in users:
            display_name = u[1] if (u[2] is None or u[2] == '미등록') else f"{u[1]} ({u[2]})"
            user_list.append({"puuid": u[0], "name": display_name, "elo": u[3]})

        # 브루트포스(모든 조합 탐색): 10명 중 5명을 뽑는 경우의 수 (252가지)
        best_diff = float('inf')
        best_team_blue = []
        best_team_red = []

        for combo in combinations(user_list, 5):
            team_blue = list(combo)
            blue_puuids = {u['puuid'] for u in team_blue}
            team_red = [u for u in user_list if u['puuid'] not in blue_puuids]

            elo_blue = sum(u['elo'] for u in team_blue)
            elo_red = sum(u['elo'] for u in team_red)
            diff = abs(elo_blue - elo_red)

            # 양 팀의 ELO 총합 차이가 가장 적은 조합 찾기
            if diff < best_diff:
                best_diff = diff
                best_team_blue = team_blue
                best_team_red = team_red

        avg_blue = sum(u['elo'] for u in best_team_blue) / 5
        avg_red = sum(u['elo'] for u in best_team_red) / 5

        # 블루팀 기준 승률 기대값 계산
        expected_win_rate = 1 / (1 + 10 ** ((avg_red - avg_blue) / 400))

        return {
            "status": "success",
            "team_blue": sorted(best_team_blue, key=lambda x: x['elo'], reverse=True),
            "team_red": sorted(best_team_red, key=lambda x: x['elo'], reverse=True),
            "avg_blue": avg_blue,
            "avg_red": avg_red,
            "expected_win_rate_blue": round(expected_win_rate * 100, 1),
            "expected_win_rate_red": round((1 - expected_win_rate) * 100, 1)
        }
    finally:
        cursor.close()
        conn.close()

# --- 이하 기존 API 엔드포인트 동일 ---
@app.get("/api/rankings")
def get_rankings():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING, WINS, LOSSES FROM USERS ORDER BY ELO_RATING DESC, WINS DESC")
        rows = cursor.fetchall()
        rankings = []
        for rank, row in enumerate(rows, 1):
            total_games = row[4] + row[5]
            win_rate = round((row[4] / total_games) * 100, 1) if total_games > 0 else 0
            rankings.append({"rank": rank, "puuid": row[0], "summoner_name": row[1], "real_name": row[2] if row[2] else "미등록", "elo_rating": row[3], "wins": row[4], "losses": row[5], "win_rate": win_rate})
        return {"status": "success", "data": rankings}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/matches")
def get_recent_matches():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MATCH_ID, GAME_CREATION, GAME_DURATION, WINNING_TEAM, GAME_MODE FROM MATCHES ORDER BY GAME_CREATION DESC FETCH FIRST 10 ROWS ONLY")
        rows = cursor.fetchall()
        matches = [{"match_id": r[0], "game_creation": r[1], "game_duration_min": round(r[2]/60, 1), "winning_team": "블루(100)" if r[3]==100 else "레드(200)", "game_mode": r[4]} for r in rows]
        return {"status": "success", "data": matches}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/matches/{match_id}")
def get_match_detail(match_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MATCH_ID, GAME_DURATION, WINNING_TEAM, GAME_MODE FROM MATCHES WHERE MATCH_ID = :1", (match_id,))
        match_row = cursor.fetchone()
        if not match_row: raise HTTPException(status_code=404, detail="해당 매치를 찾을 수 없습니다.")
        cursor.execute("SELECT mp.PUUID, u.SUMMONER_NAME, mp.TEAM_ID, mp.POSITION, mp.CHAMPION_NAME, mp.KILLS, mp.DEATHS, mp.ASSISTS, mp.KDA, mp.TOTAL_DAMAGE_DEALT, mp.GOLD_EARNED, mp.VISION_SCORE FROM MATCH_PARTICIPANTS mp JOIN USERS u ON mp.PUUID = u.PUUID WHERE mp.MATCH_ID = :1 ORDER BY mp.TEAM_ID ASC, mp.POSITION DESC", (match_id,))
        participants = [{"puuid": r[0], "summoner_name": r[1], "team_id": r[2], "position": r[3] if r[3] else "기타", "champion_name": r[4], "kills": r[5], "deaths": r[6], "assists": r[7], "kda": r[8], "total_damage": r[9], "gold_earned": r[10], "vision_score": r[11]} for r in cursor.fetchall()]
        return {"status": "success", "match_info": {"match_id": match_row[0], "duration_min": round(match_row[1]/60, 1), "winning_team": match_row[2], "game_mode": match_row[3]}, "participants": participants}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/users/{puuid}")
def get_user_profile(puuid: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING, WINS, LOSSES FROM USERS WHERE PUUID = :1", (puuid,))
        user_row = cursor.fetchone()
        if not user_row: raise HTTPException(status_code=404, detail="해당 유저를 찾을 수 없습니다.")
        total_games = user_row[4] + user_row[5]
        win_rate = round((user_row[4]/total_games)*100, 1) if total_games > 0 else 0
        user_info = {"puuid": user_row[0], "summoner_name": user_row[1], "real_name": user_row[2] if user_row[2] else "미등록", "elo_rating": user_row[3], "wins": user_row[4], "losses": user_row[5], "win_rate": win_rate}
        
        cursor.execute("SELECT CHAMPION_NAME, COUNT(*) as pick_count, SUM(CASE WHEN (TEAM_ID = 100 AND WINNING_TEAM = 100) OR (TEAM_ID = 200 AND WINNING_TEAM = 200) THEN 1 ELSE 0 END) as wins, ROUND(AVG(KDA), 2) as avg_kda FROM MATCH_PARTICIPANTS mp JOIN MATCHES m ON mp.MATCH_ID = m.MATCH_ID WHERE mp.PUUID = :1 GROUP BY CHAMPION_NAME ORDER BY pick_count DESC FETCH FIRST 5 ROWS ONLY", (puuid,))
        most_champs = [{"champion_name": r[0], "games": r[1], "wins": r[2], "losses": r[1]-r[2], "win_rate": round((r[2]/r[1])*100, 1) if r[1] > 0 else 0, "avg_kda": r[3]} for r in cursor.fetchall()]
        
        cursor.execute("SELECT m.MATCH_ID, m.GAME_CREATION, m.GAME_DURATION, m.WINNING_TEAM, mp.TEAM_ID, mp.CHAMPION_NAME, mp.KILLS, mp.DEATHS, mp.ASSISTS, mp.KDA FROM MATCH_PARTICIPANTS mp JOIN MATCHES m ON mp.MATCH_ID = m.MATCH_ID WHERE mp.PUUID = :1 ORDER BY m.GAME_CREATION DESC FETCH FIRST 5 ROWS ONLY", (puuid,))
        match_history = [{"match_id": r[0], "game_creation": r[1], "duration_min": round(r[2]/60, 1), "is_win": (r[3] == r[4]), "champion_name": r[5], "kda_string": f"{r[6]}/{r[7]}/{r[8]}", "kda": r[9]} for r in cursor.fetchall()]
        return {"status": "success", "user_info": user_info, "most_champions": most_champs, "match_history": match_history}
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)