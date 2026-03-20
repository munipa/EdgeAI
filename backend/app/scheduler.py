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


def sync_nba_team_stats():
    db = SessionLocal()
    try:
        espn.sync_all_team_stats(db=db)
    except Exception as e:
        print(f"Scheduler: error syncing NBA team stats — {e}")
    finally:
        db.close()


def sync_nba_injuries():
    db = SessionLocal()
    try:
        espn.get_nba_injuries(db=db)
        print("Scheduler: synced NBA injuries")
    except Exception as e:
        print(f"Scheduler: error syncing NBA injuries — {e}")
    finally:
        db.close()


def start():
    # Run all syncs once at startup
    sync_todays_nba_games()
    sync_nba_team_stats()
    sync_nba_injuries()
    # Then daily at 3am
    scheduler.add_job(sync_todays_nba_games, "cron", hour=3, minute=0)
    scheduler.add_job(sync_nba_team_stats, "cron", hour=3, minute=5)
    scheduler.add_job(sync_nba_injuries, "cron", hour=3, minute=10)
    scheduler.start()


def stop():
    scheduler.shutdown()
