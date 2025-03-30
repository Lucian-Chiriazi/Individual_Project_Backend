import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

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
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Connected to MongoDB and OpenAI GPT!"}

# Define request model
class RecommendationRequest(BaseModel):
    budget: float
    purpose: str
    include_os: bool = False
    peripherals: List[str] = []

@app.post("/recommend")
def get_recommendations(request: RecommendationRequest):
    if request.budget < 500 or request.budget > 10000:
        raise HTTPException(
            status_code=400,
            detail="Budget must be between £500 and £10,000"
        )
    
    try:
        # Fetch components within budget
        products = list(collection.find({"price": {"$lte": request.budget}}))

        if not products:
            raise HTTPException(status_code=404, detail="No products found within budget")

        # Format product list for GPT prompt
        product_list = "\n".join(
            [f"{p.get('name', 'Unknown')} - £{p.get('price', 0)}" for p in products]
        )


  	    
        extra_requirments = []
        if request.include_os:
            extra_requirments.append("Include an operating system (e.g., Windows).")
        if request.peripherals:
            extra_requirments.append("Include the following peripherals: " + ", ".join(request.peripherals))

        additional_note = "\n".join(extra_requirments)
        
        # Create prompt
        prompt = f"""
        You are a PC building expert. Based on the component options below, create only one PC build that is fully compatible and fits within a total budget of £{request.budget}.
        Prioritize performance and value, and aim to get as close to the full budget as possible without going over. Do not suggest more than one build. Do not provide multiple options.
        Only choose one component per category.
        Here are the available components:
        {product_list}

        {additional_note}

        Return:
        - Each selected component with its category and price
        - The total cost
        - A short explanation (optional)
        """

        # Generate recommendation using OpenAI
        response = client_openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a PC building assistant."},
                {"role": "user", "content": prompt}
            ]
        )

        gpt_recommendation = response.choices[0].message.content.strip()
        return {"recommendation": gpt_recommendation}

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
