from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.database import SessionLocal
from app.services.espn_service import ESPNService

scheduler = AsyncIOScheduler()
espn = ESPNService()


def sync_todays_nba_games():
    db = SessionLocal()
    try:
        espn.get_nba_games(db=db)
        print("Scheduler: synced today's NBA games")
    except Exception as e:
        print(f"Scheduler: error syncing NBA games — {e}")
    finally:
        db.close()


def start():
    # Run once at startup, then every day at 3am
    sync_todays_nba_games()
    scheduler.add_job(sync_todays_nba_games, "cron", hour=3, minute=0)
    scheduler.start()


def stop():
    scheduler.shutdown()
