from fastapi import APIRouter, HTTPException, Depends
from typing import List
from ...models.Watch_Settings import Material, MovementType, Gender, Color
from pydantic import BaseModel
from ...config.database import get_database
from bson import ObjectId

router = APIRouter(prefix="/api/watch-settings", tags=["Watch Settings API"])

class NameRequest(BaseModel):
    name: str

# --- Materials ---

@router.post("/materials", response_model=Material)
async def create_material(data: NameRequest, db=Depends(get_database)):
    material_doc = {"name": data.name}
    result = await db.watch_materials.insert_one(material_doc)
    created_material = await db.watch_materials.find_one({"_id": result.inserted_id})
    return created_material

@router.get("/materials", response_model=List[Material])
async def get_materials(db=Depends(get_database)):
    materials = await db.watch_materials.find().to_list(100)
    return materials

@router.delete("/materials/{material_id}")
async def delete_material(material_id: str, db=Depends(get_database)):
    if not ObjectId.is_valid(material_id):
        raise HTTPException(status_code=400, detail="Invalid material ID")
    result = await db.watch_materials.delete_one({"_id": ObjectId(material_id)})
    if result.deleted_count == 1:
        return {"status": "success", "message": "Material deleted"}
    raise HTTPException(status_code=404, detail="Material not found")

# --- Movement Types ---

@router.post("/movement-types", response_model=MovementType)
async def create_movement_type(data: NameRequest, db=Depends(get_database)):
    movement_type_doc = {"name": data.name}
    result = await db.watch_movement_types.insert_one(movement_type_doc)
    created_movement_type = await db.watch_movement_types.find_one({"_id": result.inserted_id})
    return created_movement_type

@router.get("/movement-types", response_model=List[MovementType])
async def get_movement_types(db=Depends(get_database)):
    movement_types = await db.watch_movement_types.find().to_list(100)
    return movement_types

@router.delete("/movement-types/{movement_type_id}")
async def delete_movement_type(movement_type_id: str, db=Depends(get_database)):
    if not ObjectId.is_valid(movement_type_id):
        raise HTTPException(status_code=400, detail="Invalid movement type ID")
    result = await db.watch_movement_types.delete_one({"_id": ObjectId(movement_type_id)})
    if result.deleted_count == 1:
        return {"status": "success", "message": "Movement type deleted"}
    raise HTTPException(status_code=404, detail="Movement type not found")

# --- Genders ---

@router.post("/genders", response_model=Gender)
async def create_gender(data: NameRequest, db=Depends(get_database)):
    gender_doc = {"name": data.name}
    result = await db.watch_genders.insert_one(gender_doc)
    created_gender = await db.watch_genders.find_one({"_id": result.inserted_id})
    return created_gender

@router.get("/genders", response_model=List[Gender])
async def get_genders(db=Depends(get_database)):
    genders = await db.watch_genders.find().to_list(100)
    return genders

@router.delete("/genders/{gender_id}")
async def delete_gender(gender_id: str, db=Depends(get_database)):
    if not ObjectId.is_valid(gender_id):
        raise HTTPException(status_code=400, detail="Invalid gender ID")
    result = await db.watch_genders.delete_one({"_id": ObjectId(gender_id)})
    if result.deleted_count == 1:
        return {"status": "success", "message": "Gender deleted"}
    raise HTTPException(status_code=404, detail="Gender not found")

# --- Colors ---

@router.post("/colors", response_model=Color)
async def create_color(data: NameRequest, db=Depends(get_database)):
    color_doc = {"name": data.name}
    result = await db.watch_colors.insert_one(color_doc)
    created_color = await db.watch_colors.find_one({"_id": result.inserted_id})
    return created_color

@router.get("/colors", response_model=List[Color])
async def get_colors(db=Depends(get_database)):
    colors = await db.watch_colors.find().to_list(100)
    return colors

@router.delete("/colors/{color_id}")
async def delete_color(color_id: str, db=Depends(get_database)):
    if not ObjectId.is_valid(color_id):
        raise HTTPException(status_code=400, detail="Invalid color ID")
    result = await db.watch_colors.delete_one({"_id": ObjectId(color_id)})
    if result.deleted_count == 1:
        return {"status": "success", "message": "Color deleted"}
    raise HTTPException(status_code=404, detail="Color not found")
