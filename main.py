import os
import itertools
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# .env 환경 변수 로드
load_dotenv()

from db_conn import get_db_connection
from seed_data import fetch_and_save_match
from elo_calculator import recalculate_all_elo

app = FastAPI(title="LoL ELO Dashboard API")

# --- Pydantic 요청 데이터 모델 ---
class AdminLoginRequest(BaseModel):
    password: str

class SyncMatchRequest(BaseModel):
    match_id: str

class TeamBalanceRequest(BaseModel):
    puuids: List[str]


# --- 1. 관리자 비밀번호 검증 API ---
@app.post("/api/admin/verify")
def verify_admin(req: AdminLoginRequest):
    admin_pwd = os.getenv("ADMIN_PASSWORD", "1234")  # .env에 없으면 기본값 1234
    if req.password == admin_pwd:
        return {"status": "success", "message": "관리자 인증 성공"}
    else:
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")


# --- 2. 실시간 랭킹 조회 API ---
@app.get("/api/rankings")
def get_rankings():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING, WINS, LOSSES
            FROM USERS
            ORDER BY ELO_RATING DESC, WINS DESC
        """)
        rows = cursor.fetchall()
        rankings = []
        for rank, row in enumerate(rows, start=1):
            total_games = row[4] + row[5]
            win_rate = round((row[4] / total_games * 100), 1) if total_games > 0 else 0.0
            rankings.append({
                "rank": rank,
                "puuid": row[0],
                "summoner_name": row[1],
                "real_name": row[2] if row[2] else "미등록",
                "elo_rating": row[3],
                "wins": row[4],
                "losses": row[5],
                "win_rate": win_rate
            })
        return {"status": "success", "data": rankings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# --- 3. 최근 경기 목록 조회 API ---
@app.get("/api/matches")
def get_matches():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT MATCH_ID, GAME_CREATION, GAME_DURATION, WINNING_TEAM, GAME_MODE
            FROM MATCHES
            ORDER BY GAME_CREATION DESC
        """)
        rows = cursor.fetchall()
        matches = []
        for row in rows:
            winning_team_str = "💙 블루팀" if row[3] == 100 else "❤️ 레드팀"
            matches.append({
                "match_id": row[0],
                "game_creation": row[1].isoformat() if row[1] else "",
                "game_duration_min": round(row[2] / 60, 1) if row[2] else 0,
                "winning_team": winning_team_str,
                "game_mode": row[4]
            })
        return {"status": "success", "data": matches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# --- 4. 매치 상세 정보 조회 API ---
@app.get("/api/matches/{match_id}")
def get_match_detail(match_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT MATCH_ID, GAME_DURATION, WINNING_TEAM, GAME_MODE
            FROM MATCHES WHERE MATCH_ID = :1
        """, (match_id,))
        match_row = cursor.fetchone()
        if not match_row:
            raise HTTPException(status_code=404, detail="해당 매치를 찾을 수 없습니다.")

        cursor.execute("""
            SELECT mp.PUUID, u.SUMMONER_NAME, mp.TEAM_ID, mp.CHAMPION_NAME,
                   mp.KILLS, mp.DEATHS, mp.ASSISTS, mp.TOTAL_DAMAGE, mp.GOLD_EARNED
            FROM MATCH_PARTICIPANTS mp
            JOIN USERS u ON mp.PUUID = u.PUUID
            WHERE mp.MATCH_ID = :1
            ORDER BY mp.TEAM_ID ASC, mp.KILLS DESC
        """, (match_id,))
        p_rows = cursor.fetchall()

        participants = []
        for p in p_rows:
            kda = round((p[4] + p[6]) / p[5], 2) if p[5] > 0 else (p[4] + p[6])
            participants.append({
                "puuid": p[0],
                "summoner_name": p[1],
                "team_id": p[2],
                "champion_name": p[3],
                "kills": p[4],
                "deaths": p[5],
                "assists": p[6],
                "kda": kda,
                "total_damage": p[7],
                "gold_earned": p[8]
            })

        return {
            "status": "success",
            "match_info": {
                "match_id": match_row[0],
                "duration_min": round(match_row[1] / 60, 1),
                "winning_team": match_row[2],
                "game_mode": match_row[3]
            },
            "participants": participants
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# --- 5. 유저 프로필 조회 API ---
@app.get("/api/users/{puuid}")
def get_user_profile(puuid: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING, WINS, LOSSES
            FROM USERS WHERE PUUID = :1
        """, (puuid,))
        user_row = cursor.fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="해당 유저를 찾을 수 없습니다.")

        total_games = user_row[4] + user_row[5]
        win_rate = round((user_row[4] / total_games * 100), 1) if total_games > 0 else 0.0

        # 모스트 챔피언 TOP 5
        cursor.execute("""
            SELECT CHAMPION_NAME, COUNT(*) AS GAMES,
                   SUM(CASE WHEN (mp.TEAM_ID = m.WINNING_TEAM) THEN 1 ELSE 0 END) AS WINS
            FROM MATCH_PARTICIPANTS mp
            JOIN MATCHES m ON mp.MATCH_ID = m.MATCH_ID
            WHERE mp.PUUID = :1
            GROUP BY CHAMPION_NAME
            ORDER BY GAMES DESC
            FETCH FIRST 5 ROWS ONLY
        """, (puuid,))
        most_rows = cursor.fetchall()
        most_champions = []
        for m in most_rows:
            m_games = m[1]
            m_wins = m[2]
            m_losses = m_games - m_wins
            m_win_rate = round((m_wins / m_games * 100), 1) if m_games > 0 else 0.0
            most_champions.append({
                "champion_name": m[0],
                "games": m_games,
                "wins": m_wins,
                "losses": m_losses,
                "win_rate": m_win_rate
            })

        # 최근 10경기 기록
        cursor.execute("""
            SELECT m.MATCH_ID, mp.CHAMPION_NAME, mp.KILLS, mp.DEATHS, mp.ASSISTS,
                   m.GAME_DURATION, CASE WHEN (mp.TEAM_ID = m.WINNING_TEAM) THEN 1 ELSE 0 END AS IS_WIN
            FROM MATCH_PARTICIPANTS mp
            JOIN MATCHES m ON mp.MATCH_ID = m.MATCH_ID
            WHERE mp.PUUID = :1
            ORDER BY m.GAME_CREATION DESC
            FETCH FIRST 10 ROWS ONLY
        """, (puuid,))
        history_rows = cursor.fetchall()
        match_history = []
        for h in history_rows:
            kda = round((h[2] + h[4]) / h[3], 2) if h[3] > 0 else (h[2] + h[4])
            match_history.append({
                "match_id": h[0],
                "champion_name": h[1],
                "kda_string": f"{h[2]}/{h[3]}/{h[4]}",
                "kda": kda,
                "duration_min": round(h[5] / 60, 1) if h[5] else 0,
                "is_win": bool(h[6])
            })

        return {
            "status": "success",
            "user_info": {
                "puuid": user_row[0],
                "summoner_name": user_row[1],
                "real_name": user_row[2] if user_row[2] else "미등록",
                "elo_rating": user_row[3],
                "wins": user_row[4],
                "losses": user_row[5],
                "win_rate": win_rate
            },
            "most_champions": most_champions,
            "match_history": match_history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# --- 6. 전적 수동 동기화 API (관리자 암호 검증 헤더 추가) ---
@app.post("/api/matches/sync")
def sync_match(req: SyncMatchRequest, x_admin_password: Optional[str] = Header(None)):
    admin_pwd = os.getenv("ADMIN_PASSWORD", "1234")
    # 관리자 암호 검증
    if x_admin_password != admin_pwd:
        raise HTTPException(status_code=401, detail="관리자 권한이 없습니다.")

    match_id = req.match_id.strip()
    if not match_id.startswith("KR_"):
        match_id = f"KR_{match_id}"

    try:
        # 라이엇 API에서 매치 데이터 수집
        success = fetch_and_save_match(match_id)
        if not success:
            raise HTTPException(status_code=400, detail="매치 수집 실패 (이미 존재하거나 라이엇 API 오류)")

        # ELO 재계산
        recalculate_all_elo()
        return {"status": "success", "message": f"매치 ({match_id}) 수집 및 ELO 재계산이 완료되었습니다!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 7. 5:5 팀 밸런서 API ---
@app.post("/api/team-balance")
def balance_teams(req: TeamBalanceRequest):
    if len(req.puuids) != 10:
        raise HTTPException(status_code=400, detail="정확히 10명의 유저를 선택해야 합니다.")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ', '.join([f':{i+1}' for i in range(len(req.puuids))])
        query = f"SELECT PUUID, SUMMONER_NAME, REAL_NAME, ELO_RATING FROM USERS WHERE PUUID IN ({placeholders})"
        cursor.execute(query, req.puuids)
        users = cursor.fetchall()

        if len(users) != 10:
            raise HTTPException(status_code=400, detail="선택한 유저 중 일부를 DB에서 찾을 수 없습니다.")

        user_list = [
            {"puuid": u[0], "name": u[2] if u[2] and u[2] != "미등록" else u[1].split('#')[0], "elo": u[3]}
            for u in users
        ]

        # 조합 탐색
        best_diff = float('inf')
        best_blue, best_red = [], []

        for combo in itertools.combinations(user_list, 5):
            blue_team = list(combo)
            blue_ids = {u['puuid'] for u in blue_team}
            red_team = [u for u in user_list if u['puuid'] not in blue_ids]

            avg_blue = sum(u['elo'] for u in blue_team) / 5.0
            avg_red = sum(u['elo'] for u in red_team) / 5.0
            diff = abs(avg_blue - avg_red)

            if diff < best_diff:
                best_diff = diff
                best_blue = blue_team
                best_red = red_team

        avg_blue = sum(u['elo'] for u in best_blue) / 5.0
        avg_red = sum(u['elo'] for u in best_red) / 5.0

        exp_blue = 1 / (1 + 10 ** ((avg_red - avg_blue) / 400))
        winrate_blue = round(exp_blue * 100, 1)
        winrate_red = round((1 - exp_blue) * 100, 1)

        return {
            "status": "success",
            "team_blue": best_blue,
            "team_red": best_red,
            "avg_blue": round(avg_blue, 1),
            "avg_red": round(avg_red, 1),
            "elo_diff": round(best_diff, 1),
            "expected_win_rate_blue": winrate_blue,
            "expected_win_rate_red": winrate_red
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# --- 정적 파일 폴더 연결 및 메인 화면 제공 ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
