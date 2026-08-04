import oracledb
from db_conn import get_db_connection

def reset_database():
    # 1. db.py의 공통 함수를 사용하여 안전하게 DB 연결 (비밀번호 묻지 않음!)
    conn = get_db_connection()
    cursor = conn.cursor()

    # 2. 기존 테이블 삭제 (종속성 고려하여 역순으로 DROP)
    tables_to_drop = [
        "MATCH_PARTICIPANT_RAW",
        "MATCH_PARTICIPANTS",
        "MATCHES",
        "SUMMONER_NAME_HISTORY",
        "USERS"
    ]
    
    print("🗑️ 기존 테이블 삭제를 시작합니다...")
    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE {table} CASCADE CONSTRAINTS")
            print(f"  - {table} 테이블 삭제 완료")
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            # ORA-00942: 테이블 또는 뷰가 존재하지 않습니다 (무시하고 진행)
            if error_obj.code == 942:
                print(f"  - {table} 테이블이 존재하지 않아 건너뜁니다.")
            else:
                print(f"  - {table} 테이블 삭제 중 오류: {error_obj.message}")

    print("\n🔨 신규 테이블 생성을 시작합니다...")

    # 3. 테이블 생성 DDL 스크립트 모음
    create_queries = [
        # ① USERS 테이블
        """
        CREATE TABLE USERS (
            PUUID VARCHAR2(100) PRIMARY KEY,
            SUMMONER_NAME VARCHAR2(100) NOT NULL,
            REAL_NAME VARCHAR2(50),
            IS_REGISTERED VARCHAR2(1) DEFAULT 'N' CHECK (IS_REGISTERED IN ('Y', 'N')),
            ELO_RATING NUMBER DEFAULT 1200 NOT NULL,
            WINS NUMBER DEFAULT 0 NOT NULL,
            LOSSES NUMBER DEFAULT 0 NOT NULL
        )
        """,
        
        # ② SUMMONER_NAME_HISTORY 테이블
        """
        CREATE TABLE SUMMONER_NAME_HISTORY (
            HISTORY_ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            PUUID VARCHAR2(100) NOT NULL,
            OLD_SUMMONER_NAME VARCHAR2(100) NOT NULL,
            NEW_SUMMONER_NAME VARCHAR2(100) NOT NULL,
            CHANGED_AT TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT FK_SNH_PUUID FOREIGN KEY (PUUID) REFERENCES USERS(PUUID) ON DELETE CASCADE
        )
        """,
        
        # ③ MATCHES 테이블
        """
        CREATE TABLE MATCHES (
            MATCH_ID VARCHAR2(50) PRIMARY KEY,
            GAME_CREATION TIMESTAMP NOT NULL,
            GAME_DURATION NUMBER NOT NULL,
            WINNING_TEAM NUMBER NOT NULL,
            GAME_MODE VARCHAR2(20) NOT NULL,
            PARTICIPANT_COUNT NUMBER DEFAULT 10 NOT NULL
        )
        """,
        
        # ④ MATCH_PARTICIPANTS 테이블 (끊겼던 35개 메인 지표 완벽 복구)
        """
        CREATE TABLE MATCH_PARTICIPANTS (
            MATCH_ID VARCHAR2(50) NOT NULL,
            PUUID VARCHAR2(100) NOT NULL,
            TEAM_ID NUMBER NOT NULL,
            POSITION VARCHAR2(20),
            CHAMPION_NAME VARCHAR2(50) NOT NULL,
            
            -- 기본 KDA 및 전투 지표
            KILLS NUMBER DEFAULT 0 NOT NULL,
            DEATHS NUMBER DEFAULT 0 NOT NULL,
            ASSISTS NUMBER DEFAULT 0 NOT NULL,
            KDA NUMBER(5,2) DEFAULT 0.0 NOT NULL,
            
            -- 데미지 및 회복 지표
            TOTAL_DAMAGE_DEALT NUMBER DEFAULT 0 NOT NULL,
            TOTAL_DAMAGE_TAKEN NUMBER DEFAULT 0 NOT NULL,
            TOTAL_HEAL NUMBER DEFAULT 0 NOT NULL,
            
            -- 성장 지표
            GOLD_EARNED NUMBER DEFAULT 0 NOT NULL,
            TOTAL_MINIONS_KILLED NUMBER DEFAULT 0 NOT NULL,
            NEUTRAL_MINIONS_KILLED NUMBER DEFAULT 0 NOT NULL,
            
            -- 시야 및 특수 킬
            VISION_SCORE NUMBER DEFAULT 0 NOT NULL,
            PENTA_KILLS NUMBER DEFAULT 0 NOT NULL,
            SOLO_KILLS NUMBER DEFAULT 0 NOT NULL,
            
            -- [대시보드 표시용 추가 17개 지표] (총 35개 지표 구성)
            MAGIC_DAMAGE_DEALT NUMBER DEFAULT 0,
            PHYSICAL_DAMAGE_DEALT NUMBER DEFAULT 0,
            TRUE_DAMAGE_DEALT NUMBER DEFAULT 0,
            LARGEST_MULTI_KILL NUMBER DEFAULT 0,
            TIME_CCING_OTHERS NUMBER DEFAULT 0,
            DAMAGE_DEALT_TO_OBJECTIVES NUMBER DEFAULT 0,
            DAMAGE_DEALT_TO_TURRETS NUMBER DEFAULT 0,
            DAMAGE_SELF_MITIGATED NUMBER DEFAULT 0,
            WARDS_PLACED NUMBER DEFAULT 0,
            WARDS_KILLED NUMBER DEFAULT 0,
            CONTROL_WARDS_PLACED NUMBER DEFAULT 0,
            FIRST_BLOOD_KILL NUMBER DEFAULT 0,
            FIRST_BLOOD_ASSIST NUMBER DEFAULT 0,
            FIRST_TOWER_KILL NUMBER DEFAULT 0,
            FIRST_TOWER_ASSIST NUMBER DEFAULT 0,
            ITEM_0 NUMBER DEFAULT 0,
            ITEM_1 NUMBER DEFAULT 0,
            
            -- 복합 기본키 및 외래키 설정
            PRIMARY KEY (MATCH_ID, PUUID),
            CONSTRAINT FK_MP_MATCH FOREIGN KEY (MATCH_ID) REFERENCES MATCHES(MATCH_ID) ON DELETE CASCADE,
            CONSTRAINT FK_MP_USER FOREIGN KEY (PUUID) REFERENCES USERS(PUUID) ON DELETE CASCADE
        )
        """,
        
        # ⑤ MATCH_PARTICIPANT_RAW 테이블 (라이엇 155개 JSON 원본 1:1 보관용)
        """
        CREATE TABLE MATCH_PARTICIPANT_RAW (
            MATCH_ID VARCHAR2(50) NOT NULL,
            PUUID VARCHAR2(100) NOT NULL,
            RAW_DATA CLOB NOT NULL,
            
            -- 복합 기본키 및 외래키 설정
            PRIMARY KEY (MATCH_ID, PUUID),
            CONSTRAINT FK_MPR_MATCH FOREIGN KEY (MATCH_ID) REFERENCES MATCHES(MATCH_ID) ON DELETE CASCADE,
            CONSTRAINT FK_MPR_USER FOREIGN KEY (PUUID) REFERENCES USERS(PUUID) ON DELETE CASCADE
        )
        """
    ]

    for query in create_queries:
        try:
            cursor.execute(query)
            # 쿼리의 첫 단어 2개(예: CREATE TABLE) 추출해서 출력
            action = " ".join(query.strip().split()[:3]) 
            print(f"  - ✅ {action} 생성 완료")
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            print(f"  - ❌ 테이블 생성 중 오류 발생: {error_obj.message}")

    conn.commit()
    cursor.close()
    conn.close()
    print("\n🎉 모든 DB 테이블 리셋 및 초기화가 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    reset_database()