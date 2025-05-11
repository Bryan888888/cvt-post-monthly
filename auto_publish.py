import os, requests, time, json, random, re
from datetime import datetime
from urllib.parse import urljoin

# 载入 Secrets
NEWS_API_KEY     = os.environ["NEWS_API_KEY"]  # 留作备用
CURR_API_KEY     = os.environ["CURR_API_KEY"]  # Currents API Key
ALI_ACCESS_KEY   = os.environ["ALI_ACCESS_KEY"]
PIXABAY_API_KEY  = os.environ["PIXABAY_API_KEY"]
WP_BASE_URL      = os.environ["WORDPRESS_BASE_URL"]
WP_USER          = os.environ["WORDPRESS_USERNAME"]
WP_APP_PASS      = os.environ["WORDPRESS_APPLICATION_PASSWORD"]

# 默认图片 URL 和 media_id
DEFAULT_IMAGE_URL = "https://example.com/default-image.jpg"  # 替换为你想要的默认图片 URL
DEFAULT_MEDIA_ID = 12345  # 替换为你网站的默认媒体 ID

# 1. 使用 Currents API 抓取最新行业新闻
def fetch_top_news():
    keywords = ["sewing", "stitching", "fashion", "aramid"]
    for keyword in keywords:
        try:
            print(f"🔍 正在尝试关键词：{keyword}")
            resp = requests.get(
                "https://api.currentsapi.services/v1/search",
                params={
                    "apiKey": os.environ["CURR_API_KEY"],
                    "query": keyword,
                    "language": "en",
                    "page_size": 3,
                    "sort_by": "published"
                },
                timeout=10
            )
            resp.raise_for_status()
            articles = resp.json().get("news", [])
            if articles:
                return [f"{a['title']}: {a.get('description', '')}" for a in articles]
        except Exception as e:
            print(f"⚠️ 获取关键词“{keyword}”的新闻失败：{e}")
            time.sleep(2)
    print("⚠️ 所有关键词均获取失败，返回空列表。")
    return []


# 2. 用通义平台生成文章（使用 requests）
def generate_article(news: str) -> str:
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ.get('ALI_ACCESS_KEY')}"
    }
    prompt = f"""请基于以下英文新闻内容，撰写一篇中文行业资讯摘要文章：\n\n{news}\n\n要求：\n1. 中文撰写，简洁有条理；\n2. 包括主要新闻点，不要逐条翻译；\n3. 添加适当的过渡和总结。\n\n谢谢！"""

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
        return data.get("output", {}).get("text", "通义未返回有效内容。")
    except Exception as e:
        print(f"❌ 通义 API 调用失败：{e}")
        return "很抱歉，您提供的内容中缺少具体的新闻信息。请您补充完整的新闻素材，以便我为您撰写一篇简洁的中文文章。谢谢！"

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
    news_list = fetch_top_news()
    print("📰 获取新闻内容：", news_list)

    if not news_list:
        print("⚠️ 未获取到任何新闻内容，将使用默认内容。")
        news_list = ["今天暂无重要新闻。"]

    news_text = "\n".join(news_list)
    print("📨 提交给通义的内容：", news_text)

    # 调用通义生成文章
    article = generate_article(news_text)

    # 获取配图及署名
    image_url, credit = fetch_image(news_list)

    # 构造文章标题
    title = f"每日行业洞察 - {datetime.now().strftime('%Y-%m-%d')}"

    # 发布至 WordPress
    publish_to_wp(title, article, image_url, credit)


if __name__ == "__main__":
    main()
