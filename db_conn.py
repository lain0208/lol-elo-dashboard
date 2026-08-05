import os
import sys
import oracledb
from dotenv import load_dotenv

# .env 환경변수 강제 새로고침
load_dotenv(override=True)

def get_db_connection():
    # 1. 환경 변수 유연하게 읽어오기
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_dsn = os.getenv('DB_DSN')
    wallet_dir = os.getenv('DB_WALLET_LOCATION') or os.getenv('WALLET_DIR')
    wallet_password = os.getenv('DB_WALLET_PASSWORD') or os.getenv('WALLET_PASSWORD')

    # 지갑 경로 절대경로 보정
    if wallet_dir and not os.path.isabs(wallet_dir):
        wallet_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), wallet_dir))

    # 2. DB 연결 시도 및 중앙화된 에러 처리
    try:
        conn = oracledb.connect(
            user=db_user,
            password=db_password,
            dsn=db_dsn,
            config_dir=wallet_dir,
            wallet_location=wallet_dir,  # ✅ 테스트 코드처럼 이 옵션을 명시적으로 추가!
            wallet_password=wallet_password
        )
        return conn
        
    except oracledb.DatabaseError as e:
        error_obj, = e.args
        print(f"🚨 [DB 연결 실패] 원인: {error_obj.message}")
        print("👉 .env 파일의 정보나 오라클 클라우드 상태를 확인해 주세요.")
        sys.exit(1)
        
    except Exception as e:
        print(f"🚨 [DB 연결 실패] 알 수 없는 오류: {str(e)}")
        sys.exit(1)