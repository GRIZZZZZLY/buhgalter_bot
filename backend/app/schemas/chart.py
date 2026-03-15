from pydantic import BaseModel


class ChartPoint(BaseModel):
    label: str
    amount: str


class ChartResponse(BaseModel):
    period: str
    type: str
    points: list[ChartPoint]
