
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models

from api.routes.auth import router as auth_router
from api.routes.shops import router as shops_router
from api.routes.products import router as products_router
from api.routes.inventory import router as inventory_router
from api.routes.customers import router as customers_router
from api.routes.orders import router as orders_router
from api.routes.analytics import router as analytics_router
from api.routes.payments import router as payments_router
from api.routes.payment_capture import router as payment_capture_router
from api.routes.ml import router as ml_router
from api.routes.ai_workforce import router as ai_workforce_router
from api.routes.ai_chat import router as ai_chat_router


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="DUKAANTRA API",
    description="Retail business intelligence workspace",
    version="1.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True
    },
)


# --------------------------------------------------
# CORS CONFIGURATION
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# API ROUTERS
# --------------------------------------------------

app.include_router(auth_router, prefix="/api/v1")
app.include_router(shops_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(customers_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(payment_capture_router, prefix="/api/v1")
app.include_router(ml_router, prefix="/api/v1")
app.include_router(ai_workforce_router, prefix="/api/v1")
app.include_router(ai_chat_router, prefix="/api/v1")


# --------------------------------------------------
# ROOT ENDPOINT
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "DUKAANTRA API",
        "description": "Retail business intelligence workspace",
        "version": "1.0.0",
        "status": "running",
    }


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "DUKAANTRA Backend",
    }
