"""Diagnostico: imprime los campos que devuelve /api/v2/sets."""
import json, os, sys, requests

def main():
    key = os.environ.get("PPT_API_KEY")
    if not key:
        print("Falta PPT_API_KEY"); return 1
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {key}"
    r = s.get("https://www.pokemonpricetracker.com/api/v2/sets", timeout=40)
    print("HTTP", r.status_code)
    data = r.json().get("data") or []
    print("Sets devueltos:", len(data))
    if data:
        print("CAMPOS DEL PRIMER SET:")
        print(json.dumps(data[0], indent=2)[:1200])
    return 0

if __name__ == "__main__":
    sys.exit(main())
