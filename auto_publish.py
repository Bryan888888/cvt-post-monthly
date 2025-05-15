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

# 2. 使用通义平台生成英文文章和关键字
def generate_article_and_keywords(news: str) -> dict:
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ALI_ACCESS_KEY}"
    }
    prompt = f"""
    Based on the following news snippets, please create a brand-new news article based on the provided materials. The article should integrate the individual stories into one coherent narrative with smooth transitions and meaningful connections between them. It should have an engaging introduction, a well-developed body, and a thoughtful conclusion. Please use fluent, journalistic language appropriate for a news-style report.Do **not** include section labels such as "Title", "Introduction", "Body", or "Conclusion" in your output.

    Also, provide a list of keywords related to the article after the end of the article, separated by commas. Return the title and keywords in the following format:
    Title: <generated_title>
    Keywords: <keyword1>, <keyword2>, <keyword3>, ...
    
    News snippets:
    {news}
    """

    payload = {
        "model": "qwen-turbo",
        "input": {
            "prompt": prompt
        },
        "parameters": {
            "result_format": "json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        # 添加调试输出，查看完整的响应结构
        print(f"🔍 API response data: {json.dumps(data, ensure_ascii=False, indent=2)}")

        # 确保正确访问数据中的 output 字段
        output = data.get("output", {})
        
        # 从 output 中提取文本
        text = output.get("text", "")
        
        # 提取标题（通常是第一行）
        first_line = text.split("\n")[0].strip()
        title = re.sub(r"^\**\s*Title\s*:\s*", "", first_line, flags=re.IGNORECASE).strip()

        # 清洗正文中的标题行（“Title: xxx” 或直接首行标题）
        lines = text.split("\n")
        if lines and re.search(r"(?i)^(\**\s*title\s*:|^" + re.escape(title) + r")", lines[0]):
            lines = lines[1:]  # 删除首行
        text = "\n".join(lines).strip()
        
        # 提取关键词（通常在 'Keywords: ' 后）
        keywords_line = next((line for line in text.split("\n") if "keyword" in line.lower()), "")
        keywords_match = re.search(r"(?i)keywords\s*:\s*(.+)", keywords_line)
        if keywords_match:
            keywords = [kw.strip() for kw in keywords_match.group(1).split(",") if kw.strip()]
        else:
            keywords = []


        print(f"Generated Title: {title}")  # Debug print
        print(f"Keywords for image search: {keywords}")  # Debug print
        
        return title, text, keywords

    except Exception as e:
        print(f"❌ Tongyi API failed: {e}")
        return "Error: Missing or invalid news content.", "", []



# 3. 清理生成的文章并去除段落标题
def clean_article(article: str):
    # 删除段落标题，如 Introduction, Summary, Conclusion
    article = re.sub(r"^(Introduction|Summary|Conclusion|Key News Points):\s*", "", article, flags=re.IGNORECASE)
    # 去除多余的空行
    article = re.sub(r"\n{2,}", "\n\n", article)  
    # 去除前后的空格和换行
    article = article.strip()  
    
    return article

# 4. 使用 Pixabay 搜索相关图片
def fetch_image(keywords):
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
            # 添加调试输出：查看 Pixabay 返回的完整内容
            print(f"📷 Pixabay response for keyword '{keyword}': {json.dumps(data, indent=2)}")
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
        
    # 格式化标题为6号字体并加粗
    styled_title = f"<h2>{title}</h2>"
    styled_content = f"{styled_title}\n\n<div>{content}</div>"

    post = {
        "title": title,
        "content": styled_content,  # 带格式的正文
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

    title, article, keywords = generate_article_and_keywords(news_text)    
    # 检查关键词是否成功提取
    if not keywords:
        print("⚠️ No valid keywords extracted from article. Will use fallback image.")        
    image_url, credit = fetch_image(keywords)

    # Ensure the title is valid and formatted
    title = f"Daily Industry Insight - {datetime.now().strftime('%Y-%m-%d')}" if not title or title == "Untitled" else title

    # Now proceed to publish
    publish_to_wp(title, article, image_url, credit)

if __name__ == "__main__":
    main()
