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
    "Cookie": "SPC_F=8bbvhn40hZ2SRUTCpSJ3EqOeE9Gk6NNL; _QPWSDCXHZQA=7de2c4f8-ab24-42cd-d5c5-d114e9cd9563; REC7iLP4Q=93ba7c46-7e95-415b-b04c-9c7d7527f403; SPC_CLIENTID=OGJidmhuNDBoWjJTohjfyfatgfgfjbup; _gcl_au=1.1.553767689.1772039834; _fbp=fb.2.1772039838480.632403724414090406; blueID=c4d24ed8-28c4-4928-b033-4e56c92b2970; _gcl_gs=2.1.k1$i1772066140$u53233770; _ga=GA1.1.493474339.1772039834; _sapid=59722d11f65eb2785c2fe113fdd8def136a963bbf6d1305991176c55; csrftoken=eCxncpIsPknBhaM8VFp5SUIB75FNbBqZ; SPC_U=4424988819; SPC_R_T_ID=haSdXP/M6VQpo5MqbuFufE/Aquel2SFhruNYjzKo3xzRk9zCGfqZzS2XDL0x6ojSLH0cTZAXiKIBpEuRX5bwJv+gOXV5oS1JuS2MVOZgVLB0+sUNVhBVEwt9zn55ejIkrS4vB/RyMZvD399Zax8mUyD3ptjzTAnmRnnFRXUg1aI=; SPC_R_T_IV=aHlzdFZPZGdJZGlDWHo4Zg==; SPC_CDS_CHAT=e07d36f8-8d16-467a-9706-3f002ecabe82; shopee_webUnique_ccd=gt%2BASjdNtevndmS7WdhUaQ%3D%3D%7C7GJ5Rcwrbk5pjt%2F6GcPBWPDn6eWOEib%2FK24ioJaZGcFMlKFyf6zE4lKotBEY0v0F4h4v20Edz5HS%2Fg%3D%3D%7CA9lgiRTHnyCF%2BItq%7C08%7C3; ds=d21fdbff13c69e690aa3bb7c350c4976; _ga_T69DLR1QPG=GS2.1.s1775525793$o8$g1$t1775526648$j39$l1$h725035234"
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
            print("RESPOSTA CRUA DA SHOPEE:", data)
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
