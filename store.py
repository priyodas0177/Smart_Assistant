from database import get_connection
from bs4 import BeautifulSoup
import re, time, requests, psycopg2
from datetime import datetime

conn=get_connection()
cursor=conn.cursor()

#------------WEB--------
Base="https://www.gsmarena.com/"
Header={
    "User-Agent": "Mozilla/5.0"

}

#URL→Download HTML→Convert→Ready to extract data
def get_soup(url:str)->BeautifulSoup: 
    r=requests.get(url, headers=Header, timeout=15) 
    r.raise_for_status() 
    return BeautifulSoup(r.text, "html.parser") 

#It finds the first number inside a text and returns it as an integer.
def first_int(text:str):
    if not text:
        return None
    m=re.search(r"(\d+)", text.replace(",",""))  
    return int(m.group(1)) if m else None

#date
def parse_release_date(announced_text: str):
    if not announced_text:
        return None
    
    #2023, february 01
    m=re.search(r"(\d{4}),\s*([A-Za-z]+)\s*(\d{1,2})", announced_text)
    if m:
        year, month, day=int(m.group(1)), m.group(2), int(m.group(3))
        try:
            return datetime.strptime(f"{year}-{month}-{day}", "%Y-%B-%d").date()
        except:
            return None 
        
    #date is missing
    m = re.search(r"(\d{4}),\s*([A-Za-z]+)", announced_text)
    if m:
        year,month=int(m.group(1)), m.group(2)
        try:
            return datetime.strptime(f"{year}-{month}-01", "%Y-%B-%d").date()
        except:
            return None
    
    #date month missing
    m=re.search(r"(\d{4})",announced_text)
    if m:
        return datetime(int(m.group(1)),1,1).date()
    return  None

#best ram
def ram_storage(internal_text: str):
    if not internal_text:
        return None,None
    pairs= re.findall(r"(\d+)\s*GB\s+(\d+)\s*GB\s+RAM", internal_text, flags=re.I)
    best_storage=None 
    best_ram=None

    for st, rm in pairs:
        st_i, rm_i=int(st), int(rm) 
        if best_storage is None or st_i>best_storage: 
            best_storage=st_i
            best_ram=rm_i
    return best_ram, best_storage

#price
def parse_price(text:str):
    return first_int(text)

#---------------DATABASE-------------
def get_or_create_brand(cursor,brand_name:str):
    """Insert brand if not exist, return brand_id"""
    cursor.execute("SELECT id from brands WHERE brand_name=%s",(brand_name,))
    row=cursor.fetchone()
    if row: return row[0]
    cursor.execute("INSERT INTO brands (brand_name) VALUES (%s) RETURNING id", (brand_name,))
    return cursor.fetchone()[0]

def upsert_phone(cursor,phone: dict):
    brand_id=get_or_create_brand(cursor,phone["brand"])
    cursor.execute("""
    INSERT INTO phones (
        brand_id, model_name, release_date,
        display_size, display_type,
        battery_mah, camera_mp,
        ram_gb, storage_gb, price_usd
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (brand_id, model_name) DO UPDATE SET
        release_date = EXCLUDED.release_date,
        display_size = EXCLUDED.display_size,
        display_type = EXCLUDED.display_type,
        battery_mah  = EXCLUDED.battery_mah,
        camera_mp    = EXCLUDED.camera_mp,
        ram_gb       = EXCLUDED.ram_gb,
        storage_gb   = EXCLUDED.storage_gb,
        price_usd    = EXCLUDED.price_usd
""", (
    brand_id,
    phone["model_name"],
    phone["release_date"],
    phone["display_size"],
    phone["display_type"],
    phone["battery_mah"], 
    phone["camera_mp"],
    phone["ram_gb"],
    phone["storage_gb"],
    phone["price_usd"],
))

# ------------------------ Scrapers ------------------------
def scrape_gsmarena(phone_url:str):
    """Scrape phone specs from gsmarena"""
    soup=get_soup(phone_url)

    #brand & model
    title=soup.select_one("H1.specs-phone-name-title")
    if not title:return None
    full_name=title.get_text(strip=True)
    brand=full_name.split()[0]
    model_name=full_name

    #specs table
    specs={}
    for row in soup.select("table tr"):
        key=row.select_one("td.ttl a")
        val=row.select_one("td.nfo")
        if key and val:
            k=key.getText(" ",strip=True).lower()
            v=val.get_text(" ",strip=True)
            specs[k]=v

    release_date=parse_release_date(specs.get("announced"))
    display_text=specs.get("size", " ")
    display_type=specs.get("type", " ")
    battery=None
    camera=None

    for v in specs.values():
        if "mAh" in v:
            battery=first_int(v)
            if battery: break

    for v in specs.values():
        if "MP" in v:
            mp=first_int(v)
            if mp and mp>=8:
                camera=mp
                break
    ram,storage=ram_storage(specs.get("internal", ""))
    price_text=parse_price(price_text) if price_text else None
    price=parse_price(price_text) if price_text else None

    return {
        "brand": brand,
        "model_name": model_name,
        "release_date": release_date,
        "display_size": first_int(display_text),
        "display_type": display_type,
        "battery_mah": battery,
        "camera_mp": camera,
        "ram_gb": ram,
        "storage_gb": storage,
        "price_usd": price
    }

def scrape_dazzle(phone_name:str):
    """Optional: scrape price from Dazzle Bangladesh."""
    search_url=f"https://dazzle.com.bd/search?q={phone_name.replace(' ','+')}"
    soup=get_soup(search_url)
    price_tag=soup.select_one(".product-price")
    if not price_tag:return None
    price= parse_price(price_tag.get_text())
    return {"price_usd":price}
