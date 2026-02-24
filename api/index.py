from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
from .risk_engine import RiskEngine
import uvicorn

app = FastAPI()

class PMAllocation(BaseModel):
    name: str
    assets: Dict[str, float]

class PortfolioRequest(BaseModel):
    pms: List[PMAllocation]
    lookback_years: int = 5
    confidence_level: float = 0.95
    stress_weight: float = 0.4

class AnalysisResponse(BaseModel):
    volatility: float
    var: float
    cvar: float
    risk_contribution: Dict[str, float]
    asset_risk_absolute: Dict[str, float]
    raroc: Dict[str, float]
    target_allocation: Dict[str, float]
    component_cvar: Dict[str, float]
    component_cvar_relative: Dict[str, float]
    current_allocation: Dict[str, float]

@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_portfolio(request: PortfolioRequest):
    if not request.pms:
        raise HTTPException(status_code=400, detail="At least one portfolio is required for analysis")
    
    # Extract PM configs. Note: Frontend should only send 'selected' portfolios if they want to group them.
    pm_configs = {pm.name: pm.assets for pm in request.pms}
    
    try:
        engine = RiskEngine(
            pm_configs=pm_configs,
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
