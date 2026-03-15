from fastapi import APIRouter, Query

from app.schemas.chart import ChartPoint, ChartResponse

router = APIRouter()


@router.get("/chart", response_model=ChartResponse)
def get_chart(
    period: str = Query(default="month", pattern="^(today|week|month|all)$"),
    type: str = Query(default="categories", pattern="^categories$"),
) -> ChartResponse:
    return ChartResponse(period=period, type=type, points=[ChartPoint(label="other", amount="0.00")])
