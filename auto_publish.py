import os, requests, json, random, re
from datetime import datetime
from urllib.parse import urljoin

# 载入 Secrets
NEWS_API_KEY     = os.environ["NEWS_API_KEY"]
ALI_ACCESS_KEY   = os.environ["ALI_ACCESS_KEY"]
PIXABAY_API_KEY  = os.environ["PIXABAY_API_KEY"]
WP_BASE_URL      = os.environ["WORDPRESS_BASE_URL"]
WP_USER          = os.environ["WORDPRESS_USERNAME"]
WP_APP_PASS      = os.environ["WORDPRESS_APPLICATION_PASSWORD"]

# 默认图片 URL 和 media_id
DEFAULT_IMAGE_URL = "https://example.com/default-image.jpg"  # 替换为你想要的默认图片 URL
DEFAULT_MEDIA_ID = 12345  # 替换为你网站的默认媒体 ID

# 1. 抓取最新行业新闻
def fetch_top_news():
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"apiKey": NEWS_API_KEY, "category": "technology", "pageSize": 3}
    )
    data = resp.json()
    return [f"{a['title']}: {a['description']}" for a in data.get("articles", [])]

# 2. 用通义平台生成文章（使用 requests）
def generate_article(news):
    try:
        response = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            headers={
                "Authorization": f"Bearer {ALI_ACCESS_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-turbo",
                "input": {
                    "prompt": f"你是一位资深中文科技新闻撰稿人。请根据以下新闻内容撰写一篇简洁的中文文章：\n\n{news}"
                },
                "parameters": {
                    "temperature": 0.7
                }
            }
        )
        response.raise_for_status()
        result = response.json()
        text = result.get("output", {}).get("text")
        if text:
            return text
        else:
            print(f"⚠️ 未找到生成的文本内容，响应内容：{json.dumps(result, ensure_ascii=False)}")
            return "【占位内容】生成过程中发生错误，暂无法生成文章。"
    except Exception as e:
        print(f"❌ 通义 API 调用失败：{e}")
        return "【占位内容】生成过程中发生错误，暂无法生成文章。"

# 3. 提取关键词
def extract_keywords(news_list, max_keywords=3):
    text = " ".join(news_list)
    words = re.findall(r'\b\w{5,}\b', text)
    common_words = {"technology", "market", "latest", "update", "industry", "report", "global"}
    keywords = [w.lower() for w in words if w.lower() not in common_words]
    unique_keywords = list(set(keywords))
    return unique_keywords[:max_keywords] or ["technology"]

# 4. 从 Pixabay 获取图片
def fetch_image(news_list):
    keywords = extract_keywords(news_list)
    for keyword in keywords:
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
    print("⚠️ Pixabay 无法找到相关图片，使用默认图片。")
    return DEFAULT_IMAGE_URL, "Pixabay"

# 5. 发布到 WordPress
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
        print(f"⚠️ 图片上传失败，使用默认图片: {e}")

    image_tag = f'<img src="{uploaded_image_url}" alt="Cover"/><p><em>Image by {image_credit} on Pixabay</em></p>'

    post = {
        "title": title,
        "content": f"{image_tag}<div>{content}</div>",
        "status": "publish",
        "categories": [387],
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
    print("✅ WordPress 响应内容：", json.dumps(r.json(), ensure_ascii=False, indent=2))
    print("🎉 发布成功，文章 ID:", r.json().get("id"))
except Exception as e:
    print(f"❌ 发布文章失败：{e}")


# 主流程
def main():
    news = fetch_top_news()
    article = generate_article(news)
    img_url, credit = fetch_image(news)
    title = f"每日行业洞察 - {datetime.now().strftime('%Y-%m-%d')}"
    publish_to_wp(title, article, img_url, credit)

if __name__ == "__main__":
    main()
