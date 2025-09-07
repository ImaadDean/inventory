from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from bson import ObjectId
from ...config.database import get_database
from ...models.user import User
from ...utils.auth import get_current_user_hybrid_dependency
from ...utils.timezone import now_kampala, kampala_to_utc

# Create FastAPI router for HR API
router = APIRouter(tags=["HR Management API"])

# Pydantic models for request bodies
class WorkerCreateRequest(BaseModel):
    user_id: Optional[str] = None
    full_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    base_salary: float = 0.0
    hire_date: Optional[str] = None

class WorkerUpdateRequest(BaseModel):
    base_salary: float = 0.0
    hire_date: Optional[str] = None
    is_active: bool = True

class SalaryCreateRequest(BaseModel):
    worker_id: str
    amount: float
    salary_type: str = "monthly"
    pay_period: Optional[str] = ""
    bonus_amount: float = 0.0
    reduction_amount: float = 0.0
    status: str = "pending"
    payment_method: Optional[str] = ""
    notes: Optional[str] = ""

class BonusCreateRequest(BaseModel):
    worker_id: str
    amount: float
    bonus_type: str = "performance"
    reason: Optional[str] = ""
    status: str = "pending"
    notes: Optional[str] = ""

class ReductionCreateRequest(BaseModel):
    worker_id: str
    amount: float
    reduction_type: str = "deduction"
    reason: Optional[str] = ""
    status: str = "pending"
    notes: Optional[str] = ""

class ExternalWorkerCreateRequest(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[str] = None
    base_salary: float = 0.0
    hire_date: Optional[str] = None

@router.get("/workers", response_model=dict)
async def get_workers(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get all workers with pagination and filtering"""
    try:
        db = await get_database()
        
        # Get user-based workers
        user_filter_query = {"is_worker": True}
        if search:
            user_filter_query["$or"] = [
                {"username": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}}
            ]
        if is_active is not None:
            user_filter_query["is_active"] = is_active
        
        user_workers_cursor = db.users.find(user_filter_query)
        user_workers_data = await user_workers_cursor.to_list(length=None)

        # Get external workers
        external_filter_query = {}
        if search:
            external_filter_query["$or"] = [
                {"full_name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"phone_number": {"$regex": search, "$options": "i"}}
            ]
        if is_active is not None:
            external_filter_query["is_active"] = is_active

        external_workers_cursor = db.external_workers.find(external_filter_query)
        external_workers_data = await external_workers_cursor.to_list(length=None)

        # Combine and format workers data
        all_workers = []
        for worker in user_workers_data:
            all_workers.append({
                "id": str(worker["_id"]),
                "username": worker.get("username", ""),
                "email": worker.get("email", ""),
                "full_name": worker.get("full_name", ""),
                "phone": worker.get("phone", ""),
                "position": worker.get("position", ""),
                "department": worker.get("department", ""),
                "base_salary": worker.get("base_salary", 0),
                "hire_date": worker.get("hire_date").isoformat() if worker.get("hire_date") else None,
                "is_active": worker.get("is_active", True),
                "created_at": worker.get("created_at").isoformat() if worker.get("created_at") else None,
                "is_external": False
            })
        
        for worker in external_workers_data:
            all_workers.append({
                "id": str(worker["_id"]),
                "username": "",
                "email": worker.get("email", ""),
                "full_name": worker.get("full_name", ""),
                "phone": worker.get("phone_number", ""),
                "position": "",
                "department": "",
                "base_salary": worker.get("base_salary", 0),
                "hire_date": worker.get("hire_date").isoformat() if worker.get("hire_date") else None,
                "is_active": worker.get("is_active", True),
                "created_at": worker.get("created_at").isoformat() if worker.get("created_at") else None,
                "is_external": True
            })

        # Sort all workers by creation date
        all_workers.sort(key=lambda x: x['created_at'], reverse=True)

        # Paginate the combined list
        total = len(all_workers)
        skip = (page - 1) * size
        paginated_workers = all_workers[skip:skip + size]
        
        return {
            "workers": paginated_workers,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "has_next": page * size < total,
            "has_prev": page > 1
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch workers: {str(e)}"
        )

@router.post("/workers", response_model=dict)
async def create_worker(
    data: WorkerCreateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Convert a user to a worker or create a new worker"""
    try:
        db = await get_database()

        if data.user_id:
            # Existing user logic
            user = await db.users.find_one({"_id": ObjectId(data.user_id)})
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            if user.get("is_worker", False):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User is already a worker"
                )

            if user.get("role") == "admin":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Admin users cannot be converted to workers"
                )

            # Update user to be a worker
            update_data = {
                "is_worker": True,
                "base_salary": data.base_salary,
                "hire_date": datetime.fromisoformat(data.hire_date) if data.hire_date else now_kampala(),
                "updated_at": now_kampala()
            }

            result = await db.users.update_one(
                {"_id": ObjectId(data.user_id)},
                {"$set": update_data}
            )

            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Failed to update user"
                )
            
            return {
                "success": True,
                "message": f"Worker '{user.get('full_name', user.get('username', 'Unknown'))}' created successfully",
                "worker_id": str(user["_id"])
            }
        else:
            # New worker logic
            if not data.full_name or not data.username or not data.password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Full name, username, and password are required for a new worker"
                )

            # Check if username or email already exists
            if await db.users.find_one({"username": data.username}):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists"
                )
            
            if data.email and await db.users.find_one({"email": data.email}):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists"
                )

            # Create new user
            new_user = {
                "full_name": data.full_name,
                "username": data.username,
                "email": data.email,
                "password": data.password, # In a real app, hash the password
                "role": "worker",
                "is_worker": True,
                "base_salary": data.base_salary,
                "hire_date": datetime.fromisoformat(data.hire_date) if data.hire_date else now_kampala(),
                "created_at": now_kampala(),
                "updated_at": now_kampala(),
                "is_active": True
            }
            result = await db.users.insert_one(new_user)

            return {
                "success": True,
                "message": f"New worker '{data.full_name}' created successfully",
                "worker_id": str(result.inserted_id)
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create worker: {str(e)}"
        )

@router.post("/external-workers", response_model=dict)
async def create_external_worker(
    data: ExternalWorkerCreateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create an external worker"""
    try:
        db = await get_database()

        # Create new external worker
        new_worker = {
            "full_name": data.full_name,
            "phone_number": data.phone_number,
            "email": data.email,
            "base_salary": data.base_salary,
            "hire_date": datetime.fromisoformat(data.hire_date) if data.hire_date else now_kampala(),
            "created_at": now_kampala(),
            "updated_at": now_kampala(),
            "is_active": True,
            "created_by": ObjectId(current_user.id)
        }
        result = await db.external_workers.insert_one(new_worker)

        return {
            "success": True,
            "message": f"New external worker '{data.full_name}' created successfully",
            "worker_id": str(result.inserted_id)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create external worker: {str(e)}"
        )

@router.put("/workers/{worker_id}", response_model=dict)
async def update_worker(
    worker_id: str,
    data: WorkerUpdateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update worker information"""
    try:
        db = await get_database()

        update_data = {
            "base_salary": data.base_salary,
            "is_active": data.is_active,
            "updated_at": now_kampala()
        }

        if data.hire_date:
            update_data["hire_date"] = datetime.fromisoformat(data.hire_date)
        
        result = await db.users.update_one(
            {"_id": ObjectId(worker_id), "is_worker": True},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found"
            )
        
        return {"success": True, "message": "Worker updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update worker: {str(e)}"
        )

@router.post("/salaries", response_model=dict)
async def create_salary(
    data: SalaryCreateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a salary record for a worker"""
    try:
        db = await get_database()

        # Validate worker exists and is active
        worker = await db.users.find_one({"_id": ObjectId(data.worker_id), "is_worker": True})
        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found or user is not a worker"
            )

        if not worker.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot process salary for inactive worker"
            )

        # Check for duplicate salary record for the same pay period
        existing_salary = await db.salaries.find_one({
            "worker_id": ObjectId(data.worker_id),
            "pay_period": data.pay_period
        })

        if existing_salary:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Salary record already exists for {worker.get('full_name', 'worker')} for period {data.pay_period}"
            )

        # Calculate net amount
        net_amount = data.amount + data.bonus_amount - data.reduction_amount

        salary_data = {
            "worker_id": ObjectId(data.worker_id),
            "amount": data.amount,
            "salary_type": data.salary_type,
            "pay_period": data.pay_period,
            "bonus_amount": data.bonus_amount,
            "reduction_amount": data.reduction_amount,
            "net_amount": net_amount,
            "status": data.status,
            "payment_method": data.payment_method,
            "notes": data.notes,
            "created_by": ObjectId(current_user.id),
            "created_at": now_kampala(),
            "updated_at": now_kampala()
        }

        result = await db.salaries.insert_one(salary_data)

        return {
            "success": True,
            "message": f"Salary processed for {worker.get('full_name', 'worker')} - Period: {data.pay_period}, Net: UGX {net_amount:,.0f}",
            "salary_id": str(result.inserted_id),
            "net_amount": net_amount
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create salary record: {str(e)}"
        )

@router.get("/salaries", response_model=dict)
async def get_salaries(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    worker_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get salary records with pagination and filtering"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}

        if worker_id:
            filter_query["worker_id"] = ObjectId(worker_id)

        if status:
            filter_query["status"] = status

        # Get total count
        total = await db.salaries.count_documents(filter_query)

        # Get salaries with pagination and worker details
        skip = (page - 1) * size
        pipeline = [
            {"$match": filter_query},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "worker_id",
                    "foreignField": "_id",
                    "as": "worker"
                }
            },
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": size}
        ]

        salaries_cursor = db.salaries.aggregate(pipeline)
        salaries_data = await salaries_cursor.to_list(length=size)

        # Format salaries data
        salaries = []
        for salary in salaries_data:
            worker = salary.get("worker", [{}])[0]
            salary_data = {
                "id": str(salary["_id"]),
                "worker_id": str(salary["worker_id"]),
                "worker_name": worker.get("full_name", worker.get("username", "")),
                "amount": salary.get("amount", 0),
                "salary_type": salary.get("salary_type", "monthly"),
                "pay_period": salary.get("pay_period", ""),
                "bonus_amount": salary.get("bonus_amount", 0),
                "reduction_amount": salary.get("reduction_amount", 0),
                "net_amount": salary.get("net_amount", 0),
                "status": salary.get("status", "pending"),
                "payment_method": salary.get("payment_method", ""),
                "notes": salary.get("notes", ""),
                "created_at": salary.get("created_at").isoformat() if salary.get("created_at") else None
            }
            salaries.append(salary_data)

        return {
            "salaries": salaries,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "has_next": page * size < total,
            "has_prev": page > 1
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch salaries: {str(e)}"
        )

@router.get("/bonuses", response_model=dict)
async def get_bonuses(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    worker_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get bonus records with pagination and filtering"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}
        if worker_id:
            filter_query["worker_id"] = ObjectId(worker_id)
        if status:
            filter_query["status"] = status

        # Get total count
        total = await db.bonuses.count_documents(filter_query)

        # Calculate pagination
        skip = (page - 1) * size
        has_next = skip + size < total
        has_prev = page > 1
        total_pages = (total + size - 1) // size

        # Get bonuses with pagination
        bonuses_cursor = db.bonuses.find(filter_query).skip(skip).limit(size).sort("created_at", -1)

        bonuses = []
        async for bonus in bonuses_cursor:
            # Get worker info
            worker = await db.users.find_one({"_id": bonus["worker_id"]})
            worker_name = worker.get("full_name", "Unknown") if worker else "Unknown"

            bonuses.append({
                "id": str(bonus["_id"]),
                "worker_id": str(bonus["worker_id"]),
                "worker_name": worker_name,
                "amount": bonus.get("amount", 0),
                "bonus_type": bonus.get("bonus_type", ""),
                "reason": bonus.get("reason", ""),
                "status": bonus.get("status", "pending"),
                "created_at": bonus.get("created_at").isoformat() if bonus.get("created_at") else None,
                "notes": bonus.get("notes", "")
            })

        return {
            "bonuses": bonuses,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bonuses: {str(e)}"
        )

@router.post("/bonuses", response_model=dict)
async def create_bonus(
    data: BonusCreateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a bonus record for a worker"""
    try:
        db = await get_database()

        # Validate worker exists and is active
        worker = await db.users.find_one({"_id": ObjectId(data.worker_id), "is_worker": True})
        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found or user is not a worker"
            )

        if not worker.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add bonus for inactive worker"
            )

        bonus_data = {
            "worker_id": ObjectId(data.worker_id),
            "amount": data.amount,
            "bonus_type": data.bonus_type,
            "reason": data.reason,
            "status": data.status,
            "notes": data.notes,
            "created_by": ObjectId(current_user.id),
            "created_at": now_kampala(),
            "updated_at": now_kampala()
        }

        result = await db.bonuses.insert_one(bonus_data)

        return {
            "success": True,
            "message": f"Bonus of UGX {data.amount:,.0f} added for {worker.get('full_name', 'worker')}",
            "bonus_id": str(result.inserted_id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create bonus record: {str(e)}"
        )

@router.get("/reductions", response_model=dict)
async def get_reductions(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    worker_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get reduction records with pagination and filtering"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}
        if worker_id:
            filter_query["worker_id"] = ObjectId(worker_id)
        if status:
            filter_query["status"] = status

        # Get total count
        total = await db.reductions.count_documents(filter_query)

        # Calculate pagination
        skip = (page - 1) * size
        has_next = skip + size < total
        has_prev = page > 1
        total_pages = (total + size - 1) // size

        # Get reductions with pagination
        reductions_cursor = db.reductions.find(filter_query).skip(skip).limit(size).sort("created_at", -1)

        reductions = []
        async for reduction in reductions_cursor:
            # Get worker info
            worker = await db.users.find_one({"_id": reduction["worker_id"]})
            worker_name = worker.get("full_name", "Unknown") if worker else "Unknown"

            reductions.append({
                "id": str(reduction["_id"]),
                "worker_id": str(reduction["worker_id"]),
                "worker_name": worker_name,
                "amount": reduction.get("amount", 0),
                "reduction_type": reduction.get("reduction_type", ""),
                "reason": reduction.get("reason", ""),
                "status": reduction.get("status", "pending"),
                "created_at": reduction.get("created_at").isoformat() if reduction.get("created_at") else None,
                "notes": reduction.get("notes", "")
            })

        return {
            "reductions": reductions,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch reductions: {str(e)}"
        )

@router.post("/reductions", response_model=dict)
async def create_reduction(
    data: ReductionCreateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a reduction record for a worker"""
    try:
        db = await get_database()

        # Validate worker exists and is active
        worker = await db.users.find_one({"_id": ObjectId(data.worker_id), "is_worker": True})
        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found or user is not a worker"
            )

        if not worker.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot add reduction for inactive worker"
            )

        reduction_data = {
            "worker_id": ObjectId(data.worker_id),
            "amount": data.amount,
            "reduction_type": data.reduction_type,
            "reason": data.reason,
            "status": data.status,
            "notes": data.notes,
            "created_by": ObjectId(current_user.id),
            "created_at": now_kampala(),
            "updated_at": now_kampala()
        }

        result = await db.reductions.insert_one(reduction_data)

        return {
            "success": True,
            "message": f"Reduction of UGX {data.amount:,.0f} added for {worker.get('full_name', 'worker')}",
            "reduction_id": str(result.inserted_id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create reduction record: {str(e)}"
        )

@router.get("/stats", response_model=dict)
async def get_hr_stats(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get HR statistics for dashboard"""
    try:
        db = await get_database()

        # Get total workers
        total_workers = await db.users.count_documents({"is_worker": True})

        # Get monthly payroll (sum of base salaries for active workers)
        pipeline = [
            {"$match": {"is_worker": True, "is_active": True}},
            {"$group": {"_id": None, "total": {"$sum": "$base_salary"}}}
        ]
        payroll_result = await db.users.aggregate(pipeline).to_list(1)
        monthly_payroll = payroll_result[0]["total"] if payroll_result else 0

        # Get pending bonuses
        pending_bonuses = await db.bonuses.count_documents({"status": "pending"})

        # Get pending reductions
        pending_reductions = await db.reductions.count_documents({"status": "pending"})

        return {
            "total_workers": total_workers,
            "monthly_payroll": monthly_payroll,
            "pending_bonuses": pending_bonuses,
            "pending_reductions": pending_reductions
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get HR stats: {str(e)}"
        )

@router.get("/users", response_model=List[dict])
async def get_users_for_workers(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get all users that can be converted to workers (excluding admins)"""
    try:
        db = await get_database()

        # Get all users that are not already workers and are not admins
        # Also handle cases where is_worker field might not exist (treat as False)
        users_cursor = db.users.find(
            {
                "$and": [
                    {
                        "$or": [
                            {"is_worker": {"$exists": False}},
                            {"is_worker": False},
                            {"is_worker": {"$ne": True}}
                        ]
                    },
                    {"role": {"$ne": "admin"}}
                ]
            },
            {"_id": 1, "username": 1, "full_name": 1, "email": 1, "role": 1, "is_worker": 1}
        )

        users = []
        async for user in users_cursor:
            users.append({
                "id": str(user["_id"]),
                "username": user.get("username", ""),
                "full_name": user.get("full_name", ""),
                "email": user.get("email", ""),
                "role": user.get("role", ""),
                "is_worker": user.get("is_worker", False)
            })

        # Debug: Log the query results
        print(f"Found {len(users)} users available to convert to workers")
        for user in users:
            print(f"User: {user['username']} ({user['full_name']}) - Role: {user['role']}, is_worker: {user['is_worker']}")

        return users
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get users: {str(e)}"
        )

# Temporary debug endpoint to see all users
@router.get("/debug/all-users", response_model=List[dict])
async def get_all_users_debug(
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Debug endpoint to see all users in the system"""
    try:
        db = await get_database()

        # Get ALL users for debugging
        users_cursor = db.users.find(
            {},
            {"_id": 1, "username": 1, "full_name": 1, "email": 1, "role": 1, "is_worker": 1}
        )

        users = []
        async for user in users_cursor:
            users.append({
                "id": str(user["_id"]),
                "username": user.get("username", ""),
                "full_name": user.get("full_name", ""),
                "email": user.get("email", ""),
                "role": user.get("role", ""),
                "is_worker": user.get("is_worker", False)
            })

        print(f"DEBUG: Total users in system: {len(users)}")
        for user in users:
            print(f"DEBUG: {user['username']} - Role: {user['role']}, is_worker: {user['is_worker']}")

        return users
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get all users: {str(e)}"
        )
