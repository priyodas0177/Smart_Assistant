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

#------------------- collect 20-30 phone links-----------
#It collects Samsung phone page links from GSMArena until it reaches the limit (30).
def phone_link(limit=30, delay=1.0):
    links= [] 
    seen= set() 

    page_urls=[Base + "samsung-phones-9.php"]
    for p in range(2,8):
        page_urls.append(Base+f"samsung-phones-f-9-0-p{p}.php")

    for page_url in page_urls:
        soup=get_soup(page_url) 

        for a in soup.select(".makers li a"):
            href=a.get("href") 
            if not href or not href.endswith(".php"):
                continue
            full=Base+href
            if full not in seen: 
                seen.add(full)
                links.append(full)
            if len(links) >=limit: 
                return links
        time.sleep(delay)
    return links


def phone_details(phone_url:str):
    soup=get_soup(phone_url)

    #model name
    phone_name=soup.select_one("h1.specs-phone-name-title")
    model_name=phone_name.get_text(strip=True) if phone_name else None

    #phone specs
    specs={}
    for row in soup.select("table tr"):
        key=row.select_one("td.ttl a")
        val=row.select_one("td.nfo")
        if key and val:
            k=key.get_text(" ",strip=True).lower() 
            v=val.get_text(" ",strip=True) 
            specs[k]=v

    #release date 
    release_date=parse_release_date(specs.get("announced"))

    #display
    display_size=specs.get("size")
    display_type=specs.get("type")
    display=" | ".join([x for x in [display_size, display_type] if x]) or None

    #battery
    battery=None
    for v in specs.values():
        if "mAh" in v:
            battery=first_int(v)
            if battery:
                break
    
    #camera
    camera=None
    for v in specs.values():
        if "MP" in v:
            mp=first_int(v)
            if mp and mp>=8:
                camera=mp
                break

    #ram & storage
    ram,storage=ram_storage(specs.get("internal",""))

    #price
    price_text=None
    price_tag=soup.select_one("[data-spec='price']") 
    if price_tag:
        price_text = price_tag.get_text(" ", strip=True)
    if not price_text:
        price_text=specs.get("price")
    price=parse_price(price_text) if price_text else None

    return {
        "model_name": model_name,
        "release_date": release_date,
        "display": display,
        "battery": battery,
        "camera": camera,
        "ram": ram,
        "storage": storage,
        "price": price,
        "url": phone_url
    }

def up_phone(cursor, phone):
    cursor.execute("""
        INSERT INTO phones (
            model_name, release_date, display,
            battery, camera, ram, storage, price, url
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (model_name) DO UPDATE SET
            release_date = EXCLUDED.release_date,
            display      = EXCLUDED.display,
            battery      = EXCLUDED.battery,
            camera       = EXCLUDED.camera,
            ram          = EXCLUDED.ram,
            storage      = EXCLUDED.storage,
            price        = EXCLUDED.price,
            url          = EXCLUDED.url
    """, (
        phone["model_name"],
        phone["release_date"],
        phone["display"],
        phone["battery"],
        phone["camera"],
        phone["ram"],
        phone["storage"],
        phone["price"],
        phone["url"],
    ))
    
def main(limit=30):
    links = phone_link(limit=limit, delay=1.2)
    print(f"found {len(links)} phone links")

    conn = get_connection()
    cursor = conn.cursor()

    saved = 0
    for i, url in enumerate(links, start=1):
        try:
            phone = phone_details(url)
            if not phone["model_name"]:
                print(f"[{i}] Skipped (no name): {url}")
                continue

            up_phone(cursor, phone)
            conn.commit()
            saved += 1

            print(f"[{i}] Saved: {phone['model_name']} | battery={phone['battery']} | camera={phone['camera']} | price={phone['price']}")
            time.sleep(1.2)

        except Exception as e:
            try:
                if conn and conn.closed == 0:
                    conn.rollback()
            except:
                pass
            print(f"[{i}] ERROR: {url} -> {e}")
            time.sleep(2)

    #  close AFTER loop finishes
    cursor.close()
    conn.close()
    print(f"Saved {saved} phones")
if __name__=="__main__":
    main(limit=30)
    