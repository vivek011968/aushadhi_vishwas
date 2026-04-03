import json
import urllib.request
import urllib.parse

BASE_URL = "http://127.0.0.1:5000"

def test_verification():
    print("Testing Updated QR Verification System...")
    
    # 1. Test Genuine Sun Pharma QR
    sun_qr = "https://sun.psverify.com/21/G2KTDMHK5"
    print(f"\nScanning GENUINE Sun Pharma: {sun_qr}")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/verify/{urllib.parse.quote(sun_qr, safe='')}?format=json") as response:
            data = json.loads(response.read().decode())
            print(f"Status: {data['status']}")
            print(f"Medicine Name: {data['medicine']['name']}")
            print(f"Is External: {data['medicine'].get('is_external', False)}")
    except Exception as e:
        print(f"Error: {e}")
    
    # 2. Test COUNTERFEIT Sun Pharma QR (Correct domain, wrong ID)
    fake_sun_qr = "https://sun.psverify.com/21/FAKE-ID-999"
    print(f"\nScanning COUNTERFEIT Sun Pharma: {fake_sun_qr}")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/verify/{urllib.parse.quote(fake_sun_qr, safe='')}?format=json") as response:
            data = json.loads(response.read().decode())
            print(f"Status: {data['status']}")
            print(f"Reason: {data['reason']}")
            print(f"Expected Action: Should show 'Report Counterfeit' button in UI")
    except Exception as e:
        print(f"Error: {e}")

    # 3. Test Unknown (Non-mimicking) QR
    random_qr = "SOME-RANDOM-DATA"
    print(f"\nScanning UNKNOWN Product: {random_qr}")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/verify/{urllib.parse.quote(random_qr, safe='')}?format=json") as response:
            data = json.loads(response.read().decode())
            print(f"Status: {data['status']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_verification()
