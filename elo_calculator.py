from db_conn import get_db_connection

# ELO 변동폭을 결정하는 상수 (K-Factor). 값이 클수록 한 판당 점수 변동이 큽니다.
K_FACTOR = 32 

def recalculate_all_elo():
    """모든 매치 기록을 시간순으로 읽어 전체 유저의 ELO와 전적을 재계산합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 💥 핵심 1: 오라클의 강제 병렬 처리 비활성화 (병렬 데드락 원천 차단)
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")

    # 1. 재계산을 위해 모든 유저의 ELO를 1200, 승/패를 0으로 초기화
    print("🧹 기존 유저 ELO 데이터를 1200점으로 초기화합니다...")
    cursor.execute("UPDATE USERS SET ELO_RATING = 1200, WINS = 0, LOSSES = 0")
    
    # 💥 핵심 2: 초기화 직후 무조건 COMMIT을 해서 10명 데이터의 자물쇠(Lock)를 풀어줌!
    conn.commit() 
    
    # 2. 오름차순(과거 -> 최신)으로 모든 매치 가져오기
    cursor.execute("SELECT MATCH_ID, WINNING_TEAM FROM MATCHES ORDER BY GAME_CREATION ASC")
    matches = cursor.fetchall()

    if not matches:
        print("📭 계산할 매치 데이터가 없습니다. seed_data.py로 데이터를 먼저 수집하세요.")
        return

    print(f"🧮 총 {len(matches)}개의 매치 데이터 ELO 계산을 시작합니다...")

    for match_id, winning_team in matches:
        # 3. 해당 매치의 참가자 10명과 현재 시점의 ELO 정보 가져오기
        cursor.execute("""
            SELECT mp.PUUID, mp.TEAM_ID, u.ELO_RATING, u.WINS, u.LOSSES 
            FROM MATCH_PARTICIPANTS mp
            JOIN USERS u ON mp.PUUID = u.PUUID
            WHERE mp.MATCH_ID = :1
        """, (match_id,))
        participants = cursor.fetchall()

        # 팀 분리 (100: 블루팀, 200: 레드팀)
        team_100 = [p for p in participants if p[1] == 100]
        team_200 = [p for p in participants if p[1] == 200]

        if not team_100 or not team_200:
            continue # 데이터가 불완전한 게임은 스킵

        # 4. 각 팀의 평균 ELO 계산
        avg_elo_100 = sum(p[2] for p in team_100) / len(team_100)
        avg_elo_200 = sum(p[2] for p in team_200) / len(team_200)

        # 5. ELO 승률 기대값(Expected Score) 계산 공식 적용
        expected_100 = 1 / (1 + 10 ** ((avg_elo_200 - avg_elo_100) / 400))
        expected_200 = 1 / (1 + 10 ** ((avg_elo_100 - avg_elo_200) / 400))

        # 실제 결과 (1: 승리, 0: 패배)
        actual_100 = 1 if winning_team == 100 else 0
        actual_200 = 1 if winning_team == 200 else 0

        # 6. 참가자 10명 각각의 새로운 ELO 점수 및 전적 산출
        update_data = []
        for puuid, team_id, current_elo, wins, losses in participants:
            is_team_100 = (team_id == 100)
            expected = expected_100 if is_team_100 else expected_200
            actual = actual_100 if is_team_100 else actual_200
            
            # 새 ELO = 기존 ELO + K * (실제결과 - 기대값)
            new_elo = current_elo + K_FACTOR * (actual - expected)
            
            new_wins = wins + 1 if actual == 1 else wins
            new_losses = losses + 1 if actual == 0 else losses
            
            # 업데이트 바구니에 담기 (반올림 처리)
            update_data.append((round(new_elo), new_wins, new_losses, puuid))

        # 7. DB에 계산된 새 점수 일괄 업데이트 (Batch Update)
        cursor.executemany("""
            UPDATE USERS 
            SET ELO_RATING = :1, WINS = :2, LOSSES = :3 
            WHERE PUUID = :4
        """, update_data)
        
        # 💥 핵심 3: 1경기가 계산될 때마다 점수를 확정(Commit)지어야 다음 경기 계산에 최신 점수가 반영됨
        conn.commit()

    print(f"✅ 성공적으로 ELO 재계산이 완료되었습니다! 랭킹이 업데이트 되었습니다.")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    recalculate_all_elo()