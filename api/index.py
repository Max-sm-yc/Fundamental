from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
from .risk_engine import RiskEngine
import uvicorn

app = FastAPI()

class PortfolioRequest(BaseModel):
    tickers: List[str]
    weights: List[float]
    lookback_years: int = 5
    confidence_level: float = 0.95
    stress_weight: float = 0.4

class AnalysisResponse(BaseModel):
    volatility: float
    var: float
    cvar: float
    risk_contribution: Dict[str, float]
    raroc: Dict[str, float]
    target_allocation: Dict[str, float]
    component_cvar: Dict[str, float]

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_portfolio(request: PortfolioRequest):
    if len(request.tickers) != len(request.weights):
        raise HTTPException(status_code=400, detail="Number of tickers and weights must match")
    
    portfolio_weights = dict(zip(request.tickers, request.weights))
    
    try:
        engine = RiskEngine(
            portfolio_weights=portfolio_weights,
            lookback_years=request.lookback_years,
            confidence_level=request.confidence_level,
            stress_weight=request.stress_weight
        )
        results = engine.generate_metrics()
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
