from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import time
from typing import Optional

app = FastAPI(title="ShopeeAnalytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://shopee.com.br/",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "x-api-source": "pc",
    "x-requested-with": "XMLHttpRequest",
    "af-ac-enc-dat": "null",
}


def format_item(raw):
    item = raw.get("item_basic") or raw
    price = item.get("price", 0) / 100000
    price_old = item.get("price_before_discount", 0) / 100000
    ctime = item.get("ctime", 0)
    date_str = ""
    if ctime:
        import datetime
        date_str = datetime.datetime.fromtimestamp(ctime).strftime("%d/%m/%Y")

    img = item.get("image", "")
    img_url = f"https://down-br.img.susercontent.com/file/{img}" if img else ""

    rating = item.get("item_rating", {})
    stars = round(rating.get("rating_star", 0), 1)
    rating_count = sum(rating.get("rating_count", []))

    sold = item.get("historical_sold") or item.get("sold") or 0
    stock = item.get("stock", 0)

    return {
        "itemid": item.get("itemid"),
        "shopid": item.get("shopid"),
        "name": item.get("name", ""),
        "image": img_url,
        "price": round(price, 2),
        "price_before_discount": round(price_old, 2) if price_old > price else None,
        "discount": item.get("raw_discount", 0),
        "sold": sold,
        "stock": stock,
        "rating_star": stars,
        "rating_count": rating_count,
        "shop_name": item.get("shop_name", ""),
        "shop_location": item.get("shop_location", ""),
        "created_date": date_str,
        "ctime": ctime,
        "url": f"https://shopee.com.br/product/{item.get('shopid')}/{item.get('itemid')}",
        "is_official_shop": item.get("is_official_shop", False),
        "liked_count": item.get("liked_count", 0),
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "ShopeeAnalytics API"}


@app.get("/search")
async def search(
    keyword: str = Query(..., min_length=1),
    sort: str = Query("relevance"),
    page: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=60),
):
    sort_map = {
        "relevance": ("relevancy", "desc"),
        "sales": ("sales", "desc"),
        "price_asc": ("price", "asc"),
        "price_desc": ("price", "desc"),
        "newest": ("ctime", "desc"),
    }
    by, order = sort_map.get(sort, ("relevancy", "desc"))
    newest = page * limit

    url = (
        f"https://shopee.com.br/api/v4/search/search_items"
        f"?by={by}&keyword={keyword}&limit={limit}&newest={newest}"
        f"&order={order}&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
    )

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(url, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Shopee retornou erro: {e.response.status_code}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Erro ao conectar à Shopee: {str(e)}")

    items = data.get("items") or []
    formatted = [format_item(i) for i in items]

    prices = [p["price"] for p in formatted if p["price"] > 0]
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0
    total_sold = sum(p["sold"] for p in formatted)
    max_sold = max((p["sold"] for p in formatted), default=0)

    return {
        "keyword": keyword,
        "page": page,
        "total_results": len(formatted),
        "stats": {
            "avg_price": avg_price,
            "total_sold": total_sold,
            "max_sold": max_sold,
        },
        "items": formatted,
    }


@app.get("/product/{shop_id}/{item_id}")
async def product_detail(shop_id: int, item_id: int):
    url = f"https://shopee.com.br/api/v4/item/get?itemid={item_id}&shopid={shop_id}"

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(url, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    item = data.get("data") or data.get("item") or {}
    if not item:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    price = item.get("price", 0) / 100000
    price_old = item.get("price_before_discount", 0) / 100000
    ctime = item.get("ctime", 0)
    date_str = ""
    if ctime:
        import datetime
        date_str = datetime.datetime.fromtimestamp(ctime).strftime("%d/%m/%Y")

    images = [
        f"https://down-br.img.susercontent.com/file/{img}"
        for img in (item.get("images") or [])
    ]

    rating = item.get("item_rating", {})
    rating_detail = {
        "star": round(rating.get("rating_star", 0), 1),
        "count": sum(rating.get("rating_count", [])),
        "breakdown": rating.get("rating_count", []),
    }

    return {
        "itemid": item.get("itemid"),
        "shopid": item.get("shopid"),
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "images": images,
        "price": round(price, 2),
        "price_before_discount": round(price_old, 2) if price_old > price else None,
        "discount": item.get("raw_discount", 0),
        "sold": item.get("historical_sold") or item.get("sold") or 0,
        "stock": item.get("stock", 0),
        "rating": rating_detail,
        "shop_name": item.get("shop_name", ""),
        "shop_location": item.get("shop_location", ""),
        "created_date": date_str,
        "url": f"https://shopee.com.br/product/{shop_id}/{item_id}",
        "brand": item.get("brand", ""),
        "categories": [c.get("display_name", "") for c in (item.get("categories") or [])],
        "liked_count": item.get("liked_count", 0),
        "view_count": item.get("view_count", 0),
    }


@app.get("/shop/{shop_id}")
async def shop_info(shop_id: int):
    url = f"https://shopee.com.br/api/v4/product/get_shop_info?shopid={shop_id}"

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(url, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    shop = data.get("data") or {}
    return {
        "shopid": shop_id,
        "name": shop.get("name", ""),
        "description": shop.get("description", ""),
        "rating": shop.get("rating_star", 0),
        "total_products": shop.get("item_count", 0),
        "followers": shop.get("follower_count", 0),
        "response_rate": shop.get("response_rate", 0),
        "response_time": shop.get("response_time", 0),
        "location": shop.get("shop_location", ""),
        "is_official": shop.get("is_official_shop", False),
        "url": f"https://shopee.com.br/{shop.get('account', {}).get('username', '')}",
    }
