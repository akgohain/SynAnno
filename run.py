from synanno import create_app
from dotenv import load_dotenv
from flask import send_from_directory


load_dotenv()  # Load environment variables from .env

# Initialize the app using the factory function
app = create_app()


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


if __name__ == "__main__":
    app.run(host=app.config["IP"], port=app.config["PORT"], debug=True)
