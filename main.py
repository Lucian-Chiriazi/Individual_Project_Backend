import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
from typing import List
from openai import OpenAI
from dotenv import load_dotenv
from itertools import product
from collections import defaultdict

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# Connect to MongoDB
client_mongodb = MongoClient(MONGO_URI)
db = client_mongodb[MONGO_DB_NAME]
collection = db["components"]

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RecommendationRequest(BaseModel):
    budget: float
    purpose: str
    include_os: bool = False
    peripherals: List[str] = []

PURPOSE_WEIGHTS = {
    "gaming": {"CPU": 0.3, "GPU": 0.5, "RAM": 0.1, "Storage": 0.1},
    "editing": {"CPU": 0.4, "GPU": 0.2, "RAM": 0.2, "Storage": 0.2},
    "general": {"CPU": 0.3, "GPU": 0.2, "RAM": 0.2, "Storage": 0.3},
}

REQUIRED_CATEGORIES = ["CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case"]

def is_compatible(build):
    cpu = next((c for c in build if c['type'] == "CPU"), None)
    motherboard = next((c for c in build if c['type'] == "Motherboard"), None)
    ram = next((c for c in build if c['type'] == "RAM"), None)
    psu = next((c for c in build if c['type'] == "PSU"), None)

    if not all([cpu, motherboard, ram, psu]):
        return False
    if cpu.get("socket") != motherboard.get("socket"):
        return False
    if ram.get("ram_type") != motherboard.get("ram_type"):
        return False
    return True

def score_build(build, purpose):
    weights = PURPOSE_WEIGHTS.get(purpose.lower(), PURPOSE_WEIGHTS["general"])
    score = 0.0
    for component in build:
        comp_type = component["type"]
        perf = component.get("performance_score", 0)
        weight = weights.get(comp_type, 0)
        score += perf * weight
    return score

def generate_best_build(products, budget, purpose, include_os, peripherals=[]):
    grouped = defaultdict(list)
    for p in products:
        grouped[p["type"]].append(p)

    optional_items = []
    for periph in peripherals:
        optional_items += [p for p in grouped[periph.capitalize()]]

    for category in REQUIRED_CATEGORIES:
        if not grouped[category]:
            print(f"Missing category: {category}")
            return None

    limited = {cat: sorted(grouped[cat], key=lambda x: x["performance_score"], reverse=True)[:3] for cat in REQUIRED_CATEGORIES}

    combos = product(*[limited[cat] for cat in REQUIRED_CATEGORIES])
    best_score = -1
    best_build = None

    for combo in combos:
        build = list(combo) + optional_items
        if not is_compatible(build):
            continue
        total_price = sum(p["price"] for p in build)
        if total_price > budget:
            continue
        score = score_build(build, purpose)
        if score > best_score:
            best_score = score
            best_build = build

    # Debugging code for build generation
    if not best_build:
        print("No compatible build found. Debug info:")
        print("Budget:", budget)
        print("Purpose:", purpose)
        print("Components per category:", {k: len(v) for k, v in grouped.items()})
        print("Operating system included:", include_os)

    return best_build

def format_build(build):
    lines = []
    total = 0
    for comp in build:
        lines.append(f"{comp['type']}: {comp['name']} - £{comp['price']}")
        total += comp["price"]
    lines.append(f"Total: £{total:.2f}")
    return "\n".join(lines)

def call_openai_description(build, purpose, selected_peripherals, include_os):
    component_lines = [f"{item['type']}: {item['name']} - £{item['price']}" for item in build]
    build_text = "\n".join(component_lines)

    system_message = (
        "You are a PC building assistant. Only suggest peripherals the user specifically requested. "
        "If asked, recommend specific product models by name. Be concise and focused."
    )

    peripherals_text = ", ".join(selected_peripherals) if selected_peripherals else "None"
    os_text = "requested" if include_os else "not requested"

    user_prompt = f"""
    You are a PC building expert. Here is a PC build intended for {purpose}.
    Explain the build in a friendly way to a non-technical user.

    Only recommend peripherals that the user specifically asked for. Do not suggest unrequested items.
    If the user requested an operating system, include one in the build.

    Build:
    {build_text}

    The user has {os_text} an operating system. Please recommend one if requested.
    Requested peripherals: {peripherals_text}

    Respond with:
    1. A short paragraph describing the build's strengths.
    2. If peripherals were requested, suggest specific models for only those.
    3. A recommended operating system if requested.
    """

    response = client_openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt}
        ]
    )

    return response.choices[0].message.content.strip()

@app.get("/")
def home():
    return {"message": "Connected to MongoDB and OpenAI GPT!"}

@app.post("/recommend")
def get_recommendations(request: RecommendationRequest):
    if request.budget < 500 or request.budget > 10000:
        raise HTTPException(status_code=400, detail="Budget must be between £500 and £10,000")

    try:
        products = list(collection.find({"price": {"$lte": request.budget}}))

        # Debugging code for product loading
        print("Loaded", len(products), "products under £", request.budget)

        if not products:
            raise HTTPException(status_code=404, detail="No products found within budget")

        best_build = generate_best_build(
            products,
            budget=request.budget,
            purpose=request.purpose,
            include_os=request.include_os,
            peripherals=request.peripherals
        )

        if not best_build:
            raise HTTPException(status_code=404, detail="No compatible build found")

        description = call_openai_description(
            build=best_build,
            purpose=request.purpose,
            selected_peripherals=request.peripherals,
            include_os=request.include_os
        )

        return {
            "recommendation": format_build(best_build),
            "description": description
        }

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
