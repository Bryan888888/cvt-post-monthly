import os, requests, time, json, random, re
from datetime import datetime
from urllib.parse import urljoin

# 载入 Secrets
NEWS_API_KEY     = os.environ["NEWS_API_KEY"]
NEWS_API_KEY_2   = os.environ["NEWS_API_KEY_2"]
CURR_API_KEY     = os.environ["CURR_API_KEY"]
ALI_ACCESS_KEY   = os.environ["ALI_ACCESS_KEY"]
PIXABAY_API_KEY  = os.environ["PIXABAY_API_KEY"]
WP_BASE_URL      = os.environ["WORDPRESS_BASE_URL"]
WP_USER          = os.environ["WORDPRESS_USERNAME"]
WP_APP_PASS      = os.environ["WORDPRESS_APPLICATION_PASSWORD"]

# 默认图片和 media_id（用于找不到匹配图片时的替代方案）
DEFAULT_IMAGE_URL = "https://example.com/default-image.jpg"
DEFAULT_MEDIA_ID = 12345

# 1. 使用 News API 抓取最新行业新闻
def fetch_top_news():
    keywords = ["sewing", "stitching", "fashion", "aramid"]
    headers = {"User-Agent": "Mozilla/5.0"}
    api_keys = [k for k in [os.getenv("NEWS_API_KEY"), os.getenv("NEWS_API_KEY_2")] if k]

    for keyword in keywords:
        for api_key in api_keys:
            print(f"🔍 Trying keyword: {keyword} with API key ending in ...{api_key[-4:]}")
            try:
                resp = requests.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "apiKey": api_key,
                        "q": keyword,
                        "language": "en",
                        "pageSize": 3,
                        "sortBy": "publishedAt"
                    },
                    headers=headers
                )
                if resp.status_code == 429:
                    print("⚠️ Rate limited, switching API Key or waiting...")
                    time.sleep(10)
                    continue
                resp.raise_for_status()
                articles = resp.json().get("articles", [])
                if articles:
                    return [f"{a['title']}: {a.get('description', '')}" for a in articles]
            except Exception as e:
                print(f"❌ Failed to fetch news for keyword '{keyword}': {e}")
            time.sleep(5)
    return []

# 2. 使用通义平台生成英文文章
def generate_article(news: str) -> str:
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ALI_ACCESS_KEY}"
    }
    prompt = f"""Please write an English article based on the following news snippets:\n\n{news}\n\nRequirements:\n1. Concise and well-structured.\n2. Summarize the key news points.\n3. Add a brief intro and conclusion."""

    payload = {
        "model": "qwen-turbo",
        "input": {
            "prompt": prompt
        },
        "parameters": {
            "result_format": "text"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("output", {}).get("text", "No valid content returned.")
    except Exception as e:
        print(f"❌ Tongyi API failed: {e}")
        return "Error: Missing or invalid news content."

# 3. 提取英文关键词
def extract_keywords(news_list, max_keywords=3):
    text = " ".join(news_list)
    words = re.findall(r'\b\w{5,}\b', text)
    common_words = {"technology", "market", "latest", "update", "industry", "report", "global"}
    keywords = [w.lower() for w in words if w.lower() not in common_words]
    unique_keywords = list(set(keywords))
    selected = unique_keywords[:max_keywords] or ["technology"]
    print(f"🧠 Keywords for image search: {selected}")
    return selected

# 4. 使用 Pixabay 搜索相关图片
def fetch_image(news_list):
    keywords = extract_keywords(news_list)
    for keyword in keywords:
        try:
            resp = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": PIXABAY_API_KEY,
                    "q": keyword,
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "safesearch": "true",
                    "per_page": 10
                }
            )
            data = resp.json()
            hits = data.get("hits", [])
            if hits:
                image = random.choice(hits)
                return image["largeImageURL"], image["user"]
        except Exception as e:
            print(f"⚠️ Failed to fetch image for '{keyword}': {e}")
    print("⚠️ No images found, using default.")
    return DEFAULT_IMAGE_URL, "Pixabay"

# 5. 发布文章到 WordPress
def publish_to_wp(title, content, image_url, image_credit):
    media_id = DEFAULT_MEDIA_ID
    uploaded_image_url = image_url

    try:
        image_data = requests.get(image_url).content
        filename = "cover.jpg"

        media_response = requests.post(
            urljoin(WP_BASE_URL, "/wp-json/wp/v2/media"),
            auth=(WP_USER, WP_APP_PASS),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "image/jpeg"
            },
            data=image_data
        )
        media_response.raise_for_status()
        media_json = media_response.json()
        media_id = media_json.get("id", DEFAULT_MEDIA_ID)
        uploaded_image_url = media_json.get("source_url", image_url)
    except Exception as e:
        print(f"⚠️ Image upload failed, using default image: {e}")

    image_tag = f'<img src="{uploaded_image_url}" alt="Cover"/><p><em>Image by {image_credit} on Pixabay</em></p>'

    post = {
        "title": title,
        "content": f"{image_tag}<div>{content}</div>",
        "status": "publish",
        "categories": [387],  # 你的 WordPress 分类 ID
        "excerpt": content[:100] + "…",
        "featured_media": media_id
    }
    
    try:
        r = requests.post(
            urljoin(WP_BASE_URL, "/wp-json/wp/v2/posts"),
            auth=(WP_USER, WP_APP_PASS),
            headers={"Content-Type": "application/json"},
            json=post
        )
        r.raise_for_status()
        print("✅ Article published:", json.dumps(r.json(), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"❌ Failed to publish article: {e}")

# 主执行函数
def main():
    news_list = fetch_top_news()
    print("📰 News fetched:", news_list)

    if not news_list:
        print("⚠️ No news found, using fallback content.")
        news_list = ["No significant news today."]

    news_text = "\n".join(news_list)

    article = generate_article(news_text)
    image_url, credit = fetch_image(news_list)

    title = f"Daily Industry Insight - {datetime.now().strftime('%Y-%m-%d')}"
    publish_to_wp(title, article, image_url, credit)

if __name__ == "__main__":
    main()
