"""
SearchBug Cache Service

Provides caching layer for SearchBug API responses to avoid duplicate API calls.
Cache entries expire after 30 days by default (configurable via SEARCHBUG_CACHE_TTL_DAYS).

Usage:
    from api.common.searchbug_cache import SearchBugCacheService

    cache_service = SearchBugCacheService(db_session)

    # Search with caching (will use cache if available, otherwise call API)
    result = await cache_service.search_person_unified_cached(
        searchbug_client=client,
        firstname="John",
        lastname="Doe",
        address="123 Main St"
    )
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from api.common.models_postgres import SearchBugCache

logger = logging.getLogger("searchbug_cache")

# Default cache TTL in days
CACHE_TTL_DAYS = int(os.getenv("SEARCHBUG_CACHE_TTL_DAYS", "30"))


class SearchBugCacheService:
    """
    Service for caching SearchBug API responses.

    Provides methods to:
    - Check cache for existing responses
    - Store new responses in cache
    - Search with automatic caching
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize cache service.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self.ttl_days = CACHE_TTL_DAYS

    async def get_cached_response(
        self,
        firstname: str,
        lastname: str,
        address: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached SearchBug response if available and not expired.

        Args:
            firstname: First name
            lastname: Last name
            address: Street address (optional)
            zipcode: ZIP code (optional)

        Returns:
            Cached response data or None if not found/expired
        """
        cache_key = SearchBugCache.generate_cache_key(
            firstname=firstname,
            lastname=lastname,
            address=address,
            zipcode=zipcode
        )

        stmt = select(SearchBugCache).where(
            SearchBugCache.cache_key == cache_key,
            SearchBugCache.expires_at > datetime.utcnow()
        )

        result = await self.db.execute(stmt)
        cache_entry = result.scalar_one_or_none()

        if cache_entry:
            # Update hit count and last_hit_at
            await self.db.execute(
                update(SearchBugCache)
                .where(SearchBugCache.id == cache_entry.id)
                .values(
                    hit_count=SearchBugCache.hit_count + 1,
                    last_hit_at=datetime.utcnow()
                )
            )
            await self.db.commit()

            logger.info(
                f"Cache HIT for {firstname} {lastname} "
                f"(key={cache_key[:50]}..., hits={cache_entry.hit_count + 1})"
            )

            # Return None if data was not found in original request
            if not cache_entry.data_found:
                return None

            return cache_entry.response_data

        logger.info(f"Cache MISS for {firstname} {lastname} (key={cache_key[:50]}...)")
        return None

    async def set_cached_response(
        self,
        firstname: str,
        lastname: str,
        address: Optional[str] = None,
        zipcode: Optional[str] = None,
        response_data: Optional[Dict[str, Any]] = None,
        data_found: bool = False
    ) -> None:
        """
        Store SearchBug response in cache.

        Args:
            firstname: First name
            lastname: Last name
            address: Street address (optional)
            zipcode: ZIP code (optional)
            response_data: Full SearchBug API response (or None if not found)
            data_found: Whether the search returned any data
        """
        cache_key = SearchBugCache.generate_cache_key(
            firstname=firstname,
            lastname=lastname,
            address=address,
            zipcode=zipcode
        )

        search_params = {
            "firstname": firstname,
            "lastname": lastname,
            "address": address,
            "zipcode": zipcode
        }

        expires_at = datetime.utcnow() + timedelta(days=self.ttl_days)

        # Use upsert to handle concurrent requests
        stmt = insert(SearchBugCache).values(
            cache_key=cache_key,
            search_params=search_params,
            response_data=response_data or {},
            data_found=data_found,
            hit_count=0,
            created_at=datetime.utcnow(),
            expires_at=expires_at
        ).on_conflict_do_update(
            index_elements=['cache_key'],
            set_={
                'response_data': response_data or {},
                'data_found': data_found,
                'expires_at': expires_at,
                'hit_count': 0,
                'last_hit_at': None
            }
        )

        await self.db.execute(stmt)
        await self.db.commit()

        logger.info(
            f"Cache SET for {firstname} {lastname} "
            f"(key={cache_key[:50]}..., data_found={data_found}, ttl={self.ttl_days}d)"
        )

    async def search_person_unified_cached(
        self,
        searchbug_client,
        firstname: str,
        lastname: str,
        zipcode: Optional[str] = None,
        address: Optional[str] = None,
        limit: Optional[int] = None,
        bypass_cache: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Search for person with automatic caching.

        1. Check cache for existing response
        2. If cache hit - return cached data
        3. If cache miss - call SearchBug API and cache response

        Args:
            searchbug_client: Initialized SearchbugClient instance
            firstname: First name (required)
            lastname: Last name (required)
            zipcode: ZIP code (optional)
            address: Street address (optional)
            limit: Maximum number of results
            bypass_cache: If True, skip cache lookup and force API call

        Returns:
            Person data dict or None if not found
        """
        # Check cache first (unless bypassed)
        if not bypass_cache:
            cached_response = await self.get_cached_response(
                firstname=firstname,
                lastname=lastname,
                address=address,
                zipcode=zipcode
            )

            if cached_response is not None:
                logger.info(f"Returning cached response for {firstname} {lastname}")
                return cached_response

            # Check if we have a cached "not found" entry
            cache_key = SearchBugCache.generate_cache_key(
                firstname=firstname,
                lastname=lastname,
                address=address,
                zipcode=zipcode
            )

            stmt = select(SearchBugCache).where(
                SearchBugCache.cache_key == cache_key,
                SearchBugCache.expires_at > datetime.utcnow(),
                SearchBugCache.data_found == False
            )
            result = await self.db.execute(stmt)
            not_found_entry = result.scalar_one_or_none()

            if not_found_entry:
                # Update hit count
                await self.db.execute(
                    update(SearchBugCache)
                    .where(SearchBugCache.id == not_found_entry.id)
                    .values(
                        hit_count=SearchBugCache.hit_count + 1,
                        last_hit_at=datetime.utcnow()
                    )
                )
                await self.db.commit()

                logger.info(
                    f"Cache HIT (not_found) for {firstname} {lastname} "
                    f"(hits={not_found_entry.hit_count + 1})"
                )
                return None

        # Cache miss - call SearchBug API
        logger.info(f"Calling SearchBug API for {firstname} {lastname}")

        person_data = await searchbug_client.search_person_unified(
            firstname=firstname,
            lastname=lastname,
            zipcode=zipcode,
            address=address,
            limit=limit
        )

        # Cache the response (whether found or not)
        await self.set_cached_response(
            firstname=firstname,
            lastname=lastname,
            address=address,
            zipcode=zipcode,
            response_data=person_data,
            data_found=person_data is not None
        )

        return person_data

    async def invalidate_cache(
        self,
        firstname: str,
        lastname: str,
        address: Optional[str] = None,
        zipcode: Optional[str] = None
    ) -> bool:
        """
        Invalidate (delete) a specific cache entry.

        Args:
            firstname: First name
            lastname: Last name
            address: Street address (optional)
            zipcode: ZIP code (optional)

        Returns:
            True if entry was deleted, False if not found
        """
        from sqlalchemy import delete

        cache_key = SearchBugCache.generate_cache_key(
            firstname=firstname,
            lastname=lastname,
            address=address,
            zipcode=zipcode
        )

        stmt = delete(SearchBugCache).where(SearchBugCache.cache_key == cache_key)
        result = await self.db.execute(stmt)
        await self.db.commit()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"Cache INVALIDATED for {firstname} {lastname}")

        return deleted

    async def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries deleted
        """
        from sqlalchemy import delete

        stmt = delete(SearchBugCache).where(
            SearchBugCache.expires_at < datetime.utcnow()
        )
        result = await self.db.execute(stmt)
        await self.db.commit()

        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info(f"Cache CLEANUP: removed {deleted_count} expired entries")

        return deleted_count

    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        from sqlalchemy import func

        # Total entries
        total_stmt = select(func.count()).select_from(SearchBugCache)
        total_result = await self.db.execute(total_stmt)
        total_count = total_result.scalar()

        # Active (non-expired) entries
        active_stmt = select(func.count()).select_from(SearchBugCache).where(
            SearchBugCache.expires_at > datetime.utcnow()
        )
        active_result = await self.db.execute(active_stmt)
        active_count = active_result.scalar()

        # Entries with data found
        found_stmt = select(func.count()).select_from(SearchBugCache).where(
            SearchBugCache.data_found == True,
            SearchBugCache.expires_at > datetime.utcnow()
        )
        found_result = await self.db.execute(found_stmt)
        found_count = found_result.scalar()

        # Total hits
        hits_stmt = select(func.sum(SearchBugCache.hit_count)).select_from(SearchBugCache)
        hits_result = await self.db.execute(hits_stmt)
        total_hits = hits_result.scalar() or 0

        return {
            "total_entries": total_count,
            "active_entries": active_count,
            "expired_entries": total_count - active_count,
            "entries_with_data": found_count,
            "entries_not_found": active_count - found_count,
            "total_hits": total_hits,
            "ttl_days": self.ttl_days
        }
