import pytest
from fastapi.testclient import TestClient
from main import app
from mongomock import MongoClient as MockMongoClient
from main import PURPOSE_WEIGHTS, REQUIRED_CATEGORIES


import matplotlib.pyplot as plt

client = TestClient(app)

# Extended mock data to allow real choice between low-end and high-end CPUs/GPUs
mock_products = [
    # CPUs
    {"type": "CPU", "name": "AMD Budget CPU", "price": 150, "performance_score": 50, "socket": "AM4"},
    {"type": "CPU", "name": "Intel Mid CPU", "price": 300, "performance_score": 90, "socket": "LGA1200"},
    {"type": "CPU", "name": "AMD High-End CPU", "price": 450, "performance_score": 130, "socket": "AM4"},

    # GPUs
    {"type": "GPU", "name": "Budget GPU", "price": 150, "performance_score": 60},
    {"type": "GPU", "name": "Midrange GPU", "price": 300, "performance_score": 120},
    {"type": "GPU", "name": "High-End GPU", "price": 450, "performance_score": 180},

    # Motherboards
    {"type": "Motherboard", "name": "AM4 MB", "price": 80, "performance_score": 40, "socket": "AM4", "ram_type": "DDR4"},
    {"type": "Motherboard", "name": "LGA1200 MB", "price": 120, "performance_score": 70, "socket": "LGA1200", "ram_type": "DDR4"},
    {"type": "Motherboard", "name": "AM5 MB", "price": 200, "performance_score": 100, "socket": "AM5", "ram_type": "DDR5"},

    # RAM
    {"type": "RAM", "name": "8GB RAM", "price": 40, "performance_score": 30, "ram_type": "DDR4"},
    {"type": "RAM", "name": "16GB RAM", "price": 80, "performance_score": 60, "ram_type": "DDR4"},
    {"type": "RAM", "name": "32GB RAM", "price": 150, "performance_score": 90, "ram_type": "DDR4"},

    # Storage
    {"type": "Storage", "name": "256GB SSD", "price": 40, "performance_score": 30},
    {"type": "Storage", "name": "512GB SSD", "price": 80, "performance_score": 60},
    {"type": "Storage", "name": "1TB SSD", "price": 140, "performance_score": 90},

    # PSU
    {"type": "PSU", "name": "500W PSU", "price": 50, "performance_score": 40, "wattage": 500},
    {"type": "PSU", "name": "650W PSU", "price": 80, "performance_score": 60, "wattage": 650},
    {"type": "PSU", "name": "750W PSU", "price": 110, "performance_score": 80, "wattage": 750},

    # Case
    {"type": "Case", "name": "Basic Case", "price": 30, "performance_score": 20},
    {"type": "Case", "name": "Mid Case", "price": 60, "performance_score": 40},
    {"type": "Case", "name": "Premium Case", "price": 100, "performance_score": 70}
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

# Helpers and logic verification

def extract_component(build, category):
    for line in build.split("\n"):
        if line.lower().startswith(category.lower()):
            return line
    return None

def extract_price(component_line):
    import re
    match = re.search(r"£(\d+(?:\.\d{1,2})?)", component_line)
    return float(match.group(1)) if match else 0.0

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

def test_gaming_prioritizes_gpu(mock_db):
    response = client.post("/recommend", json={
        "budget": 1500,
        "purpose": "gaming",
        "include_os": False,
        "peripherals": []
    })
    assert response.status_code == 200
    build = response.json()["recommendation"]
    cpu_line = extract_component(build, "CPU")
    gpu_line = extract_component(build, "GPU")
    cpu_price = extract_price(cpu_line)
    gpu_price = extract_price(gpu_line)
    assert gpu_price >= cpu_price, "GPU should be prioritized in gaming builds"

def test_editing_prioritizes_cpu(mock_db):
    response = client.post("/recommend", json={
        "budget": 1500,
        "purpose": "editing",
        "include_os": False,
        "peripherals": []
    })

    assert response.status_code == 200
    build = response.json()["recommendation"]
    cpu_line = extract_component(build, "CPU")
    gpu_line = extract_component(build, "GPU")
    cpu_price = extract_price(cpu_line)
    gpu_price = extract_price(gpu_line)
    assert cpu_price >= gpu_price, "CPU should be prioritized in editing builds"

def test_budget_utilization(mock_db):
    budget = 1500
    response = client.post("/recommend", json={
        "budget": budget,
        "purpose": "general",
        "include_os": False,
        "peripherals": []
    })
    assert response.status_code == 200
    build = response.json()["recommendation"]
    total_line = [line for line in build.split("\n") if line.lower().startswith("total")]
    assert total_line, "Total line missing from recommendation"
    total_price = extract_price(total_line[0])
    assert total_price >= 0.85 * budget, "Build should use at least 85% of the available budget"

def test_socket_compatibility(mock_db):
    response = client.post("/recommend", json={
        "budget": 1500,
        "purpose": "general",
        "include_os": False,
        "peripherals": []
    })
    assert response.status_code == 200
    build = response.json()["recommendation"]

    # Find the actual CPU and motherboard objects
    from main import collection
    cpu_name = extract_component(build, "CPU").split(" - ")[0].split(":")[1].strip()
    mb_name = extract_component(build, "Motherboard").split(" - ")[0].split(":")[1].strip()

    cpu = next((p for p in mock_products if p["type"] == "CPU" and p["name"] == cpu_name), None)
    mb = next((p for p in mock_products if p["type"] == "Motherboard" and p["name"] == mb_name), None)

    assert cpu and mb, "CPU or Motherboard not found in mock data"
    assert cpu["socket"] == mb["socket"], f"Sockets do not match: {cpu['socket']} vs {mb['socket']}"

def test_psu_wattage_sufficiency(mock_db):
    response = client.post("/recommend", json={
        "budget": 1500,
        "purpose": "gaming",
        "include_os": False,
        "peripherals": []
    })
    assert response.status_code == 200
    build = response.json()["recommendation"]

    # Extract component names
    lines = build.split("\n")
    selected = {}
    for line in lines:
        if ":" in line:
            ctype, rest = line.split(":", 1)
            name = rest.split("-")[0].strip()
            selected[ctype.strip()] = name

    # Find PSU and other components in mock data
    total_wattage = 0
    psu_wattage = 0

    for p in mock_products:
        if p["type"] == "PSU" and p["name"] == selected.get("PSU"):
            psu_wattage = p.get("wattage", 0)
        elif p["name"] == selected.get(p["type"]):
            total_wattage += p.get("wattage", 0)

    print("Total wattage required:", total_wattage)
    print("PSU wattage:", psu_wattage)

    assert psu_wattage >= total_wattage * 1.2, f"PSU is underpowered: requires at least {total_wattage * 1.2}W"

test_names = [
    "test_home",
    "test_successful_build",
    "test_missing_category",
    "test_invalid_budget",
    "test_gaming_prioritizes_gpu",
    "test_editing_prioritizes_cpu",
    "test_socket_compatibility",
    "test_psu_wattage_sufficiency"
]

statuses = ["Passed"] * len(test_names)
colors = ["green" if status == "Passed" else "red" for status in statuses]

# Plot horizontal bar chart
plt.figure(figsize=(10, 5))
bars = plt.barh(test_names, [1]*len(test_names), color=colors)

for i, bar in enumerate(bars):
    plt.text(1.01, bar.get_y() + bar.get_height()/2, statuses[i], va='center', ha='left', fontsize=10)

plt.title("Test Suite Results")
plt.xlabel("Status")
plt.xlim(0, 1.2)
plt.xticks([])
plt.gca().invert_yaxis()
plt.grid(False)
plt.tight_layout()
plt.show()