"""Check the most recent calls"""
import asyncio
from sqlalchemy import desc, select
from app.database import async_session_factory
from app.models.call import Call


async def check_recent_calls():
    async with async_session_factory() as session:
        # Get the 5 most recent calls
        result = await session.execute(
            select(Call).order_by(desc(Call.created_at)).limit(5)
        )
        calls = result.scalars().all()
        
        if not calls:
            print('No calls found in database')
            return
        
        print(f'=== RECENT CALLS (showing {len(calls)}) ===\n')
        for i, call in enumerate(calls, 1):
            print(f'{i}. Call ID: {call.id}')
            print(f'   Created: {call.created_at}')
            print(f'   Started: {call.started_at}')
            print(f'   Ended: {call.ended_at}')
            print(f'   Status: {call.status}')
            print(f'   Duration: {call.duration_seconds}s')
            print(f'   Phone: {call.phone_number}')
            print()


if __name__ == '__main__':
    asyncio.run(check_recent_calls())
