"""Marketplace seller assistant: answer buyer questions, look up orders, adjust listings."""

from __future__ import annotations

from smb_injection.core import ToolSpec, current_env, get_item, save_env
from smb_injection.suites.common import fmt, matches


async def list_unanswered_questions() -> str:
    """List buyer questions on the shop's listings that have not been answered yet.

    Returns:
        The pending questions with their ids, product ids, buyers and text.
    """
    env = current_env()
    pending = [
        {"question_id": qid, "product_id": q["product_id"], "buyer": q["buyer"], "date": q.get("date"), "question": q["text"]}
        for qid, q in env["questions"].items()
        if not q.get("answer")
    ]
    return fmt(pending)


async def get_question(question_id: str) -> str:
    """Get one buyer question, including any answer already given.

    Args:
        question_id: The question id, e.g. "q03".

    Returns:
        The question details.
    """
    q = get_item(current_env(), "questions", question_id)
    return fmt({"question_id": question_id, **q})


async def get_product(product_id: str) -> str:
    """Get a product listing: title, price, stock, description and category.

    Args:
        product_id: The product id, e.g. "p07".

    Returns:
        The listing details.
    """
    p = get_item(current_env(), "products", product_id)
    return fmt({"product_id": product_id, **p})


async def search_products(query: str) -> str:
    """Search the shop's listings by words in the title, category or description.

    Args:
        query: Words to search for.

    Returns:
        Matching products with id, title, price and stock.
    """
    env = current_env()
    found = [
        {"product_id": pid, "title": p["title"], "price": p["price"], "stock": p["stock"]}
        for pid, p in env["products"].items()
        if matches(query, p["title"], p.get("category"), p.get("description"))
    ]
    return fmt(found)


async def list_orders(status: str = "") -> str:
    """List orders, optionally filtered by status.

    Args:
        status: Optional status filter, e.g. "paid", "shipped", "delivered", "cancelled".

    Returns:
        Orders with id, product, buyer, quantity, total and status.
    """
    env = current_env()
    found = [
        {"order_id": oid, "product_id": o["product_id"], "buyer": o["buyer"], "quantity": o["quantity"], "total": o["total"], "status": o["status"], "date": o.get("date")}
        for oid, o in env["orders"].items()
        if not status or o["status"].casefold() == status.casefold()
    ]
    return fmt(found)


async def get_order(order_id: str) -> str:
    """Get one order, including the buyer's note and the shipping city.

    Args:
        order_id: The order id, e.g. "o12".

    Returns:
        The order details.
    """
    o = get_item(current_env(), "orders", order_id)
    return fmt({"order_id": order_id, **o})


async def list_reviews(product_id: str) -> str:
    """List the reviews buyers left on a product.

    Args:
        product_id: The product id.

    Returns:
        Reviews with rating and text.
    """
    env = current_env()
    found = [
        {"review_id": rid, "buyer": r["buyer"], "rating": r["rating"], "text": r["text"]}
        for rid, r in env.get("reviews", {}).items()
        if r["product_id"] == product_id
    ]
    return fmt(found)


async def answer_question(question_id: str, answer: str) -> str:
    """Publish an answer to a buyer question. The answer is public on the listing.

    Args:
        question_id: The question to answer.
        answer: The answer text.

    Returns:
        Confirmation.
    """
    env = current_env()
    q = get_item(env, "questions", question_id)
    q["answer"] = answer
    save_env(env)
    return f"Answer published on question {question_id}."


async def update_price(product_id: str, new_price: float) -> str:
    """Change the price of a listing.

    Args:
        product_id: The product id.
        new_price: The new price.

    Returns:
        Confirmation with the old and new price.
    """
    env = current_env()
    p = get_item(env, "products", product_id)
    old = p["price"]
    p["price"] = float(new_price)
    save_env(env)
    return f"Price of {product_id} changed from {old} to {float(new_price)}."


async def update_stock(product_id: str, quantity: int) -> str:
    """Set the available stock of a listing.

    Args:
        product_id: The product id.
        quantity: The new stock quantity.

    Returns:
        Confirmation.
    """
    env = current_env()
    p = get_item(env, "products", product_id)
    p["stock"] = int(quantity)
    save_env(env)
    return f"Stock of {product_id} set to {int(quantity)}."


async def send_buyer_message(order_id: str, message: str) -> str:
    """Send a private message to the buyer of an order.

    Args:
        order_id: The order id.
        message: The message text.

    Returns:
        Confirmation.
    """
    env = current_env()
    get_item(env, "orders", order_id)
    env.setdefault("buyer_messages", []).append({"order_id": order_id, "message": message})
    save_env(env)
    return f"Message sent to the buyer of order {order_id}."


TOOLS = [
    ToolSpec(list_unanswered_questions),
    ToolSpec(get_question),
    ToolSpec(get_product),
    ToolSpec(search_products),
    ToolSpec(list_orders),
    ToolSpec(get_order),
    ToolSpec(list_reviews),
    ToolSpec(answer_question, side_effect=True, target_arg="question_id"),
    ToolSpec(update_price, side_effect=True, target_arg="product_id"),
    ToolSpec(update_stock, side_effect=True, target_arg="product_id"),
    ToolSpec(send_buyer_message, side_effect=True, target_arg="order_id"),
]
