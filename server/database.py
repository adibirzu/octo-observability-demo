"""Database engine, session management, and models."""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey,
    func, text, event,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from server.config import cfg

engine = create_async_engine(
    cfg.database_url,
    pool_size=cfg.db_pool_size,
    max_overflow=cfg.db_max_overflow,
    pool_timeout=cfg.db_pool_timeout,
    pool_pre_ping=True,
    echo=False,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session with chaos simulation support."""
    if cfg.simulate_db_disconnect:
        raise ConnectionError("Simulated database disconnect")
    if cfg.simulate_db_latency:
        await asyncio.sleep(2.5)  # artificial latency
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── ORM Models ──────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    phone = Column(String(50))
    company = Column(String(200))
    industry = Column(String(100))
    revenue = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    orders = relationship("Order", back_populates="customer")
    tickets = relationship("SupportTicket", back_populates="customer")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    sku = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    category = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    total = Column(Float, nullable=False)
    status = Column(String(50), default="pending")
    notes = Column(Text)
    shipping_address = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")
    product = relationship("Product")


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    invoice_number = Column(String(50), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    tax = Column(Float, default=0.0)
    status = Column(String(50), default="unpaid")
    due_date = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    order = relationship("Order")


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    subject = Column(String(300), nullable=False)
    description = Column(Text)
    priority = Column(String(20), default="medium")
    status = Column(String(50), default="open")
    assigned_to = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    customer = relationship("Customer", back_populates="tickets")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(50), default="user")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    action = Column(String(100), nullable=False)
    resource = Column(String(200))
    details = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    trace_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    report_type = Column(String(50))
    query = Column(Text)
    parameters = Column(Text)
    created_by = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    campaign_type = Column(String(50), default="email")  # email, sms, social, ppc
    status = Column(String(50), default="draft")  # draft, active, paused, completed
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    target_audience = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    leads = relationship("Lead", back_populates="campaign")


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    email = Column(String(200), nullable=False)
    name = Column(String(200))
    source = Column(String(100))  # web, referral, social, paid
    status = Column(String(50), default="new")  # new, contacted, qualified, converted, lost
    score = Column(Integer, default=0)
    notes = Column(Text)
    converted_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    campaign = relationship("Campaign", back_populates="leads")
    customer = relationship("Customer")


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    tracking_number = Column(String(100))
    carrier = Column(String(100))  # fedex, ups, dhl, usps
    status = Column(String(50), default="processing")  # processing, shipped, in_transit, delivered, returned
    origin_region = Column(String(50))  # us-east, eu-west, ap-southeast, etc.
    destination_region = Column(String(50))
    weight_kg = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    estimated_delivery = Column(DateTime)
    actual_delivery = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    order = relationship("Order")


class PageView(Base):
    __tablename__ = "page_views"
    id = Column(Integer, primary_key=True)
    page = Column(String(200), nullable=False)
    visitor_ip = Column(String(50))
    visitor_region = Column(String(50))  # detected from header or GeoIP
    user_agent = Column(String(500))
    load_time_ms = Column(Integer)
    referrer = Column(String(500))
    session_id = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    region = Column(String(50), nullable=False)  # us-east-1, eu-west-1, ap-southeast-1
    address = Column(Text)
    capacity = Column(Integer, default=10000)
    current_stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
