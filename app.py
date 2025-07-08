from flask import Flask, render_template, request, session, redirect, url_for, make_response
from dotenv import load_dotenv
import openai
import os
import json
from duckduckgo_search import DDGS

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "some_secret_key")

# Create OpenAI client (new API)
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PROFILE_DIR = "profiles"
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)

def fetch_streamer_images(query, num_images=10):
    search_term = f"{query} twitch streamer photo"
    try:
        with DDGS() as ddgs:
            results = ddgs.images(search_term, max_results=20)
            seen = set()
            valid = []
            for r in results:
                url = r.get("image")
                if url and url.startswith("http") and (".jpg" in url or ".jpeg" in url) and url not in seen:
                    seen.add(url)
                    valid.append(url)
                    if len(valid) >= num_images:
                        break
            if len(valid) < num_images:
                alt_query = f"{query} twitch streamer portrait photo"
                extra = ddgs.images(alt_query, max_results=10)
                for r in extra:
                    url = r.get("image")
                    if url and url.startswith("http") and (".jpg" in url or ".jpeg" in url) and url not in seen:
                        seen.add(url)
                        valid.append(url)
                        if len(valid) >= num_images:
                            break
            return valid if valid else ["/static/default.jpg"] * num_images
    except Exception as e:
        print(f"Image fetch error: {e}")
        return ["/static/default.jpg"] * num_images

def extract_personality(text):
    prompt = f"Analyze this text and extract tone, speech behavior, and signature phrases. Remember the conversation so that you can continue where you left off:\n{text}"
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a speech analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI error (extract_personality): {e}")
        return "Casual and engaging tone."

def save_profile(name, summary):
    with open(os.path.join(PROFILE_DIR, f"{name.lower()}.json"), 'w') as f:
        json.dump({"style": summary}, f)

def load_profile(name):
    path = os.path.join(PROFILE_DIR, f"{name.lower()}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f).get("style", "")
    return ""

@app.route('/')
def home():
    session.clear()
    return render_template('index.html')

@app.route('/custom_streamer', methods=['POST'])
def custom_streamer():
    name = request.form.get("custom_name").strip()
    if not name:
        return redirect(url_for("home"))
    style = load_profile(name)
    session["streamer"] = name
    session["style"] = style
    session["history"] = []
    session["image_urls"] = fetch_streamer_images(name)
    return redirect(url_for("chat"))

@app.route('/upload_profile', methods=['GET', 'POST'])
def upload_profile():
    if request.method == "POST":
        file = request.files['profile_file']
        name = request.form['streamer_name'].strip()
        if file and name:
            content = file.read().decode("utf-8")
            summary = extract_personality(content)
            save_profile(name, summary)
            return f"✅ Profile for <strong>{name}</strong> saved.<br><a href='/'>Go Home</a>"
    return render_template('upload_profile.html')

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if "streamer" not in session:
        return redirect(url_for("home"))

    streamer = session.get("streamer", "Streamer")
    style = session.get("style", "")
    history = session.get("history", [])
    end_session = False

    if request.method == "POST":
        user_msg = request.form["message"].strip()

        if user_msg.lower() in ["end chat", "quit", "close"]:
            session.clear()
            return redirect(url_for("home"))

        if user_msg.lower() == "clear chat":
            session["history"] = []
            return redirect(url_for("chat"))

        if user_msg.lower() == "download chat":
            return redirect(url_for("download_chat"))

        if user_msg.lower() in ["exit", "goodbye"]:
            end_session = True

        try:
            system_prompt = f"""
You are the streamer {streamer}. You talk like them. 

"""
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=200,
                temperature=0.6
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI error (chat): {e}")
            reply = f"⚠️ Error: {str(e)}"

        history.append((user_msg, reply))
        session["history"] = history

    return render_template("chat.html",
                           streamer=streamer,
                           history=history,
                           image_urls=session.get("image_urls", []),
                           end_session=end_session)

@app.route('/download_chat')
def download_chat():
    if "history" not in session or not session["history"]:
        return redirect(url_for("chat"))

    streamer = session.get("streamer", "Streamer")
    chat_text = "\n".join([f"You: {u}\n{streamer}: {b}" for u, b in session["history"]])
    response = make_response(chat_text)
    response.headers["Content-Disposition"] = "attachment; filename=chat_history.txt"
    response.mimetype = "text/plain"
    return response

if __name__ == '__main__':
    app.run(debug=True)
