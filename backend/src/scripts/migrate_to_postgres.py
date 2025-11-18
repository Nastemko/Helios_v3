"""
Migrate data from SQLite to PostgreSQL

Usage:
    python scripts/migrate_to_postgres.py

Environment variables needed:
    DATABASE_URL=postgresql://heliosuser:password@localhost/helios

This script will:
1. Read all data from SQLite
2. Write it to PostgreSQL
3. Verify the migration
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_data(sqlite_url: str, postgres_url: str):
    """Migrate all data from SQLite to PostgreSQL"""
    
    logger.info("=" * 60)
    logger.info("SQLite to PostgreSQL Migration")
    logger.info("=" * 60)
    
    # Create engines
    logger.info(f"Connecting to SQLite: {sqlite_url}")
    sqlite_engine = create_engine(sqlite_url)
    
    logger.info(f"Connecting to PostgreSQL: {postgres_url.split('@')[1]}")  # Hide password
    postgres_engine = create_engine(postgres_url)
    
    # Create sessions
    SqliteSession = sessionmaker(bind=sqlite_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)
    
    sqlite_session = SqliteSession()
    postgres_session = PostgresSession()
    
    # Get metadata
    metadata = MetaData()
    metadata.reflect(bind=sqlite_engine)
    
    # Create tables in PostgreSQL
    logger.info("\nCreating tables in PostgreSQL...")
    from models import Base
    Base.metadata.create_all(bind=postgres_engine)
    logger.info("✓ Tables created")
    
    # Migrate each table
    tables_to_migrate = ['users', 'texts', 'text_segments', 'annotations']
    
    for table_name in tables_to_migrate:
        if table_name not in metadata.tables:
            logger.warning(f"⚠ Table '{table_name}' not found in SQLite, skipping")
            continue
            
        logger.info(f"\nMigrating table: {table_name}")
        table = Table(table_name, metadata, autoload_with=sqlite_engine)
        
        # Read from SQLite
        rows = sqlite_session.execute(table.select()).fetchall()
        row_count = len(rows)
        logger.info(f"  Found {row_count} rows")
        
        if row_count == 0:
            logger.info("  No data to migrate")
            continue
        
        # Write to PostgreSQL
        try:
            # Convert rows to dicts
            columns = [col.name for col in table.columns]
            data = [dict(zip(columns, row)) for row in rows]
            
            # Insert in batches
            batch_size = 100
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                postgres_session.execute(table.insert(), batch)
                postgres_session.commit()
                logger.info(f"  Inserted {min(i + batch_size, len(data))}/{len(data)} rows")
            
            logger.info(f"✓ Successfully migrated {row_count} rows")
            
        except Exception as e:
            logger.error(f"✗ Error migrating {table_name}: {e}")
            postgres_session.rollback()
            raise
    
    # Verify migration
    logger.info("\n" + "=" * 60)
    logger.info("Verification")
    logger.info("=" * 60)
    
    for table_name in tables_to_migrate:
        if table_name not in metadata.tables:
            continue
            
        table = Table(table_name, metadata, autoload_with=sqlite_engine)
        
        sqlite_count = sqlite_session.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).scalar()
        
        postgres_count = postgres_session.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).scalar()
        
        status = "✓" if sqlite_count == postgres_count else "✗"
        logger.info(f"{status} {table_name}: SQLite={sqlite_count}, PostgreSQL={postgres_count}")
        
        if sqlite_count != postgres_count:
            raise Exception(f"Row count mismatch in {table_name}!")
    
    logger.info("\n" + "=" * 60)
    logger.info("✓ Migration completed successfully!")
    logger.info("=" * 60)
    
    sqlite_session.close()
    postgres_session.close()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Get database URLs
    sqlite_url = "sqlite:///./helios_local.db"
    postgres_url = os.getenv("DATABASE_URL")
    
    if not postgres_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Example: DATABASE_URL=postgresql://heliosuser:password@localhost/helios")
        sys.exit(1)
    
    if not postgres_url.startswith("postgresql"):
        print("Error: DATABASE_URL must be a PostgreSQL URL")
        sys.exit(1)
    
    # Confirm
    print(f"\nMigration Plan:")
    print(f"  From: {sqlite_url}")
    print(f"  To:   {postgres_url.split('@')[1]}")  # Hide password
    print(f"\nThis will copy all data from SQLite to PostgreSQL.")
    print(f"PostgreSQL tables will be created if they don't exist.")
    
    response = input("\nProceed? (yes/no): ")
    if response.lower() != "yes":
        print("Migration cancelled")
        sys.exit(0)
    
    try:
        migrate_data(sqlite_url, postgres_url)
    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}")
        sys.exit(1)

