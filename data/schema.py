from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from framework.core.decorators import Table

class Address(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str

class Product(BaseModel):
    product_id: int
    name: str
    category: str
    price: float
    tags: List[str]

@Table("users")
class User(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime
    last_login: datetime
    address: Address

@Table("orders")
class Order(BaseModel):
    id: int
    user_id: int
    status: str
    total_amount: float
    ordered_at: datetime
    items: List[Product]
