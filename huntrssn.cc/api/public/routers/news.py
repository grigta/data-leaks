from fastapi import APIRouter, Depends, Request, Response, Query, HTTPException
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from api.common.database import get_postgres_session
from api.common.models_postgres import News
from api.public.dependencies import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


class NewsResponse(BaseModel):
    id: str
    title: str
    content: str
    created_at: Optional[datetime]

    @classmethod
    def from_news(cls, news: News):
        return cls(
            id=str(news.id),
            title=news.title,
            content=news.content,
            created_at=news.created_at
        )


class NewsListResponse(BaseModel):
    news: List[NewsResponse]
    total: int
    limit: int
    offset: int


@router.get("/", response_model=NewsListResponse)
@limiter.limit("100/hour")
async def get_news_list(
    request: Request,
    response: Response,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_postgres_session)
):
    try:
        # Get news list with pagination
        news_query = select(News).order_by(News.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(news_query)
        news_list = result.scalars().all()

        # Get total count
        count_query = select(func.count()).select_from(News)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Convert to response models
        news_responses = [NewsResponse.from_news(news) for news in news_list]

        return NewsListResponse(
            news=news_responses,
            total=total,
            limit=limit,
            offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching news list")
        raise HTTPException(status_code=500, detail="Failed to fetch news list")
