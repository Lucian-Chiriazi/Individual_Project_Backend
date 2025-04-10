
import pytest
from fastapi.testclient import TestClient
from main import app
from mongomock import MongoClient as MockMongoClient
from main import generate_best_build, PURPOSE_WEIGHTS, REQUIRED_CATEGORIES
from collections import defaultdict

client = TestClient(app)

# Sample mock data for testing
mock_products = [
    {"type": "CPU", "name": "Test CPU", "price": 180, "performance_score": 90, "socket": "AM4"},
    {"type": "Motherboard", "name": "Test MB", "price": 120, "performance_score": 80, "socket": "AM4", "ram_type": "DDR4"},
    {"type": "RAM", "name": "Test RAM", "price": 70, "performance_score": 60, "ram_type": "DDR4"},
    {"type": "GPU", "name": "Test GPU", "price": 400, "performance_score": 200},
    {"type": "Storage", "name": "Test SSD", "price": 100, "performance_score": 70},
    {"type": "PSU", "name": "Test PSU", "price": 80, "performance_score": 60, "wattage": 600},
    {"type": "Case", "name": "Test Case", "price": 60, "performance_score": 50},
]

@pytest.fixture
def mock_db(monkeypatch):
    class MockCollection:
        def find(self, query):
            return [p for p in mock_products if p["price"] <= query["price"]["$lte"]]

    class MockDB:
        def __getitem__(self, name):
            return MockCollection()

    class MockClient:
        def __getitem__(self, name):
            return MockDB()

    monkeypatch.setattr("main.client_mongodb", MockClient())
    monkeypatch.setattr("main.db", MockDB())
    monkeypatch.setattr("main.collection", MockCollection())

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"].startswith("Connected")

def test_successful_build(mock_db):
    response = client.post("/recommend", json={
        "budget": 1200,
        "purpose": "gaming",
        "include_os": True,
        "peripherals": ["keyboard", "mouse"]
    })
    assert response.status_code == 200
    data = response.json()
    assert "recommendation" in data
    assert "description" in data
    assert "CPU" in data["recommendation"]
    assert "GPU" in data["recommendation"]

def test_missing_category(mock_db, monkeypatch):
    # Remove GPU to simulate missing required category
    monkeypatch.setattr("main.collection.find", lambda q: [p for p in mock_products if p["type"] != "GPU"])
    response = client.post("/recommend", json={
        "budget": 1200,
        "purpose": "gaming",
        "include_os": False,
        "peripherals": []
    })
    assert response.status_code == 404

def test_invalid_budget():
    response = client.post("/recommend", json={
        "budget": 300,
        "purpose": "gaming",
        "include_os": False,
        "peripherals": []
    })
    assert response.status_code == 400
    assert "Budget must be between" in response.json()["detail"]
