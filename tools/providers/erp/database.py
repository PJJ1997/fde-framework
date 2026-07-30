"""SQLite database for ERP orders."""
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from datetime import datetime


class OrderDatabase:
    """Order database manager using SQLite."""

    def __init__(self, db_path: str = "data/orders.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database and create orders table if not exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    total_amount REAL NOT NULL,
                    address TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    cancel_reason TEXT
                )
            """)
            
            # Create index for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_customer_name 
                ON orders(customer_name)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON orders(status)
            """)
            
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        try:
            yield conn
        finally:
            conn.close()

    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            count = cursor.fetchone()[0]
            return f"ORD-{1001 + count}"

    def create_order(
        self,
        customer_name: str,
        product_name: str,
        quantity: int,
        price: float,
        address: str,
    ) -> Dict[str, Any]:
        """Create a new order."""
        order_id = self._generate_order_id()
        total_amount = quantity * price
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (
                    order_id, customer_name, product_name, quantity, price,
                    total_amount, address, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id, customer_name, product_name, quantity, price,
                total_amount, address, "created", now, now
            ))
            conn.commit()

        return self.get_order(order_id)

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None

    def update_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        address: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update order fields."""
        order = self.get_order(order_id)
        if not order:
            return None

        updates = []
        params = []

        if quantity is not None:
            updates.append("quantity = ?")
            params.append(quantity)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if address is not None:
            updates.append("address = ?")
            params.append(address)
        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if updates:
            # Recalculate total_amount if quantity or price changed
            new_quantity = quantity if quantity is not None else order["quantity"]
            new_price = price if price is not None else order["price"]
            new_total = new_quantity * new_price

            updates.append("total_amount = ?")
            params.append(new_total)
            
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            
            params.append(order_id)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE orders SET {', '.join(updates)} WHERE order_id = ?",
                    params
                )
                conn.commit()

        return self.get_order(order_id)

    def delete_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Delete order permanently."""
        order = self.get_order(order_id)
        if not order:
            return None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
            conn.commit()

        return order

    def cancel_order(self, order_id: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Cancel an order (set status to cancelled)."""
        order = self.get_order(order_id)
        if not order:
            return None

        # Check if order can be cancelled
        if order["status"] in ["cancelled", "completed"]:
            return None  # Cannot cancel

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE orders
                SET status = ?, cancelled_at = ?, cancel_reason = ?, updated_at = ?
                WHERE order_id = ?
            """, (
                "cancelled",
                datetime.now().isoformat(),
                reason or "未提供原因",
                datetime.now().isoformat(),
                order_id
            ))
            conn.commit()

        return self.get_order(order_id)

    def list_orders(
        self,
        customer_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """List orders with optional filters."""
        query = "SELECT * FROM orders WHERE 1=1"
        params = []

        if customer_name:
            query += " AND customer_name = ?"
            params.append(customer_name)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]


# Global database instance
_db_instance = None


def get_db() -> OrderDatabase:
    """Get or create global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = OrderDatabase()
    return _db_instance
