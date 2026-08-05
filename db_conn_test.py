import os
import oracledb
from dotenv import load_dotenv

# .env 파일 환경변수 로드
load_dotenv()

def test_connection():
    try:
        # DB 연결 (Thin Mode + Wallet 설정)
        connection = oracledb.connect(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            dsn=os.getenv("DB_DSN"),
            config_dir=os.getenv("WALLET_DIR"),
            wallet_location=os.getenv("WALLET_DIR"),
            wallet_password=os.getenv("WALLET_PASSWORD")
        )
        
        print("🎉 오라클 DB 연결 성공!")
        
        # 쿼리 테스트 (생성해둔 USERS 및 MATCHES 테이블 존재 여부 확인)
        cursor = connection.cursor()
        cursor.execute("SELECT table_name FROM user_tables")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"📊 LOL_APP 스키마의 테이블 목록: {tables}")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")

if __name__ == "__main__":
    test_connection()