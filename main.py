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
    # if psu.get("wattage", 0) < sum([c.get("wattage", 0) for c in build if c.get("wattage")]):
        # return False

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

def generate_best_build(products, budget, purpose, include_os=False, peripherals=[]):
    grouped = defaultdict(list)
    for p in products:
        grouped[p["type"]].append(p)

    optional_items = []
    if include_os:
        optional_items += [p for p in grouped["Operating System"]]
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


    # Debugging - delete after
    if not best_build:
        print("No compatible build found. Debug info:")
        print("Budget:", budget)
        print("Purpose:", purpose)
        print("Components per category:", {k: len(v) for k, v in grouped.items()})

    return best_build

def format_build(build):
    lines = []
    total = 0
    for comp in build:
        lines.append(f"{comp['type']}: {comp['name']} - £{comp['price']}")
        total += comp["price"]
    lines.append(f"Total: £{total:.2f}")
    return "\n".join(lines)

def call_openai_description(build, purpose, include_peripherals):
    component_lines = [f"{item['type']}: {item['name']} - £{item['price']}" for item in build]
    build_text = "\n".join(component_lines)

    system_message = "You are a helpful PC building assistant. Only provide peripherals if the user explicitly requests them."

    user_prompt = f"""
    You are a PC building expert. Here is a PC build intended for {purpose}.
    Explain the build in a friendly way to a non-technical user.

    If the user did not request peripherals, do not suggest any peripherals or mention them in any way.

    Build:
    {build_text}

    User requested peripherals: {include_peripherals}

    Respond with:
    1. A short paragraph describing the build's strengths.
    2. Only include a list of peripherals if requested.
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
        
        # Debugging - delete after
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
            include_peripherals=bool(request.peripherals)
        )

        return {
            "recommendation": format_build(best_build),
            "description": description
        }

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
