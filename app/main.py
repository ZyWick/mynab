from fastapi import FastAPI

from app.routers import auth, budget, categories, me, plaid, transactions

app = FastAPI(title="my-ynab", version="0.1.0")

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(plaid.router)
app.include_router(categories.router)
app.include_router(budget.router)
app.include_router(transactions.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
