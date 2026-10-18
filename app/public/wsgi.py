from app import create_app
import webbrowser
from waitress import serve

app = create_app()

if __name__ == "__main__":
    url = "http://127.0.0.1:5000"
    print(f"🚗 Starting WheelQ with Waitress on {url}")
    webbrowser.open(url)
    serve(app, host="127.0.0.1", port=5000)
