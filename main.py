from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
import psycopg2
import re
from database import get_connection
from fastapi.responses import HTMLResponse

app=FastAPI()
templates = Jinja2Templates(directory=".")
@app.get("/", response_class=HTMLResponse)
def home(request:Request):
    return templates.TemplateResponse("index.html", {"request": request})

def fetch_phone(name: str):
    conn = get_connection()
    cur = conn.cursor()

    # normalize user query: remove spaces, hyphens, dots, underscores
    q = re.sub(r"[\s\-\._]+", "", name).lower()

    cur.execute("""
        SELECT model_name, release_date, display, battery,
               camera, ram, storage, price
        FROM phones
        WHERE lower(regexp_replace(model_name, '[\\s\\-\\._]+', '', 'g')) ILIKE %s
        ORDER BY length(model_name) ASC
        LIMIT 1
    """, (f"%{q}%",))

    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def best_battery_under(max_price: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT model_name, battery, price
        FROM phones
        WHERE price IS NOT NULL AND battery IS NOT NULL AND price <= %s
        ORDER BY battery DESC, price ASC
        LIMIT 1
    """, (max_price,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def parse_compare(question: str):
    q = question.strip()

    # accept common typo "comapre"
    if "compare" not in q.lower() and "comapre" not in q.lower():
        return None, None

    q = re.sub(r"\b(compare|comapre)\b", "", q, flags=re.I).strip()
    q = re.sub(r"\bvs\.?\b", " and ", q, flags=re.I)

    parts = [p.strip() for p in re.split(r"\band\b", q, flags=re.I) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None

def display_inches(display_text: str):
    if not display_text:
        return None
    m = re.search(r"(\d+(\.\d+)?)\s*inches", display_text, flags=re.I)
    return f"{m.group(1)} inches" if m else None

def clean_int(x):
    return x if isinstance(x, int) else None

def compare(p1, p2):
    n1, r1, d1, b1, c1, ram1, s1, pr1 = p1
    n2, r2, d2, b2, c2, ram2, s2, pr2 = p2

    # Decide camera winner
    cam_winner = None
    if c1 and c2:
        if c1 > c2:
            cam_winner = n1
        elif c2 > c1:
            cam_winner = n2

    # Decide battery winner
    bat_winner = None
    if b1 and b2:
        if b1 > b2:
            bat_winner = n1
        elif b2 > b1:
            bat_winner = n2

    # Decide overall winner
    score1 = 0
    score2 = 0

    if cam_winner == n1:
        score1 += 1
    elif cam_winner == n2:
        score2 += 1

    if bat_winner == n1:
        score1 += 1
    elif bat_winner == n2:
        score2 += 1

    if score1 > score2:
        winner = n1
        loser = n2
    elif score2 > score1:
        winner = n2
        loser = n1
    else:
        winner = None

    # Display comparison
    display_text = "Display is similar."
    if d1 and d2 and d1 != d2:
        display_text = "Display quality differs slightly between the two models."

    # Build sentence
    if winner:
        feature_parts = []
        if cam_winner == winner:
            feature_parts.append("better camera")
        if bat_winner == winner:
            feature_parts.append("better battery life")

        feature_text = " and ".join(feature_parts) if feature_parts else "better overall performance"

        answer = (
            f"{winner} has {feature_text} than {loser}. "
            f"{display_text} "
            f"Overall, {winner} is recommended for photography and long usage."
        )
    else:
        answer = (
            f"{n1} and {n2} have similar camera and battery performance. "
            f"{display_text} "
            f"Overall, both phones are recommended depending on your preference."
        )

    return answer

@app.post("/ask", response_class=HTMLResponse)
def ask(request: Request, question: str = Form(...)):
    question = (question or "").strip()

    if not question:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "answer": "Please provide a question."}
        )

    # Best battery under budget
    if "best battery" in question.lower() and "under" in question.lower():
        m = re.search(r"under\s*\$?\s*(\d+)", question.lower())
        if m:
            budget = int(m.group(1))
            row = best_battery_under(budget)
            if row:
                name, bat, price = row
                ans = f"Best battery under ${budget}: {name} ({bat}mAh) price ${price}."
            else:
                ans = "No phone found under that budget."

            return templates.TemplateResponse("index.html", {"request": request, "answer": ans})

    # Compare two models
    a, b = parse_compare(question)
    if a and b:
        p1 = fetch_phone(a)
        p2 = fetch_phone(b)
        if not p1 or not p2:
            ans = "One or both phones not found in DB."
        else:
            ans = compare(p1, p2)

        return templates.TemplateResponse("index.html", {"request": request, "answer": ans})

    # Single model specs
    p = fetch_phone(question)
    if p:
        name, release, disp, bat, cam, ram, storage, price = p
        ans = (
            f"{name} released {release} has {disp}, {bat}mAh battery, "
            f"{cam}MP camera, {ram}GB RAM, {storage}GB storage, price ${price}."
        )
        return templates.TemplateResponse("index.html", {"request": request, "answer": ans})

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "answer": "Phone not found. Try exact model name."}
    )

