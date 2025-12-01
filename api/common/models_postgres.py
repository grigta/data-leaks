"""
SQLAlchemy 2.0 models for PostgreSQL database.
"""
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Numeric, DateTime, JSON, Enum, ForeignKey, CheckConstraint, Index, Boolean, func, UniqueConstraint, BigInteger, Integer
from sqlalchemy.dialects import postgresql
from uuid import uuid4, UUID
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import enum


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class OrderStatus(enum.Enum):
    """Order status enumeration."""
    pending = "pending"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class OrderType(enum.Enum):
    """Order type enumeration."""
    reverse_ssn = "reverse_ssn"  # DEPRECATED: Used only for historical orders, new searches disabled
    instant_ssn = "instant_ssn"  # Instant SSN search via SearchBug API
    manual_ssn = "manual_ssn"    # Manual SSN ticket processed by worker


class TransactionStatus(enum.Enum):
    """Transaction status enumeration."""
    pending = "pending"
    paid = "paid"
    expired = "expired"
    failed = "failed"


class PaymentMethod(enum.Enum):
    """Payment method enumeration."""
    crypto = "crypto"
    card = "card"
    bank_transfer = "bank_transfer"


class TicketStatus(enum.Enum):
    """Ticket status enumeration."""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    rejected = "rejected"


class RegistrationStatus(enum.Enum):
    """Registration status enumeration."""
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MessageStatus(enum.Enum):
    """Message status enumeration."""
    pending = "pending"
    answered = "answered"
    closed = "closed"


class ContactMessageType(enum.Enum):
    """Contact message type enumeration."""
    bug_report = "bug_report"
    feature_request = "feature_request"


class SupportMessageType(enum.Enum):
    """Support thread message type enumeration."""
    bug_report = "bug_report"
    feature_request = "feature_request"
    general_question = "general_question"


class CouponType(enum.Enum):
    """Coupon type enumeration."""
    percentage = "percentage"
    fixed_amount = "fixed_amount"
    registration = "registration"
    registration_bonus = "registration_bonus"


class MessageType(enum.Enum):
    """Message type enumeration for support threads."""
    user = "user"
    admin = "admin"


class RequestSource(enum.Enum):
    """Request source enumeration."""
    web = "web"
    telegram_bot = "telegram_bot"
    other = "other"


class User(Base):
    """User model for authentication and profile management."""
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    access_code: Mapped[Optional[str]] = mapped_column(String(15), unique=True, nullable=True)
    api_token: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    telegram: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jabber: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    worker_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    banned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    instant_ssn_rules_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    instant_ssn_rules_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal('0.00'),
        nullable=False
    )
    invited_by: Mapped[Optional[UUID]] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True
    )
    invitation_code: Mapped[Optional[str]] = mapped_column(String(15), unique=True, nullable=True)
    invitation_bonus_received: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    orders: Mapped[List["Order"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cart_items: Mapped[List["CartItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[List["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[List["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    user_coupons: Mapped[List["UserCoupon"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    news: Mapped[List["News"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    manual_ssn_tickets: Mapped[List["ManualSSNTicket"]] = relationship(back_populates="user", foreign_keys="[ManualSSNTicket.user_id]", cascade="all, delete-orphan")
    assigned_tickets: Mapped[List["ManualSSNTicket"]] = relationship(back_populates="worker", foreign_keys="[ManualSSNTicket.worker_id]")
    telegram_chats: Mapped[List["TelegramChat"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    abuse_tracking: Mapped[List["InstantSSNAbuseTracking"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    support_threads: Mapped[List["SupportThread"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    support_messages: Mapped[List["SupportMessage"]] = relationship(back_populates="user", foreign_keys="[SupportMessage.user_id]", cascade="all, delete-orphan")
    contact_threads: Mapped[List["ContactThread"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    contact_messages: Mapped[List["ContactMessage"]] = relationship(back_populates="user", foreign_keys="[ContactMessage.user_id]", cascade="all, delete-orphan")
    custom_pricing: Mapped[List["CustomPricing"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    invited_users: Mapped[List["User"]] = relationship(back_populates="inviter", foreign_keys="[User.invited_by]")
    inviter: Mapped[Optional["User"]] = relationship(back_populates="invited_users", foreign_keys=[invited_by], remote_side=[id])

    # Table constraints
    __table_args__ = (
        CheckConstraint('balance >= 0', name='check_balance_non_negative'),
        Index('idx_users_email', 'email'),
        Index('idx_users_username', 'username'),
        Index('idx_users_access_code', 'access_code'),
        Index('idx_users_api_token', 'api_token'),
        Index('idx_users_is_admin', 'is_admin'),
        Index('idx_users_worker_role', 'worker_role'),
        Index('idx_users_is_banned', 'is_banned'),
        Index('idx_users_created_at', 'created_at'),
        Index('idx_users_invited_by', 'invited_by'),
        Index('idx_users_invitation_code', 'invitation_code'),
    )


class Order(Base):
    """Order model for purchase history."""
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    items: Mapped[dict] = mapped_column(JSON, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.pending, nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), default=OrderType.instant_ssn, nullable=False)
    is_viewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="orders")

    # Table constraints
    __table_args__ = (
        CheckConstraint('total_price >= 0', name='check_total_price_non_negative'),
        Index('idx_orders_user_id', 'user_id'),
        Index('idx_orders_status', 'status'),
        Index('idx_orders_order_type', 'order_type'),
        Index('idx_orders_created_at', 'created_at'),
        Index('idx_orders_is_viewed', 'is_viewed'),
        Index('idx_orders_user_type', 'user_id', 'order_type'),
    )


class CartItem(Base):
    """Cart item model for shopping cart."""
    __tablename__ = "cart_items"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ssn_record_id: Mapped[str] = mapped_column(String(50), nullable=False)
    ssn: Mapped[str] = mapped_column(String(11), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Enrichment metadata
    enrichment_attempted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enrichment_success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enrichment_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    enrichment_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="cart_items")

    # Table constraints
    __table_args__ = (
        CheckConstraint('price > 0', name='check_price_positive'),
        Index('idx_cart_user_id', 'user_id'),
        Index('idx_cart_ssn', 'ssn'),
    )


class Session(Base):
    """Session model for JWT token management."""
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="sessions")

    # Table constraints
    __table_args__ = (
        Index('idx_sessions_token', 'token'),
        Index('idx_sessions_user_id', 'user_id'),
    )


class Transaction(Base):
    """Transaction model for balance deposits and withdrawals."""
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod),
        default=PaymentMethod.crypto,
        nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus),
        default=TransactionStatus.pending,
        nullable=False
    )
    payment_provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    external_transaction_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    payment_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    network: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="transactions")

    # Table constraints
    __table_args__ = (
        CheckConstraint('amount > 0', name='check_amount_positive'),
        Index('idx_transactions_user_id', 'user_id'),
        Index('idx_transactions_status', 'status'),
        Index('idx_transactions_created_at', 'created_at'),
        Index('idx_transactions_external_id', 'external_transaction_id'),
        Index('idx_transactions_currency', 'currency'),
    )


class Coupon(Base):
    """Coupon model for deposit bonuses."""
    __tablename__ = "coupons"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    bonus_percent: Mapped[Optional[int]] = mapped_column(nullable=True)
    coupon_type: Mapped[CouponType] = mapped_column(Enum(CouponType), default=CouponType.percentage, nullable=False)
    bonus_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    requires_registration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_uses: Mapped[int] = mapped_column(nullable=False)
    current_uses: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user_coupons: Mapped[List["UserCoupon"]] = relationship(back_populates="coupon", cascade="all, delete-orphan")

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "bonus_percent IS NULL OR (coupon_type = 'percentage' AND bonus_percent > 0 AND bonus_percent <= 100)",
            name='check_bonus_percent_range'
        ),
        CheckConstraint('bonus_amount IS NULL OR bonus_amount > 0', name='check_bonus_amount_positive'),
        CheckConstraint('max_uses > 0', name='check_max_uses_positive'),
        CheckConstraint('current_uses >= 0', name='check_current_uses_non_negative'),
        CheckConstraint('current_uses <= max_uses', name='check_current_uses_within_limit'),
        Index('idx_coupons_is_active', 'is_active'),
        Index('idx_coupons_coupon_type', 'coupon_type'),
        # Note: idx_coupons_code not needed - unique constraint on 'code' already creates an index
    )


class UserCoupon(Base):
    """Junction table for user-coupon relationships."""
    __tablename__ = "user_coupons"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    coupon_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('coupons.id', ondelete='CASCADE'), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="user_coupons")
    coupon: Mapped["Coupon"] = relationship(back_populates="user_coupons")

    # Table constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'coupon_id', name='uq_user_coupon'),
        Index('idx_user_coupons_user_id', 'user_id'),
        Index('idx_user_coupons_coupon_id', 'coupon_id'),
    )


class News(Base):
    """News model for admin posts."""
    __tablename__ = "news"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    author: Mapped["User"] = relationship(back_populates="news")

    # Table constraints
    __table_args__ = (
        Index('idx_news_author_id', 'author_id'),
        Index('idx_news_created_at', 'created_at'),
        Index('idx_news_author_created', 'author_id', 'created_at'),
    )


class ManualSSNTicket(Base):
    """Manual SSN ticket model for worker processing."""
    __tablename__ = "manual_ssn_tickets"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    firstname: Mapped[str] = mapped_column(String(100), nullable=False)
    lastname: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.pending, nullable=False)
    worker_id: Mapped[Optional[UUID]] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    response_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_viewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[RequestSource] = mapped_column(Enum(RequestSource), default=RequestSource.web, nullable=False)
    order_id: Mapped[Optional[UUID]] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="manual_ssn_tickets", foreign_keys=[user_id])
    worker: Mapped[Optional["User"]] = relationship(back_populates="assigned_tickets", foreign_keys=[worker_id])
    message_reference: Mapped[Optional["TelegramMessageReference"]] = relationship(back_populates="ticket", uselist=False)

    # Table constraints
    __table_args__ = (
        Index('idx_manual_ssn_tickets_user_id', 'user_id'),
        Index('idx_manual_ssn_tickets_worker_id', 'worker_id'),
        Index('idx_manual_ssn_tickets_status', 'status'),
        Index('idx_manual_ssn_tickets_created_at', 'created_at'),
        Index('idx_manual_ssn_tickets_worker_status', 'worker_id', 'status'),
        Index('idx_manual_ssn_tickets_is_viewed', 'is_viewed'),
        Index('idx_manual_ssn_tickets_user_viewed', 'user_id', 'is_viewed'),
        Index('idx_manual_ssn_tickets_order_id', 'order_id'),
    )


class WorkerRegistrationRequest(Base):
    """Worker registration request model."""
    __tablename__ = "worker_registration_requests"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    access_code: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(Enum(RegistrationStatus), default=RegistrationStatus.pending, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Table constraints
    __table_args__ = (
        Index('idx_worker_registration_requests_status', 'status'),
        Index('idx_worker_registration_requests_access_code', 'access_code'),
        Index('idx_worker_registration_requests_created_at', 'created_at'),
    )


class InstantSSNSearch(Base):
    """Instant SSN search log model for tracking all search attempts."""
    __tablename__ = "instant_ssn_searches"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    search_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ssn_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_id: Mapped[Optional[UUID]] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    user_charged: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal('0.00'), nullable=False)
    source: Mapped[RequestSource] = mapped_column(Enum(RequestSource), default=RequestSource.web, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Table constraints
    __table_args__ = (
        CheckConstraint('api_cost >= 0', name='check_api_cost_non_negative'),
        CheckConstraint('user_charged >= 0', name='check_user_charged_non_negative'),
        Index('idx_instant_ssn_searches_user_id', 'user_id'),
        Index('idx_instant_ssn_searches_success', 'success'),
        Index('idx_instant_ssn_searches_created_at', 'created_at'),
        Index('idx_instant_ssn_searches_user_success', 'user_id', 'success'),
    )


class TelegramChat(Base):
    """Telegram chat model for bot integration."""
    __tablename__ = "telegram_chats"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    access_code: Mapped[str] = mapped_column(String(15), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    search_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="telegram_chats")

    # Table constraints
    __table_args__ = (
        # Note: idx_telegram_chats_chat_id not needed - unique constraint on 'chat_id' already creates an index
        Index('idx_telegram_chats_user_id', 'user_id'),
        Index('idx_telegram_chats_access_code', 'access_code'),
        Index('idx_telegram_chats_is_active', 'is_active'),
        Index('idx_telegram_chats_user_active', 'user_id', 'is_active'),
    )


class TelegramMessageReference(Base):
    """Telegram message reference for replying to original messages."""
    __tablename__ = "telegram_message_references"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('manual_ssn_tickets.id', ondelete='CASCADE'), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    ticket: Mapped["ManualSSNTicket"] = relationship(back_populates="message_reference")

    # Table constraints
    __table_args__ = (
        Index('idx_telegram_message_references_ticket_id', 'ticket_id'),
        Index('idx_telegram_message_references_created_at', 'created_at'),
        UniqueConstraint('ticket_id', name='uq_telegram_message_references_ticket_id'),
    )


class InstantSSNAbuseTracking(Base):
    """Instant SSN abuse tracking model for detecting and preventing abuse patterns."""
    __tablename__ = "instant_ssn_abuse_tracking"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    search_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    abuse_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_abuse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consecutive_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="abuse_tracking")

    # Table constraints
    __table_args__ = (
        Index('idx_abuse_user_id', 'user_id'),
        Index('idx_abuse_user_created', 'user_id', 'created_at'),
        Index('idx_abuse_type', 'abuse_type'),
    )


class SupportThread(Base):
    """Support thread model for grouping support messages."""
    __tablename__ = "support_threads"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message_type: Mapped[SupportMessageType] = mapped_column(Enum(SupportMessageType), default=SupportMessageType.general_question, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus), default=MessageStatus.pending, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="support_threads")
    messages: Mapped[List["SupportMessage"]] = relationship(back_populates="thread", cascade="all, delete-orphan")

    # Table constraints
    __table_args__ = (
        Index('idx_support_threads_user_id', 'user_id'),
        Index('idx_support_threads_status', 'status'),
        Index('idx_support_threads_message_type', 'message_type'),
        Index('idx_support_threads_last_message_at', 'last_message_at'),
        Index('idx_support_threads_user_status', 'user_id', 'status'),
    )


class SupportMessage(Base):
    """Support message model for individual messages within support threads."""
    __tablename__ = "support_messages"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('support_threads.id', ondelete='CASCADE'), nullable=False)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(Enum(MessageType), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    thread: Mapped["SupportThread"] = relationship(back_populates="messages")
    user: Mapped["User"] = relationship(back_populates="support_messages", foreign_keys=[user_id])

    # Table constraints
    __table_args__ = (
        Index('idx_support_messages_thread_id', 'thread_id'),
        Index('idx_support_messages_user_id', 'user_id'),
        Index('idx_support_messages_message_type', 'message_type'),
        Index('idx_support_messages_is_read', 'is_read'),
        Index('idx_support_messages_thread_read', 'thread_id', 'is_read'),
        Index('idx_support_messages_created_at', 'created_at'),
    )


class ContactThread(Base):
    """Contact thread model for grouping contact messages."""
    __tablename__ = "contact_threads"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message_type: Mapped[ContactMessageType] = mapped_column(Enum(ContactMessageType), nullable=False)
    status: Mapped[MessageStatus] = mapped_column(Enum(MessageStatus), default=MessageStatus.pending, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="contact_threads")
    messages: Mapped[List["ContactMessage"]] = relationship(back_populates="thread", cascade="all, delete-orphan")

    # Table constraints
    __table_args__ = (
        Index('idx_contact_threads_user_id', 'user_id'),
        Index('idx_contact_threads_status', 'status'),
        Index('idx_contact_threads_last_message_at', 'last_message_at'),
        Index('idx_contact_threads_user_status', 'user_id', 'status'),
        Index('idx_contact_threads_message_type', 'message_type'),
    )


class ContactMessage(Base):
    """Contact message model for individual messages within contact threads."""
    __tablename__ = "contact_messages"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    thread_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('contact_threads.id', ondelete='CASCADE'), nullable=False)
    user_id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[MessageType] = mapped_column(Enum(MessageType), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    thread: Mapped["ContactThread"] = relationship(back_populates="messages")
    user: Mapped["User"] = relationship(back_populates="contact_messages", foreign_keys=[user_id])

    # Table constraints
    __table_args__ = (
        Index('idx_contact_messages_thread_id', 'thread_id'),
        Index('idx_contact_messages_user_id', 'user_id'),
        Index('idx_contact_messages_message_type', 'message_type'),
        Index('idx_contact_messages_is_read', 'is_read'),
        Index('idx_contact_messages_thread_read', 'thread_id', 'is_read'),
        Index('idx_contact_messages_created_at', 'created_at'),
    )


class MaintenanceMode(Base):
    """Maintenance mode model for service-level maintenance management."""
    __tablename__ = "maintenance_modes"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    service_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Table constraints
    __table_args__ = (
        Index('idx_maintenance_modes_service_name', 'service_name'),
        Index('idx_maintenance_modes_is_active', 'is_active'),
    )


class CustomPricing(Base):
    """Custom pricing model for user-specific service pricing."""
    __tablename__ = "custom_pricing"

    id: Mapped[UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4)
    access_code: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(postgresql.UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    service_name: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="custom_pricing")

    # Table constraints
    __table_args__ = (
        CheckConstraint('price >= 0', name='check_custom_pricing_price_non_negative'),
        CheckConstraint('(access_code IS NOT NULL) OR (user_id IS NOT NULL)', name='check_custom_pricing_identifier_required'),
        UniqueConstraint('access_code', 'service_name', name='uq_custom_pricing_access_code_service'),
        UniqueConstraint('user_id', 'service_name', name='uq_custom_pricing_user_service'),
        Index('idx_custom_pricing_access_code', 'access_code'),
        Index('idx_custom_pricing_user_id', 'user_id'),
        Index('idx_custom_pricing_service_name', 'service_name'),
        Index('idx_custom_pricing_is_active', 'is_active'),
    )
