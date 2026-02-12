from dotenv import load_dotenv
import os

load_dotenv()
print("DATABASE_URL =", os.getenv("DATABASE_URL"))


from app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
