from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    stocks: Mapped[list[Stock]] = relationship(back_populates="industry")  # type: ignore[name-defined]


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id"), index=True)
    industry: Mapped[Industry] = relationship(back_populates="stocks")

    purchase_date: Mapped[dt.date] = mapped_column(Date)
    purchase_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    purchase_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    prices: Mapped[list[PricePoint]] = relationship(back_populates="stock")  # type: ignore[name-defined]


class PricePoint(Base):
    __tablename__ = "price_points"
    __table_args__ = (
        UniqueConstraint("stock_id", "observed_at", name="uq_price_points_stock_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)

    stock: Mapped[Stock] = relationship(back_populates="prices")
