from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError


from database.session import create_db_and_tables, get_session
from models.product import (
   Product,
    ProductCreate,
    ProductUpdate,
    Supplier,
    SupplierCreate,
    BulkPriceUpdate,
    StockAdjustment,
)

app = FastAPI(
    title="Product Catalog API",
    version="1.0.0"
)


def error_response(
    request: Request,
    status_code: int,
    message: str,
    errors: list | None = None,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "status_code": status_code,
            "message": message,
            "errors": errors or [],
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url.path),
        },
    )

@app.on_event("startup")
def on_startup():
    create_db_and_tables()




@app.post("/products", response_model=Product, status_code=201)
def create_product(
    product: ProductCreate,
    session: Session = Depends(get_session)
):
   

    db_product = Product(**product.model_dump())

    session.add(db_product)
    session.commit()
    session.refresh(db_product)

    return db_product


@app.get("/products", response_model=List[Product])
def list_products(
    skip: int = 0,
    limit: int = 10,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    session: Session = Depends(get_session),
):
    query = select(Product)

    if category:
        query = query.where(Product.category == category)

    if min_price is not None:
        query = query.where(Product.price >= min_price)

    if max_price is not None:
        query = query.where(Product.price <= max_price)

    if in_stock is not None:
        if in_stock:
            query = query.where(Product.stock > 0)
        else:
            query = query.where(Product.stock == 0)

    return session.exec(
        query.offset(skip).limit(limit)
    ).all()


@app.get("/products/{product_id}", response_model=Product)
def get_product(
    product_id: int,
    session: Session = Depends(get_session)
):
    product = session.get(Product, product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return product


@app.patch("/products/{product_id}", response_model=Product)
def update_product(
    product_id: int,
    product_update: ProductUpdate,
    session: Session = Depends(get_session)
):
    product = session.get(Product, product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    update_data = product_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(product, key, value)

    product.updated_at = datetime.utcnow()

    session.add(product)
    session.commit()
    session.refresh(product)

    return product
    
@app.patch("/products/bulk-price-update")
def bulk_price_update(
    update: BulkPriceUpdate,
    session: Session = Depends(get_session)
):
    products = session.exec(
        select(Product).where(Product.id.in_(update.product_ids))
    ).all()

    if not products:
        raise HTTPException(
            status_code=404,
            detail="No matching products found"
        )

    for product in products:
        product.price = round(
            product.price * (1 + update.percentage / 100),
            2
        )
        product.updated_at = datetime.utcnow()
        session.add(product)

    session.commit()

    return {
        "message": f"Updated {len(products)} products successfully"
    } 
@app.patch("/products/{product_id}/stock")
def adjust_stock(
    product_id: int,
    adjustment: StockAdjustment,
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    if adjustment.operation == "add":
        product.stock += adjustment.quantity

    elif adjustment.operation == "remove":
        if product.stock < adjustment.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient stock"
            )

        product.stock -= adjustment.quantity

    else:
        raise HTTPException(
            status_code=400,
            detail="Operation must be 'add' or 'remove'"
        )

    product.updated_at = datetime.utcnow()

    session.add(product)
    session.commit()
    session.refresh(product)

    return {
        "message": "Stock updated successfully",
        "product": product
    }    


@app.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    session: Session = Depends(get_session)
):
    product = session.get(Product, product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    session.delete(product)
    session.commit()


@app.get("/products/search", response_model=List[Product])
def search_products(
    q: str,
    session: Session = Depends(get_session)
):
    query = select(Product).where(
        Product.name.contains(q) |
        Product.description.contains(q)
    )

    return session.exec(query).all()
    
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return error_response(
        request=request,
        status_code=exc.status_code,
        message=exc.detail,
    )
    
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return error_response(
        request=request,
        status_code=422,
        message="Validation Error",
        errors=exc.errors(),
    )
    
@app.exception_handler(IntegrityError)
async def integrity_exception_handler(
    request: Request,
    exc: IntegrityError,
):
    return error_response(
        request=request,
        status_code=400,
        message="Database integrity error",
    )
    
@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
):
    return error_response(
        request=request,
        status_code=500,
        message="Internal Server Error",
    )