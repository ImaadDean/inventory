from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, date
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
    payment_frequency: str = "monthly"
    payment_schedule: Optional[str] = None

class WorkerUpdateRequest(BaseModel):
    base_salary: float = 0.0
    hire_date: Optional[str] = None
    is_active: bool = True
    payment_frequency: Optional[str] = None
    payment_schedule: Optional[str] = None

class WorkerStatusUpdateRequest(BaseModel):
    is_active: bool

class SalaryCreateRequest(BaseModel):
    worker_id: str
    amount: float
    work_date: Optional[str] = None
    work_description: Optional[str] = ""
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
    payment_frequency: str = "monthly"
    payment_schedule: Optional[str] = None

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
                "payment_frequency": worker.get("payment_frequency", "monthly"),
                "payment_schedule": worker.get("payment_schedule", ""),
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
                "payment_frequency": worker.get("payment_frequency", "monthly"),
                "payment_schedule": worker.get("payment_schedule", ""),
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

            # For casual workers, base_salary should be 0
            base_salary = 0 if data.payment_frequency == "casual" else data.base_salary

            # Update user to be a worker
            update_data = {
                "is_worker": True,
                "base_salary": base_salary,
                "hire_date": datetime.fromisoformat(data.hire_date) if data.hire_date else now_kampala(),
                "payment_frequency": data.payment_frequency,
                "payment_schedule": data.payment_schedule,
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

            # For casual workers, base_salary should be 0
            base_salary = 0 if data.payment_frequency == "casual" else data.base_salary

            # Create new user
            new_user = {
                "full_name": data.full_name,
                "username": data.username,
                "email": data.email,
                "password": data.password, # In a real app, hash the password
                "role": "worker",
                "is_worker": True,
                "base_salary": base_salary,
                "hire_date": datetime.fromisoformat(data.hire_date) if data.hire_date else now_kampala(),
                "payment_frequency": data.payment_frequency,
                "payment_schedule": data.payment_schedule,
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

        # For casual workers, base_salary should be 0
        base_salary = 0 if data.payment_frequency == "casual" else data.base_salary

        # Create new external worker
        new_worker = {
            "full_name": data.full_name,
            "phone_number": data.phone_number,
            "email": data.email,
            "base_salary": base_salary,
            "hire_date": datetime.fromisoformat(data.hire_date) if data.hire_date else now_kampala(),
            "payment_frequency": data.payment_frequency,
            "payment_schedule": data.payment_schedule,
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
    """Update worker information for both internal and external workers."""
    try:
        db = await get_database()

        # For casual workers, base_salary should be 0
        base_salary = data.base_salary
        if data.payment_frequency == "casual":
            base_salary = 0

        update_data = {
            "base_salary": base_salary,
            "is_active": data.is_active,
            "updated_at": now_kampala()
        }

        if data.hire_date:
            update_data["hire_date"] = datetime.fromisoformat(data.hire_date)

        if data.payment_frequency:
            update_data["payment_frequency"] = data.payment_frequency

        if data.payment_schedule:
            update_data["payment_schedule"] = data.payment_schedule

        # Try to update in 'users' collection first
        result = await db.users.update_one(
            {"_id": ObjectId(worker_id), "is_worker": True},
            {"$set": update_data}
        )

        # If not found in 'users', try 'external_workers'
        if result.matched_count == 0:
            result = await db.external_workers.update_one(
                {"_id": ObjectId(worker_id)},
                {"$set": update_data}
            )

            if result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Worker not found in either user or external worker collections"
                )

        return {"success": True, "message": "Worker updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update worker: {str(e)}"
        )

@router.patch("/workers/{worker_id}/status", response_model=dict)
async def update_worker_status(
    worker_id: str,
    data: WorkerStatusUpdateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update worker status (activate/deactivate)"""
    try:
        db = await get_database()

        update_data = {
            "is_active": data.is_active,
            "updated_at": now_kampala()
        }

        # Try to update in 'users' collection first (internal workers)
        result = await db.users.update_one(
            {"_id": ObjectId(worker_id), "is_worker": True},
            {"$set": update_data}
        )

        worker_name = "Unknown Worker"
        worker_type = "internal"

        # If found in users collection, get the worker name
        if result.matched_count > 0:
            worker = await db.users.find_one({"_id": ObjectId(worker_id)})
            if worker:
                worker_name = worker.get("full_name", worker.get("username", "Unknown Worker"))
        else:
            # If not found in 'users', try 'external_workers'
            result = await db.external_workers.update_one(
                {"_id": ObjectId(worker_id)},
                {"$set": update_data}
            )

            if result.matched_count > 0:
                worker_type = "external"
                worker = await db.external_workers.find_one({"_id": ObjectId(worker_id)})
                if worker:
                    worker_name = worker.get("full_name", "Unknown Worker")
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Worker not found in either user or external worker collections"
                )

        # Create appropriate success message
        status_text = "activated" if data.is_active else "deactivated"
        message = f"Worker '{worker_name}' has been {status_text} successfully"

        return {
            "success": True,
            "message": message,
            "worker_id": worker_id,
            "worker_name": worker_name,
            "worker_type": worker_type,
            "new_status": data.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update worker status: {str(e)}"
        )

@router.post("/salaries", response_model=dict)
async def create_salary(
    data: SalaryCreateRequest,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Create a salary record for a worker"""
    try:
        db = await get_database()

        # Validate worker exists and is active (check both internal and external workers)
        print(f"Looking for worker with ID: {data.worker_id}")

        worker = await db.users.find_one({"_id": ObjectId(data.worker_id), "is_worker": True})
        is_external_worker = False

        if not worker:
            # Check external workers
            worker = await db.external_workers.find_one({"_id": ObjectId(data.worker_id)})
            if not worker:
                print(f"Worker not found in either users or external_workers collections")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Worker not found"
                )
            is_external_worker = True
            print(f"Found external worker: {worker.get('full_name')}")
        else:
            print(f"Found internal worker: {worker.get('full_name', worker.get('username'))}")

        if not worker.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot process salary for inactive worker"
            )

        # External worker status already determined above

        # For external workers, force bonus and reduction amounts to 0
        bonus_amount = 0 if is_external_worker else data.bonus_amount
        reduction_amount = 0 if is_external_worker else data.reduction_amount

        # Calculate net amount
        net_amount = data.amount + bonus_amount - reduction_amount

        # Parse work date or use current date
        try:
            work_date = datetime.fromisoformat(data.work_date) if data.work_date else now_kampala()
            print(f"Work date: {work_date}")
        except Exception as e:
            print(f"Error parsing work date '{data.work_date}': {e}")
            work_date = now_kampala()

        print(f"Creating salary with net amount: {net_amount}")
        print(f"Worker type: {'External' if is_external_worker else 'Internal'}")

        salary_data = {
            "worker_id": ObjectId(data.worker_id),
            "amount": float(data.amount),
            "work_date": work_date,
            "work_description": data.work_description or "",
            "bonus_amount": float(bonus_amount),
            "reduction_amount": float(reduction_amount),
            "net_amount": float(net_amount),
            "status": data.status or "pending",
            "payment_method": data.payment_method or "cash",
            "notes": data.notes or "",
            "created_by": ObjectId(current_user.id),
            "created_at": now_kampala(),
            "updated_at": now_kampala()
        }

        print(f"Inserting salary data: {salary_data}")
        result = await db.salaries.insert_one(salary_data)
        print(f"Salary created with ID: {result.inserted_id}")
        salary_id = str(result.inserted_id)

        # Create expense record using proper expense structure
        expense_id = None
        try:
            worker_name = worker.get('full_name', worker.get('username', 'Unknown Worker'))
            work_desc = data.work_description or "Salary payment"

            # Determine expense category based on worker type
            expense_category = "External Labor" if is_external_worker else "Staff Salaries"

            # Create expense description
            expense_description = f"Salary payment - {worker_name}"
            if data.work_description and data.work_description != 'Regular salary payment':
                expense_description += f" ({data.work_description})"

            # Convert work_date to proper date format for expense
            if isinstance(work_date, datetime):
                expense_date = work_date.date()
            elif isinstance(work_date, str):
                # Parse string date
                expense_date = datetime.fromisoformat(work_date.split('T')[0]).date()
            elif isinstance(work_date, date):
                expense_date = work_date
            else:
                expense_date = datetime.now().date()

            # Ensure amounts are float
            amount_float = float(net_amount)
            base_amount_float = float(data.amount)
            bonus_float = float(bonus_amount)
            reduction_float = float(reduction_amount)

            # Determine payment status based on salary status
            payment_status = "paid" if data.status == "paid" else "not_paid"
            amount_paid = amount_float if data.status == "paid" else 0

            # Create expense document following the expense API structure
            expense_doc = {
                "description": expense_description[:500],  # Limit description length
                "category": expense_category,
                "amount": amount_float,
                "amount_paid": amount_paid,  # Amount paid depends on salary status
                "expense_date": expense_date.isoformat() if hasattr(expense_date, 'isoformat') else str(expense_date),
                "payment_method": (data.payment_method or "cash")[:50],  # Limit length
                "vendor": worker_name[:200] if worker_name else "Unknown Worker",  # Limit length
                "notes": (f"Salary payment for {worker_name}. Base: UGX {base_amount_float:,.0f}" +
                        (f", Bonus: UGX {bonus_float:,.0f}" if bonus_float > 0 else "") +
                        (f", Reduction: UGX {reduction_float:,.0f}" if reduction_float > 0 else "") +
                        (f". {data.notes}" if data.notes else "") +
                        f". Salary ID: {salary_id}")[:1000],  # Limit notes length
                "status": payment_status,
                "created_at": kampala_to_utc(now_kampala()),
                "updated_at": kampala_to_utc(now_kampala()),
                "created_by": current_user.username  # Use username like expense API
            }

            print(f"Creating expense with data: {expense_doc}")
            expense_result = await db.expenses.insert_one(expense_doc)
            expense_id = str(expense_result.inserted_id)
            print(f"Successfully created expense record {expense_id} for salary {salary_id}")

            # If salary is created as paid, also create an installment record
            if data.status == "paid":
                payment_doc = {
                    "expense_id": expense_result.inserted_id,
                    "amount": amount_float,
                    "payment_date": kampala_to_utc(now_kampala()),
                    "payment_method": (data.payment_method or "cash")[:50],
                    "notes": f"Payment made from HR salary processing for {worker_name}",
                    "created_by": current_user.username
                }
                await db.installments.insert_one(payment_doc)
                print(f"Created installment record for initial paid salary {salary_id}")

        except Exception as e:
            # Log the error but don't fail the salary creation
            print(f"Warning: Failed to create expense record for salary {salary_id}: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            print(f"Expense data that failed: {expense_doc if 'expense_doc' in locals() else 'expense_doc not created'}")
            expense_id = None

        work_desc = data.work_description or "Work completed"
        return {
            "success": True,
            "message": f"Salary processed for {worker.get('full_name', 'worker')} - {work_desc}, Net: UGX {net_amount:,.0f}",
            "salary_id": salary_id,
            "expense_id": expense_id,
            "net_amount": net_amount
        }
    except Exception as e:
        print(f"Error creating salary: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create salary record: {str(e)}"
        )

@router.patch("/salaries/{salary_id}/status", response_model=dict)
async def update_salary_status(
    salary_id: str,
    status_data: dict,
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Update salary status and sync with expense record"""
    try:
        db = await get_database()

        new_status = status_data.get("status")
        if not new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status is required"
            )

        # Update salary record
        salary_result = await db.salaries.update_one(
            {"_id": ObjectId(salary_id)},
            {
                "$set": {
                    "status": new_status,
                    "updated_at": now_kampala()
                }
            }
        )

        if salary_result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Salary record not found"
            )

        # Find and update corresponding expense record
        try:
            # Get the salary record to find the net amount
            salary = await db.salaries.find_one({"_id": ObjectId(salary_id)})
            if salary:
                expense_status_map = {
                    "pending": "not_paid",
                    "approved": "not_paid",
                    "paid": "paid",
                    "partially_paid": "partially_paid",
                    "cancelled": "not_paid"
                }

                expense_status = expense_status_map.get(new_status, "not_paid")

                # Calculate amount_paid based on status
                amount_paid = salary.get("net_amount", 0) if new_status == "paid" else 0

                # Find the expense record
                expense = await db.expenses.find_one({"notes": {"$regex": f"Salary ID: {salary_id}"}})

                if expense:
                    expense_id = expense["_id"]

                    # If marking as paid, create an installment record
                    if new_status == "paid" and expense.get("status") != "paid":
                        # Get worker name for better payment notes
                        worker_name = "Unknown Worker"
                        if salary.get("worker_id"):
                            worker_doc = await db.users.find_one({"_id": salary["worker_id"]})
                            if not worker_doc:
                                worker_doc = await db.external_workers.find_one({"_id": salary["worker_id"]})
                            if worker_doc:
                                worker_name = worker_doc.get("full_name", worker_doc.get("username", "Unknown Worker"))

                        payment_doc = {
                            "expense_id": expense_id,
                            "amount": amount_paid,
                            "payment_date": kampala_to_utc(now_kampala()),
                            "payment_method": salary.get("payment_method", "cash"),
                            "notes": f"Payment made from HR salary processing for {worker_name}",
                            "created_by": current_user.username
                        }
                        await db.installments.insert_one(payment_doc)
                        print(f"Created installment record for salary payment {salary_id}")

                    # Update expense record
                    expense_update_result = await db.expenses.update_one(
                        {"_id": expense_id},
                        {
                            "$set": {
                                "status": expense_status,
                                "amount_paid": amount_paid,
                                "updated_at": kampala_to_utc(now_kampala())
                            }
                        }
                    )

                    if expense_update_result.modified_count > 0:
                        print(f"Updated expense record for salary {salary_id} to status {expense_status}")
                    else:
                        print(f"Failed to update expense record for salary {salary_id}")
                else:
                    print(f"No expense record found for salary {salary_id}")
            else:
                print(f"Salary record {salary_id} not found for expense update")

        except Exception as e:
            print(f"Warning: Failed to update expense record for salary {salary_id}: {str(e)}")

        return {
            "success": True,
            "message": f"Salary status updated to {new_status}",
            "salary_id": salary_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update salary status: {str(e)}"
        )

@router.get("/salaries", response_model=dict)
async def get_salaries(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    worker_id: Optional[str] = Query(None),
    salary_status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get salary records with pagination and filtering"""
    try:
        print(f"Getting salaries - page: {page}, size: {size}, worker_id: {worker_id}, salary_status: {salary_status}")
        db = await get_database()

        # Build filter query
        filter_query = {}

        if worker_id:
            filter_query["worker_id"] = ObjectId(worker_id)

        if salary_status:
            filter_query["status"] = salary_status

        # Get total count
        print(f"Filter query: {filter_query}")
        total = await db.salaries.count_documents(filter_query)
        print(f"Total salaries found: {total}")

        # Get salaries with pagination and worker details
        skip = (page - 1) * size
        pipeline = [
            {"$match": filter_query},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "worker_id",
                    "foreignField": "_id",
                    "as": "internal_worker"
                }
            },
            {
                "$lookup": {
                    "from": "external_workers",
                    "localField": "worker_id",
                    "foreignField": "_id",
                    "as": "external_worker"
                }
            },
            {
                "$addFields": {
                    "worker": {
                        "$cond": {
                            "if": {"$gt": [{"$size": "$internal_worker"}, 0]},
                            "then": {"$arrayElemAt": ["$internal_worker", 0]},
                            "else": {"$arrayElemAt": ["$external_worker", 0]}
                        }
                    }
                }
            },
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": size}
        ]

        print(f"Aggregation pipeline: {pipeline}")
        salaries_cursor = db.salaries.aggregate(pipeline)
        salaries_data = await salaries_cursor.to_list(length=size)
        print(f"Retrieved {len(salaries_data)} salary records")

        # Format salaries data
        salaries = []
        print(f"Processing {len(salaries_data)} salary records")
        for i, salary in enumerate(salaries_data):
            try:
                print(f"Processing salary {i+1}: {salary.get('_id')}")
                worker = salary.get("worker", {})
                print(f"Worker data: {worker}")

                # Determine if worker is external by checking if they have a username
                # External workers don't have usernames, internal workers do
                is_external_worker = not bool(worker.get("username"))
                print(f"Is external worker: {is_external_worker}")

                salary_data = {
                    "id": str(salary["_id"]),
                    "worker_id": str(salary["worker_id"]),
                    "worker_name": worker.get("full_name", worker.get("username", "")),
                    "amount": salary.get("amount", 0),
                    "work_date": salary.get("work_date").isoformat() if salary.get("work_date") else None,
                    "work_description": salary.get("work_description", ""),
                    "bonus_amount": salary.get("bonus_amount", 0),
                    "reduction_amount": salary.get("reduction_amount", 0),
                    "net_amount": salary.get("net_amount", 0),
                    "status": salary.get("status", "pending"),
                    "payment_method": salary.get("payment_method", ""),
                    "notes": salary.get("notes", ""),
                    "is_external_worker": is_external_worker,
                    "created_at": salary.get("created_at").isoformat() if salary.get("created_at") else None
                }
                print(f"Created salary data: {salary_data}")
                salaries.append(salary_data)

            except Exception as e:
                print(f"Error processing salary {i+1}: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                continue

        result = {
            "salaries": salaries,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size,
            "has_next": page * size < total,
            "has_prev": page > 1
        }
        print(f"Returning result with {len(salaries)} salaries")
        return result

    except Exception as e:
        print(f"Error in get_salaries: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch salaries: {str(e)}"
        )

@router.get("/bonuses", response_model=dict)
async def get_bonuses(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    worker_id: Optional[str] = Query(None),
    bonus_status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get bonus records with pagination and filtering"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}
        if worker_id:
            filter_query["worker_id"] = ObjectId(worker_id)
        if bonus_status:
            filter_query["status"] = bonus_status

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
    reduction_status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_hybrid_dependency())
):
    """Get reduction records with pagination and filtering"""
    try:
        db = await get_database()

        # Build filter query
        filter_query = {}
        if worker_id:
            filter_query["worker_id"] = ObjectId(worker_id)
        if reduction_status:
            filter_query["status"] = reduction_status

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
