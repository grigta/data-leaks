from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import logging

from api.common.database import get_postgres_session
from api.common.models_postgres import News, User
from api.admin.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic models
class CreateNewsRequest(BaseModel):
    title: str = Field(max_length=200, description="News title")
    content: str = Field(description="News content")


class UpdateNewsRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None)


class NewsResponse(BaseModel):
    id: str
    title: str
    content: str
    author_id: str
    author_username: str
    created_at: str
    updated_at: str

    @classmethod
    def from_news(cls, news: News) -> "NewsResponse":
        return cls(
            id=str(news.id),
            title=news.title,
            content=news.content,
            author_id=str(news.author_id),
            author_username=news.author.username if news.author else "Unknown",
            created_at=news.created_at.isoformat(),
            updated_at=news.updated_at.isoformat()
        )


class NewsListResponse(BaseModel):
    news: List[NewsResponse]
    total_count: int


# Endpoints
@router.post("/", response_model=NewsResponse, status_code=status.HTTP_201_CREATED)
async def create_news(
    request: CreateNewsRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Create a new news article"""
    try:
        new_news = News(
            title=request.title,
            content=request.content,
            author_id=admin_user.id
        )
        db.add(new_news)
        await db.commit()
        await db.refresh(new_news)

        # Reload with author relationship
        query = select(News).options(selectinload(News.author)).where(News.id == new_news.id)
        result = await db.execute(query)
        news_with_author = result.scalar_one()

        logger.info(f"Admin {admin_user.username} created news {news_with_author.id}")
        return NewsResponse.from_news(news_with_author)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create news: {str(e)}"
        )


@router.get("/", response_model=NewsListResponse)
async def list_news(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Get list of all news articles"""
    try:
        # Get news with author relationship
        query = select(News).options(selectinload(News.author)).order_by(News.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        news_list = result.scalars().all()

        # Get total count
        count_query = select(func.count(News.id))
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        return NewsListResponse(
            news=[NewsResponse.from_news(news) for news in news_list],
            total_count=total_count
        )
    except Exception as e:
        logger.error(f"Error listing news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list news: {str(e)}"
        )


@router.get("/{news_id}", response_model=NewsResponse)
async def get_news(
    news_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Get a single news article by ID"""
    try:
        query = select(News).options(selectinload(News.author)).where(News.id == news_id)
        result = await db.execute(query)
        news = result.scalar_one_or_none()

        if not news:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="News not found"
            )

        return NewsResponse.from_news(news)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting news {news_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get news: {str(e)}"
        )


@router.patch("/{news_id}", response_model=NewsResponse)
async def update_news(
    news_id: UUID,
    request: UpdateNewsRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Update a news article"""
    try:
        query = select(News).where(News.id == news_id)
        result = await db.execute(query)
        news = result.scalar_one_or_none()

        if not news:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="News not found"
            )

        # Update fields if provided
        if request.title is not None:
            news.title = request.title
        if request.content is not None:
            news.content = request.content

        await db.commit()
        await db.refresh(news)

        # Reload with author relationship
        query = select(News).options(selectinload(News.author)).where(News.id == news_id)
        result = await db.execute(query)
        news_with_author = result.scalar_one()

        logger.info(f"Admin {admin_user.username} updated news {news_id}")
        return NewsResponse.from_news(news_with_author)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating news {news_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update news: {str(e)}"
        )


@router.delete("/{news_id}")
async def delete_news(
    news_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """Delete a news article"""
    try:
        query = select(News).where(News.id == news_id)
        result = await db.execute(query)
        news = result.scalar_one_or_none()

        if not news:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="News not found"
            )

        await db.delete(news)
        await db.commit()

        logger.info(f"Admin {admin_user.username} deleted news {news_id}")
        return {"message": "News deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting news {news_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete news: {str(e)}"
        )
