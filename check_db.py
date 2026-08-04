import os
import oracledb
from dotenv import load_dotenv

load_dotenv()

def inspect_and_fix_all_tables():
    conn = oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dsn=os.getenv("DB_DSN"),
        config_dir=os.getenv("WALLET_DIR"),
        wallet_location=os.getenv("WALLET_DIR"),
        wallet_password=os.getenv("WALLET_PASSWORD")
    )
    cursor = conn.cursor()

    # 3개 테이블 전체 필수 컬럼 정의 (수집 스크립트 전수 대응)
    schema_checks = {
        "USERS": {
            "PUUID": "VARCHAR2(100)",
            "SUMMONER_NAME": "VARCHAR2(100)",
            "ELO_RATING": "NUMBER DEFAULT 1200",
            "WINS": "NUMBER DEFAULT 0",
            "LOSSES": "NUMBER DEFAULT 0"
        },
        "MATCHES": {
            "MATCH_ID": "VARCHAR2(50)",
            "GAME_DURATION": "NUMBER",
            "WINNING_TEAM": "NUMBER",
            "GAME_CREATION": "TIMESTAMP",
            "CREATED_AT": "DATE DEFAULT SYSDATE"
        },
        "MATCH_PARTICIPANTS": {
            "MATCH_ID": "VARCHAR2(50)",
            "PUUID": "VARCHAR2(100)",
            "TEAM_ID": "NUMBER",
            "CHAMPION_NAME": "VARCHAR2(50)",
            "KILLS": "NUMBER DEFAULT 0",
            "DEATHS": "NUMBER DEFAULT 0",
            "ASSISTS": "NUMBER DEFAULT 0",
            "DAMAGE_DEALT": "NUMBER DEFAULT 0",
            "WIN": "NUMBER DEFAULT 0"
        }
    }

    for table_name, required_cols in schema_checks.items():
        print(f"\n🔍 [{table_name}] 테이블 점검 중...")
        
        # 현재 테이블의 실제 컬럼 목록 조회
        cursor.execute(f"SELECT column_name FROM user_tab_cols WHERE table_name = '{table_name}'")
        existing_cols = [row[0] for row in cursor.fetchall()]
        print(f"  📊 현재 컬럼 목록: {existing_cols}")

        for col_name, col_type in required_cols.items():
            if col_name not in existing_cols:
                print(f"  🔧 누락된 [{col_name}] 컬럼 추가 중...")
                cursor.execute(f"ALTER TABLE LOL_APP.{table_name} ADD ({col_name} {col_type})")
                print(f"  ✅ [{col_name}] 컬럼 추가 완료!")
            else:
                print(f"  ✅ [{col_name}] 컬럼 정상 확인")

    conn.commit()
    cursor.close()
    conn.close()
    print("\n🎉 모든 DB 테이블 스키마 점검 및 자동 보정이 완벽히 완료되었습니다!")

if __name__ == "__main__":
    inspect_and_fix_all_tables()