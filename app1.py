import matplotlib
matplotlib.use('Agg')  # Use a non-GUI backend for Matplotlib

from flask import Flask, render_template, request, jsonify
import pathlib
import csv
import emoji
import pandas as pd
from instaloader import ConnectionException, Instaloader, Post
from sqlite3 import connect
from os.path import expanduser
from glob import glob
import os
import time
from deep_translator import GoogleTranslator  # Import Deep Translator

app = Flask(__name__)

# Set up path to Firefox cookies
path_to_firefox_cookies = r"C:\Users\deepika\AppData\Roaming\Mozilla\Firefox\Profiles\ap61719b.default-release\cookies.sqlite"

# Ensure the cookies file exists
if not os.path.exists(path_to_firefox_cookies):
    raise SystemExit(f"Error: Firefox cookies file not found at {path_to_firefox_cookies}")

FIREFOXCOOKIEFILE = glob(expanduser(path_to_firefox_cookies))[0]

# Initialize Instaloader
instaloader = Instaloader(max_connection_attempts=1)

# Get cookies for Instagram
instaloader.context._session.cookies.update(
    connect(FIREFOXCOOKIEFILE).execute("SELECT name, value FROM moz_cookies WHERE host='.instagram.com'"))

# Check connection
try:
    username = instaloader.test_login()
    if not username:
        raise ConnectionException()
except ConnectionException:
    raise SystemExit("Cookie import failed. Are you logged in successfully in Firefox?")

instaloader.context.username = username
instaloader.save_session_to_file()

# Initialize Instagram scraper
instagram = Instaloader(download_pictures=False, download_videos=False,
                        download_video_thumbnails=False, save_metadata=False, max_connection_attempts=0)
instagram.load_session_from_file(username)

# Function to translate text to English
def translate_to_english(text):
    try:
        translated_text = GoogleTranslator(source='auto', target='en').translate(text)
        return translated_text
    except Exception as e:
        return text  # Return original text if translation fails

# Function to scrape data
def scrape_data(shortcode):
    """
    Scrapes Instagram comments for a given post shortcode.
    """
    try:
        post = Post.from_shortcode(instagram.context, shortcode)
    except Exception as e:
        return None, None, None, f"Error fetching post data: {e}"

    output_path = pathlib.Path('post_data')
    output_path.mkdir(exist_ok=True)  # Create directory if it doesn't exist
    csv_name = output_path / f"{shortcode}.csv"

    field_names = ["post_shortcode", "commenter_username", "comment_text", "comment_likes"]

    post_description = translate_to_english(post.caption) if post.caption else ""

    with open(csv_name, "w", encoding="utf-8", newline='') as post_file:
        post_writer = csv.DictWriter(post_file, fieldnames=field_names)
        post_writer.writeheader()

        for x in post.get_comments():
            comment_text = (emoji.demojize(x.text)).encode('utf-8', errors='ignore').decode() if x.text else ""
            translated_comment = translate_to_english(comment_text)  # Translate comment to English
            
            post_info = {
                "post_shortcode": post.shortcode,
                "commenter_username": x.owner.username if x.owner else "Unknown",
                "comment_text": translated_comment,
                "comment_likes": x.likes_count
            }
            post_writer.writerow(post_info)

    return csv_name, post_description, post.comments, None

# Function to perform sentiment analysis
def analyze_sentiment(csv_file):
    df = pd.read_csv(csv_file)
    df['comment_text'] = df['comment_text'].fillna("")

    def get_polarity(text):
        from textblob import TextBlob
        return TextBlob(str(text)).sentiment.polarity

    df['text_polarity'] = df['comment_text'].apply(get_polarity)
    df['sentiment'] = pd.cut(df['text_polarity'], [-1, -0.0000000001, 0.0000000001, 1], labels=["Negative", "Neutral", "Positive"])

    positive = df[df['sentiment'] == "Positive"].shape[0]
    neutral = df[df['sentiment'] == "Neutral"].shape[0]
    negative = df[df['sentiment'] == "Negative"].shape[0]

    return positive, neutral, negative

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        shortcode = request.form["shortcode"]
        time.sleep(2)  # Simulate processing delay

        csv_file, post_description, total_comments, error = scrape_data(shortcode)
        if error:
            return render_template("home.html", error=error)

        positive, neutral, negative = analyze_sentiment(csv_file)

        return jsonify({
            "post_description": post_description,
            "total_comments": total_comments,
            "positive": positive,
            "neutral": neutral,
            "negative": negative
        })

    return render_template("home.html")

if __name__ == "__main__":
    app.run(debug=True)
