from fastapi import APIRouter, HTTPException

from app.schemas import HealthResponse, OptimizeEnergyRequest, OptimizeEnergyResponse
from app.services.interpret import InterpretationError
from app.services.optimizer import OptimizationError
from app.services.pipeline import build_optimize_response

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post(
    "/optimize-energy",
    response_model=OptimizeEnergyResponse,
    response_model_exclude_none=True,
)
def optimize_energy(payload: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
    try:
        return build_optimize_response(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InterpretationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OptimizationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
