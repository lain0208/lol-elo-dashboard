import os
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from db_conn import get_db_connection

# 자동화를 위해 기존에 만든 스크립트 모듈 가져오기
from seed_data import seed_match_to_db
from elo_calculator import recalculate_all_elo

app = FastAPI(title="LoL ELO Dashboard API")

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

# --- 🚀 [NEW] 라이엇 웹훅 수신용 API 엔드포인트 ---
def process_new_match(match_id: str):
    """백그라운드에서 매치를 수집하고 ELO를 재계산하는 작업"""
    print(f"🔄 [백그라운드 작업] 매치 {match_id} 수집 및 ELO 계산 시작...")
    seed_match_to_db(match_id)
    recalculate_all_elo()
    print(f"✅ [백그라운드 작업] 매치 {match_id} 자동 업데이트 완료!")

@app.post("/api/webhook")
async def riot_webhook(request: Request, background_tasks: BackgroundTasks):
    """라이엇 토너먼트 서버가 게임 종료 시 이 주소로 데이터를 보냅니다."""
    try:
        data = await request.json()
        print("📨 라이엇으로부터 웹훅 데이터를 수신했습니다:", data)
        
        # 라이엇이 보내주는 JSON에서 매치 ID 추출 (테스트/실제 환경에 따라 키값이 다를 수 있음)
        match_id = data.get("matchId") or data.get("gameId") 
        
        if match_id:
            # 1. match_id가 그냥 숫자(예: 7000000)로 오면 'KR_'를 붙여줌
            if not str(match_id).startswith("KR_"):
                match_id = f"KR_{match_id}"
                
            # 2. 백그라운드에서 수집 및 계산 스크립트 자동 실행
            background_tasks.add_task(process_new_match, match_id)
            return {"status": "success", "message": f"매치 {match_id} 자동 업데이트 예약됨"}
        else:
            return {"status": "ignored", "message": "매치 ID를 찾을 수 없음"}
            
    except Exception as e:
        print(f"❌ 웹훅 처리 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail="웹훅 처리 실패")

# --- [이하 기존 코드 동일] ---
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
        for rank, row in enumerate(rows, 1):
            total_games = row[4] + row[5]
            win_rate = round((row[4] / total_games) * 100, 1) if total_games > 0 else 0
            rankings.append({
                "rank": rank, "puuid": row[0], "summoner_name": row[1],
                "real_name": row[2] if row[2] else "미등록", "elo_rating": row[3],
                "wins": row[4], "losses": row[5], "win_rate": win_rate
            })
        return {"status": "success", "data": rankings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.get("/api/matches")
def get_recent_matches():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT MATCH_ID, GAME_CREATION, GAME_DURATION, WINNING_TEAM, GAME_MODE 
            FROM MATCHES ORDER BY GAME_CREATION DESC FETCH FIRST 10 ROWS ONLY
        """)
        rows = cursor.fetchall()
        matches = []
        for row in rows:
            matches.append({
                "match_id": row[0], "game_creation": row[1],
                "game_duration_min": round(row[2] / 60, 1),
                "winning_team": "블루(100)" if row[3] == 100 else "레드(200)",
                "game_mode": row[4]
            })
        return {"status": "success", "data": matches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("🚀 FastAPI 서버를 시작합니다...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)