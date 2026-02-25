"""
Test Polygon Router — batch testing of search flows.
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.admin.dependencies import get_current_admin_user
from api.common.database import get_postgres_session, async_session_maker
from api.common.models_postgres import (
    User, TestPolygon, TestPolygonRecord, TestPolygonRun, TestPolygonResult
)


router = APIRouter(prefix="/test-polygon", tags=["Test Polygon"])
logger = logging.getLogger(__name__)

# Name suffixes to strip when parsing fullname
_NAME_SUFFIXES = {'JR', 'SR', 'II', 'III', 'IV', 'V', 'JR.', 'SR.'}


def _parse_fullname(fullname: str):
    """Parse fullname handling middle names and JR/SR/III suffixes.

    Returns (firstname, middlename, lastname) or raises ValueError.
    """
    parts = fullname.strip().upper().split()
    if len(parts) < 2:
        raise ValueError(f"Cannot parse fullname: {fullname}")

    # Strip suffixes from end
    while len(parts) > 2 and parts[-1] in _NAME_SUFFIXES:
        parts.pop()

    if len(parts) < 2:
        raise ValueError(f"Cannot parse fullname after suffix removal: {fullname}")

    firstname = parts[0]
    lastname = parts[-1]
    middlename = ' '.join(parts[1:-1]) if len(parts) > 2 else None

    return firstname, middlename, lastname


def _parse_address_string(address_str: str):
    """Parse address string like '201 NORTHPOINT AVE, HIGH POINT, NC 27262' into components.

    Returns dict with keys: street, city, state, zip.
    """
    parts = [p.strip() for p in address_str.split(',')]
    street = parts[0] if parts else ''
    city = ''
    state_val = ''
    zip_code = ''

    if len(parts) >= 3:
        city = parts[1].strip()
        # Last part(s) could be "NC 27262" or state and zip are separate parts
        if len(parts) == 3:
            # "street, city, state zip"
            last_tokens = parts[2].strip().split()
            if len(last_tokens) >= 2 and len(last_tokens[0]) == 2 and last_tokens[0].isalpha():
                state_val = last_tokens[0]
                zip_code = last_tokens[1]
            elif len(last_tokens) == 1 and len(last_tokens[0]) == 2 and last_tokens[0].isalpha():
                state_val = last_tokens[0]
        elif len(parts) >= 4:
            # "street, city, state, zip" or "street, city, state, zip, extra..."
            state_candidate = parts[2].strip()
            if len(state_candidate) == 2 and state_candidate.isalpha():
                state_val = state_candidate
                zip_code = parts[3].strip().split()[0] if parts[3].strip() else ''
            else:
                # Maybe "street, city extra, state zip"
                last_tokens = parts[-1].strip().split()
                if len(last_tokens) >= 2 and len(last_tokens[0]) == 2 and last_tokens[0].isalpha():
                    state_val = last_tokens[0]
                    zip_code = last_tokens[1]
    elif len(parts) == 2:
        # "street, state zip" or "street, city"
        last_tokens = parts[1].strip().split()
        if len(last_tokens) >= 2 and len(last_tokens[0]) == 2 and last_tokens[0].isalpha():
            state_val = last_tokens[0]
            zip_code = last_tokens[1]

    return {
        'street': street.upper(),
        'city': city.upper(),
        'state': state_val.upper(),
        'zip': zip_code,
    }


# ── Pydantic models ──────────────────────────────────────────────

class RecordInput(BaseModel):
    fullname: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=2, max_length=500)
    expected_ssn: str = Field(min_length=4, max_length=11)


class CreateTestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    records: List[RecordInput] = Field(default_factory=list)


class UpdateTestRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    records: Optional[List[RecordInput]] = None


class RunTestRequest(BaseModel):
    provider: str = "searchbug"  # searchbug | whitepages
    save_debug: bool = True
    parallelism: int = Field(default=5, ge=1, le=20)
    prioritization: str = Field(default="default", pattern=r"^(default|quality_first|quantity_first)$")


class RecordResponse(BaseModel):
    id: str
    fullname: str
    address: str
    expected_ssn: str
    sort_order: int


class TestResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    records_count: int
    created_at: str
    updated_at: str
    last_run: Optional[dict] = None  # summary of latest run


class TestDetailResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    records: List[RecordResponse]
    created_at: str
    updated_at: str


class RunResponse(BaseModel):
    id: str
    test_id: str
    test_name: str
    flow_config: Optional[dict]
    status: str
    total_records: int
    processed_count: int
    matched_count: int
    not_found_count: int
    wrong_ssn_count: int
    error_count: int
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str


class ResultResponse(BaseModel):
    id: str
    record_id: str
    fullname: str
    address: str
    expected_ssn: str
    status: str  # match, not_found, wrong_ssn, error
    found_ssn: Optional[str]
    best_method: Optional[str]
    matched_keys_count: int
    total_candidates: int
    search_time: Optional[float]
    error_message: Optional[str]
    sort_order: int


class ResultsListResponse(BaseModel):
    results: List[ResultResponse]
    total_count: int


class TestsListResponse(BaseModel):
    tests: List[TestResponse]
    total_count: int


# ── Helper: normalize SSN for comparison ─────────────────────────

def _normalize_ssn(ssn: str) -> str:
    """Remove dashes and spaces from SSN for comparison."""
    return re.sub(r'[\s\-]', '', ssn)


# ── CRUD Endpoints ───────────────────────────────────────────────

@router.get("/tests", response_model=TestsListResponse)
async def list_tests(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """List all test polygon sets with last run summary."""
    # Count total
    count_q = select(func.count(TestPolygon.id))
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch tests with record counts
    q = (
        select(TestPolygon)
        .order_by(desc(TestPolygon.updated_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    tests = result.scalars().all()

    items = []
    for t in tests:
        # Count records
        rec_count = (await db.execute(
            select(func.count(TestPolygonRecord.id)).where(TestPolygonRecord.test_id == t.id)
        )).scalar() or 0

        # Get latest run
        latest_run_q = (
            select(TestPolygonRun)
            .where(TestPolygonRun.test_id == t.id)
            .order_by(desc(TestPolygonRun.created_at))
            .limit(1)
        )
        latest_run = (await db.execute(latest_run_q)).scalar_one_or_none()

        last_run_data = None
        if latest_run:
            last_run_data = {
                "id": str(latest_run.id),
                "status": latest_run.status,
                "total_records": latest_run.total_records,
                "matched_count": latest_run.matched_count,
                "not_found_count": latest_run.not_found_count,
                "wrong_ssn_count": latest_run.wrong_ssn_count,
                "error_count": latest_run.error_count,
                "match_rate": round(latest_run.matched_count / latest_run.total_records * 100, 1) if latest_run.total_records > 0 else 0,
                "flow_config": latest_run.flow_config,
                "finished_at": latest_run.finished_at.isoformat() if latest_run.finished_at else None,
                "created_at": latest_run.created_at.isoformat(),
            }

        items.append(TestResponse(
            id=str(t.id),
            name=t.name,
            description=t.description,
            records_count=rec_count,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
            last_run=last_run_data,
        ))

    return TestsListResponse(tests=items, total_count=total)


@router.post("/tests", response_model=TestResponse, status_code=201)
async def create_test(
    request: CreateTestRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new test polygon set."""
    test = TestPolygon(
        name=request.name,
        description=request.description,
        created_by=current_user.id,
    )
    db.add(test)
    await db.flush()

    # Add records
    for i, rec in enumerate(request.records):
        db.add(TestPolygonRecord(
            test_id=test.id,
            fullname=rec.fullname.strip().upper(),
            address=rec.address.strip().upper(),
            expected_ssn=_normalize_ssn(rec.expected_ssn),
            sort_order=i,
        ))

    await db.commit()
    await db.refresh(test)

    return TestResponse(
        id=str(test.id),
        name=test.name,
        description=test.description,
        records_count=len(request.records),
        created_at=test.created_at.isoformat(),
        updated_at=test.updated_at.isoformat(),
    )


@router.get("/tests/{test_id}", response_model=TestDetailResponse)
async def get_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get test details with all records."""
    test = await db.get(TestPolygon, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    recs_q = (
        select(TestPolygonRecord)
        .where(TestPolygonRecord.test_id == test_id)
        .order_by(TestPolygonRecord.sort_order)
    )
    recs = (await db.execute(recs_q)).scalars().all()

    return TestDetailResponse(
        id=str(test.id),
        name=test.name,
        description=test.description,
        records=[RecordResponse(
            id=str(r.id),
            fullname=r.fullname,
            address=r.address,
            expected_ssn=r.expected_ssn,
            sort_order=r.sort_order,
        ) for r in recs],
        created_at=test.created_at.isoformat(),
        updated_at=test.updated_at.isoformat(),
    )


@router.put("/tests/{test_id}", response_model=TestResponse)
async def update_test(
    test_id: UUID,
    request: UpdateTestRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Update test name/description and optionally replace records."""
    test = await db.get(TestPolygon, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    if request.name is not None:
        test.name = request.name
    if request.description is not None:
        test.description = request.description

    # If records provided, replace all
    if request.records is not None:
        # Delete old records
        old_recs = (await db.execute(
            select(TestPolygonRecord).where(TestPolygonRecord.test_id == test_id)
        )).scalars().all()
        for r in old_recs:
            await db.delete(r)

        # Add new records
        for i, rec in enumerate(request.records):
            db.add(TestPolygonRecord(
                test_id=test.id,
                fullname=rec.fullname.strip().upper(),
                address=rec.address.strip().upper(),
                expected_ssn=_normalize_ssn(rec.expected_ssn),
                sort_order=i,
            ))

    test.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(test)

    rec_count = (await db.execute(
        select(func.count(TestPolygonRecord.id)).where(TestPolygonRecord.test_id == test_id)
    )).scalar() or 0

    return TestResponse(
        id=str(test.id),
        name=test.name,
        description=test.description,
        records_count=rec_count,
        created_at=test.created_at.isoformat(),
        updated_at=test.updated_at.isoformat(),
    )


@router.delete("/tests/{test_id}")
async def delete_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete a test and all its runs/results."""
    test = await db.get(TestPolygon, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    await db.delete(test)
    await db.commit()
    return {"message": "Test deleted"}


# ── Run Test ─────────────────────────────────────────────────────

@router.post("/tests/{test_id}/run", response_model=RunResponse)
async def run_test(
    test_id: UUID,
    request: RunTestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Start a test run. Processes records in background."""
    test = await db.get(TestPolygon, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    rec_count = (await db.execute(
        select(func.count(TestPolygonRecord.id)).where(TestPolygonRecord.test_id == test_id)
    )).scalar() or 0

    if rec_count == 0:
        raise HTTPException(status_code=400, detail="Test has no records")

    # Create run
    run = TestPolygonRun(
        test_id=test_id,
        flow_config={
            "provider": request.provider,
            "save_debug": request.save_debug,
            "parallelism": request.parallelism,
            "prioritization": request.prioritization,
        },
        status="running",
        total_records=rec_count,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Start background processing
    background_tasks.add_task(
        _execute_test_run,
        run_id=run.id,
        test_id=test_id,
        provider=request.provider,
        save_debug=request.save_debug,
        parallelism=request.parallelism,
        prioritization=request.prioritization,
    )

    return RunResponse(
        id=str(run.id),
        test_id=str(test_id),
        test_name=test.name,
        flow_config=run.flow_config,
        status=run.status,
        total_records=run.total_records,
        processed_count=0,
        matched_count=0,
        not_found_count=0,
        wrong_ssn_count=0,
        error_count=0,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=None,
        created_at=run.created_at.isoformat(),
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get run status and stats."""
    run = await db.get(TestPolygonRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    test = await db.get(TestPolygon, run.test_id)

    return RunResponse(
        id=str(run.id),
        test_id=str(run.test_id),
        test_name=test.name if test else "Deleted test",
        flow_config=run.flow_config,
        status=run.status,
        total_records=run.total_records,
        processed_count=run.processed_count,
        matched_count=run.matched_count,
        not_found_count=run.not_found_count,
        wrong_ssn_count=run.wrong_ssn_count,
        error_count=run.error_count,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        created_at=run.created_at.isoformat(),
    )


@router.get("/runs/{run_id}/results", response_model=ResultsListResponse)
async def get_run_results(
    run_id: UUID,
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get results for a run with optional status filter."""
    run = await db.get(TestPolygonRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Base query with join to records for fullname/address
    q = (
        select(TestPolygonResult, TestPolygonRecord)
        .join(TestPolygonRecord, TestPolygonResult.record_id == TestPolygonRecord.id)
        .where(TestPolygonResult.run_id == run_id)
    )

    if status_filter:
        q = q.where(TestPolygonResult.status == status_filter)

    # Count
    count_q = (
        select(func.count(TestPolygonResult.id))
        .where(TestPolygonResult.run_id == run_id)
    )
    if status_filter:
        count_q = count_q.where(TestPolygonResult.status == status_filter)
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(TestPolygonRecord.sort_order).offset(offset).limit(limit)
    rows = (await db.execute(q)).all()

    results = []
    for res, rec in rows:
        results.append(ResultResponse(
            id=str(res.id),
            record_id=str(res.record_id),
            fullname=rec.fullname,
            address=rec.address,
            expected_ssn=rec.expected_ssn,
            status=res.status,
            found_ssn=res.found_ssn,
            best_method=res.best_method,
            matched_keys_count=res.matched_keys_count,
            total_candidates=res.total_candidates,
            search_time=res.search_time,
            error_message=res.error_message,
            sort_order=rec.sort_order,
        ))

    return ResultsListResponse(results=results, total_count=total)


@router.get("/runs/{run_id}/results/{result_id}/debug")
async def get_result_debug(
    run_id: UUID,
    result_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """Get full debug data for a single result."""
    res = await db.get(TestPolygonResult, result_id)
    if not res or res.run_id != run_id:
        raise HTTPException(status_code=404, detail="Result not found")

    rec = await db.get(TestPolygonRecord, res.record_id)

    return {
        "id": str(res.id),
        "record_id": str(res.record_id),
        "fullname": rec.fullname if rec else "",
        "address": rec.address if rec else "",
        "expected_ssn": rec.expected_ssn if rec else "",
        "status": res.status,
        "found_ssn": res.found_ssn,
        "best_method": res.best_method,
        "matched_keys_count": res.matched_keys_count,
        "total_candidates": res.total_candidates,
        "search_time": res.search_time,
        "error_message": res.error_message,
        "debug_data": res.debug_data,
    }


# ── Background task: execute the test run ────────────────────────

async def _execute_test_run(
    run_id: UUID,
    test_id: UUID,
    provider: str,
    save_debug: bool,
    parallelism: int,
    prioritization: str = "default",
):
    """Process all records in a test run (runs in background)."""
    logger.info(f"Starting test run {run_id} for test {test_id} (parallelism={parallelism})")

    async with async_session_maker() as db:
        try:
            # Load records
            recs = (await db.execute(
                select(TestPolygonRecord)
                .where(TestPolygonRecord.test_id == test_id)
                .order_by(TestPolygonRecord.sort_order)
            )).scalars().all()

            semaphore = asyncio.Semaphore(parallelism)

            async def process_record(record: TestPolygonRecord):
                async with semaphore:
                    return await _process_single_record(record, provider, save_debug, prioritization)

            # Run all records concurrently (bounded by semaphore)
            tasks = [process_record(rec) for rec in recs]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Save results and update counters
            matched = 0
            not_found = 0
            wrong_ssn = 0
            errors = 0

            for rec, result in zip(recs, results):
                if isinstance(result, Exception):
                    logger.error(f"Error processing record {rec.id}: {result}")
                    res_obj = TestPolygonResult(
                        run_id=run_id,
                        record_id=rec.id,
                        status="error",
                        error_message=str(result),
                    )
                    errors += 1
                else:
                    res_obj = TestPolygonResult(
                        run_id=run_id,
                        record_id=rec.id,
                        status=result["status"],
                        found_ssn=result.get("found_ssn"),
                        best_method=result.get("best_method"),
                        matched_keys_count=result.get("matched_keys_count", 0),
                        total_candidates=result.get("total_candidates", 0),
                        debug_data=result.get("debug_data") if save_debug else None,
                        search_time=result.get("search_time"),
                        error_message=result.get("error_message"),
                    )
                    if result["status"] == "match":
                        matched += 1
                    elif result["status"] == "not_found":
                        not_found += 1
                    elif result["status"] == "wrong_ssn":
                        wrong_ssn += 1
                    elif result["status"] == "error":
                        errors += 1

                db.add(res_obj)

            # Update run stats
            run = await db.get(TestPolygonRun, run_id)
            if run:
                run.status = "completed"
                run.processed_count = len(recs)
                run.matched_count = matched
                run.not_found_count = not_found
                run.wrong_ssn_count = wrong_ssn
                run.error_count = errors
                run.finished_at = datetime.utcnow()

            await db.commit()
            logger.info(
                f"Test run {run_id} completed: matched={matched}, not_found={not_found}, "
                f"wrong_ssn={wrong_ssn}, errors={errors}"
            )

        except Exception as e:
            logger.error(f"Fatal error in test run {run_id}: {e}", exc_info=True)
            run = await db.get(TestPolygonRun, run_id)
            if run:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                await db.commit()


async def _process_single_record(
    record: TestPolygonRecord,
    provider: str,
    save_debug: bool,
    prioritization: str = "default",
) -> Dict[str, Any]:
    """Process a single fullz record through the search flow.

    Returns dict with keys: status, found_ssn, best_method, matched_keys_count,
    total_candidates, debug_data, search_time, error_message
    """
    start_time = time.time()

    try:
        # Parse fullname into first/last (handles JR, SR, III, etc.)
        try:
            firstname, middlename, lastname = _parse_fullname(record.fullname)
        except ValueError as ve:
            return {
                "status": "error",
                "error_message": str(ve),
                "search_time": time.time() - start_time,
            }

        # Parse address into components for fallback
        parsed_addr = _parse_address_string(record.address)

        # Import search dependencies
        from database.bloom_key_generator import generate_all_bloom_keys_from_searchbug
        from database.search_key_generator import (
            generate_query_keys_from_searchbug,
            generate_candidate_keys,
            extract_all_searchbug_mn,
            extract_dob_year,
        )
        from database.clickhouse_search_engine import (
            _get_best_match_priority,
            _normalize_address_for_match,
        )
        from database.clickhouse_schema import (
            SSN_BLOOM_PHONE_LOOKUP,
            SSN_MUTANTS_BLOOM_PHONE_LOOKUP,
            SSN_BLOOM_ADDRESS_LOOKUP,
            SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP,
        )
        from database.clickhouse_client import execute_query

        # Step 1: Call SearchBug API
        searchbug_data = None
        try:
            async with async_session_maker() as api_db:
                from api.common.searchbug_client import create_searchbug_client_dynamic
                from api.common.searchbug_cache import SearchBugCacheService

                cache_service = SearchBugCacheService(api_db)
                async with await create_searchbug_client_dynamic(api_db) as searchbug:
                    searchbug_data = await cache_service.search_person_unified_cached(
                        searchbug_client=searchbug,
                        firstname=firstname,
                        lastname=lastname,
                        address=record.address,
                    )
        except Exception as sb_err:
            logger.warning(f"SearchBug call failed for {record.fullname}: {sb_err}")

        # Build search data from SearchBug response or fallback to input data
        searchbug_used = bool(searchbug_data)

        if searchbug_data:
            # Extract from SearchBug response
            names = searchbug_data.get('names', [])
            sb_firstname = firstname
            sb_lastname = lastname
            sb_middlename = middlename
            if names:
                sb_firstname = names[0].get('first_name', firstname)
                sb_lastname = names[0].get('last_name', lastname)
                sb_middlename = names[0].get('middle_name') or middlename

            dob = searchbug_data.get('dob', '')
            addresses = searchbug_data.get('addresses', []) or []
            all_phones_raw = searchbug_data.get('all_phones', []) or []

            all_phones = []
            for phone_obj in all_phones_raw:
                if isinstance(phone_obj, dict):
                    phone_num = phone_obj.get('phone_number', '')
                    if phone_num:
                        all_phones.append(phone_num)
                elif isinstance(phone_obj, str):
                    all_phones.append(phone_obj)

            addresses_with_state = []
            for addr in addresses:
                full_street = addr.get('full_street', '')
                state_val = addr.get('state', '')
                if full_street and state_val:
                    addresses_with_state.append({'address': full_street, 'state': state_val})
        else:
            # Fallback: build search data directly from input
            logger.info(f"SearchBug returned no data for {record.fullname}, using direct DB search")
            names = [{'first_name': firstname, 'last_name': lastname}]
            if middlename:
                names[0]['middle_name'] = middlename
            sb_firstname = firstname
            sb_lastname = lastname
            sb_middlename = middlename
            dob = ''
            all_phones = []
            addresses_with_state = []
            if parsed_addr['street'] and parsed_addr['state']:
                addresses_with_state.append({
                    'address': parsed_addr['street'],
                    'state': parsed_addr['state'],
                })

        # Step 2: Generate bloom keys
        searchbug_search_data = {
            'names': names,
            'firstname': sb_firstname,
            'middlename': sb_middlename,
            'lastname': sb_lastname,
            'dob': dob,
            'phones': all_phones,
            'addresses': addresses_with_state,
        }

        bloom_results = generate_all_bloom_keys_from_searchbug(searchbug_search_data)
        bloom_keys_phone = bloom_results.get('bloom_keys_phone', [])
        bloom_keys_address = bloom_results.get('bloom_keys_address', [])

        all_candidates: List[Dict] = []

        # Check phone bloom keys
        bloom_phone_info = []
        for key in bloom_keys_phone:
            query = f"""
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone = {{key:String}}
            UNION ALL
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone = {{key:String}}
            LIMIT 100
            """
            candidates = execute_query(query, parameters={"key": key})
            bloom_phone_info.append({"key": key, "found": len(candidates) > 0, "count": len(candidates)})
            all_candidates.extend(candidates)

        # Check address bloom keys
        bloom_address_info = []
        for key in bloom_keys_address:
            query = f"""
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address = {{key:String}}
            UNION ALL
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address = {{key:String}}
            LIMIT 100
            """
            candidates = execute_query(query, parameters={"key": key})
            bloom_address_info.append({"key": key, "found": len(candidates) > 0, "count": len(candidates)})
            all_candidates.extend(candidates)

        if not all_candidates:
            debug_data = None
            if save_debug:
                debug_data = {
                    "searchbug_used": searchbug_used,
                    "searchbug_data": {
                        "firstname": sb_firstname,
                        "middlename": sb_middlename,
                        "lastname": sb_lastname,
                        "dob": dob,
                        "phones": all_phones,
                        "addresses": addresses_with_state,
                    },
                    "bloom_keys_phone": bloom_phone_info,
                    "bloom_keys_address": bloom_address_info,
                    "level1_candidates_count": 0,
                    "query_keys": [],
                    "candidates": [],
                    "final_results": [],
                }
            return {
                "status": "not_found",
                "total_candidates": 0,
                "matched_keys_count": 0,
                "debug_data": debug_data,
                "search_time": time.time() - start_time,
            }

        # Step 3: Level 2 matching
        query_keys_dict = generate_query_keys_from_searchbug(searchbug_search_data)

        final_results: List[Dict] = []
        seen_ssns: Set[str] = set()
        matched_query_keys: Set[str] = set()
        candidates_debug = []

        for candidate in all_candidates:
            candidate_keys = generate_candidate_keys(candidate)
            matched_key_values = candidate_keys.keys() & query_keys_dict.keys()
            matched = {k: query_keys_dict[k] for k in matched_key_values}

            matched_keys_list = [f"{method}: {key}" for key, method in matched.items()]
            best_priority = _get_best_match_priority(matched_keys_list) if matched_keys_list else None

            if save_debug:
                candidates_debug.append({
                    "ssn": candidate.get('ssn', ''),
                    "firstname": candidate.get('firstname'),
                    "lastname": candidate.get('lastname'),
                    "middlename": candidate.get('middlename'),
                    "dob": candidate.get('dob'),
                    "address": candidate.get('address'),
                    "phone": candidate.get('phone'),
                    "source_table": candidate.get('source_table'),
                    "matched_keys": matched_keys_list,
                    "matched_keys_count": len(matched_keys_list),
                    "best_priority": best_priority if best_priority != 999 else None,
                })

            if matched:
                ssn_val = candidate.get('ssn', '')
                if ssn_val not in seen_ssns:
                    seen_ssns.add(ssn_val)
                    final_results.append({
                        "ssn": ssn_val,
                        "matched_keys": matched_keys_list,
                        "matched_keys_count": len(matched_keys_list),
                        "best_priority": best_priority if best_priority != 999 else None,
                        "firstname": candidate.get('firstname'),
                        "lastname": candidate.get('lastname'),
                        "middlename": candidate.get('middlename'),
                        "address": candidate.get('address'),
                    })
                else:
                    # Merge keys
                    for existing in final_results:
                        if existing["ssn"] == ssn_val:
                            merged = set(existing["matched_keys"]) | set(matched_keys_list)
                            existing["matched_keys"] = sorted(merged)
                            existing["matched_keys_count"] = len(existing["matched_keys"])
                            existing["best_priority"] = _get_best_match_priority(existing["matched_keys"])
                            break
                matched_query_keys.update(matched)

        # Sort by chosen prioritization strategy
        if prioritization == "quality_first":
            final_results.sort(key=lambda r: (
                r.get("best_priority") or 999,
                -r["matched_keys_count"],
            ))
        else:  # "default" and "quantity_first"
            final_results.sort(key=lambda r: (
                -r["matched_keys_count"],
                r.get("best_priority") or 999,
            ))

        # Compare best result SSN with expected
        expected_ssn_norm = _normalize_ssn(record.expected_ssn)

        if not final_results:
            status_val = "not_found"
            found_ssn = None
            best_method = None
            matched_count = 0
        else:
            best = final_results[0]
            found_ssn_norm = _normalize_ssn(best["ssn"])
            found_ssn = best["ssn"]
            matched_count = best["matched_keys_count"]

            # Determine best method name
            if best["matched_keys"]:
                # Extract method name from "Method: key" format
                best_method = best["matched_keys"][0].split(":")[0].strip()
            else:
                best_method = None

            if found_ssn_norm == expected_ssn_norm:
                status_val = "match"
            else:
                status_val = "wrong_ssn"

        debug_data = None
        if save_debug:
            # Build query keys info
            qk_info = []
            for key_value, method_name in sorted(query_keys_dict.items(), key=lambda x: x[1]):
                qk_info.append({
                    "key": key_value,
                    "method": method_name,
                    "matched": key_value in matched_query_keys,
                })

            debug_data = {
                "searchbug_used": searchbug_used,
                "searchbug_data": {
                    "firstname": sb_firstname,
                    "middlename": sb_middlename,
                    "lastname": sb_lastname,
                    "dob": dob,
                    "phones": all_phones,
                    "addresses": addresses_with_state,
                },
                "bloom_keys_phone": bloom_phone_info,
                "bloom_keys_address": bloom_address_info,
                "level1_candidates_count": len(all_candidates),
                "query_keys": qk_info,
                "candidates": candidates_debug,
                "final_results": final_results,
            }

        return {
            "status": status_val,
            "found_ssn": found_ssn,
            "best_method": best_method,
            "matched_keys_count": matched_count,
            "total_candidates": len(all_candidates),
            "debug_data": debug_data,
            "search_time": time.time() - start_time,
        }

    except Exception as e:
        logger.error(f"Error processing record {record.id}: {e}", exc_info=True)
        return {
            "status": "error",
            "error_message": str(e),
            "search_time": time.time() - start_time,
        }
