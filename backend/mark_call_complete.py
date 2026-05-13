"""Mark the latest call as completed"""
import asyncio
from sqlalchemy import desc, select
from app.database import async_session_factory
from app.models.call import Call


async def mark_latest_call_complete():
    async with async_session_factory() as session:
        # Get the latest call
        result = await session.execute(
            select(Call).order_by(desc(Call.created_at)).limit(1)
        )
        latest_call = result.scalar_one_or_none()
        
        if not latest_call:
            print('No calls found in database')
            return
        
        print(f'Call ID: {latest_call.id}')
        print(f'Current Status: {latest_call.status}')
        
        if latest_call.status == 'in_progress':
            latest_call.status = 'completed'
            await session.commit()
            print('✅ Status updated to: completed')
        else:
            print(f'Status is already: {latest_call.status}')


if __name__ == '__main__':
    asyncio.run(mark_latest_call_complete())
