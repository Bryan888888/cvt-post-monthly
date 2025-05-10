import os, requests, json, random, re
from datetime import datetime
from openai import OpenAI
from urllib.parse import urljoin

# 载入 Secrets
NEWS_API_KEY     = os.environ["NEWS_API_KEY"]
OPENAI_API_KEY   = os.environ["OPENAI_API_KEY"]
PIXABAY_API_KEY  = os.environ["PIXABAY_API_KEY"]
WP_BASE_URL      = os.environ["WORDPRESS_BASE_URL"]
WP_USER          = os.environ["WORDPRESS_USERNAME"]
WP_APP_PASS      = os.environ["WORDPRESS_APPLICATION_PASSWORD"]

# 1. 抓取最新行业新闻
def fetch_top_news():
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"apiKey": NEWS_API_KEY, "category": "technology", "pageSize": 3}
    )
    data = resp.json()
    return [f"{a['title']}: {a['description']}" for a in data.get("articles", [])]

# 2. 用 GPT 生成文章
def generate_article(news_list):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = (
        "根据以下行业新闻要点，写一篇 500 字左右的原创技术市场洞察文章，"
        "并结合我们产品的优势：\n" + "\n".join(news_list)
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一名资深市场分析师。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content

# 3. 从新闻中提取关键词（用于 Pixabay 图像搜索）
def extract_keywords(news_list, max_keywords=3):
    text = " ".join(news_list)
    words = re.findall(r'\b\w{5,}\b', text)  # 提取长度大于5的单词
    common_words = {"technology", "market", "latest", "update", "industry", "report", "global"}
    keywords = [w.lower() for w in words if w.lower() not in common_words]
    unique_keywords = list(set(keywords))
    return unique_keywords[:max_keywords] or ["technology"]

# 4. 获取无版权图片（Pixabay 搜索 + 随机选择）
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
    raise Exception("❌ Pixabay 无法找到与新闻匹配的图片")

# 5. 发布到 WordPress
def publish_to_wp(title, content, image_url, image_credit):
    # 5.1 上传媒体
    media = requests.post(
        urljoin(WP_BASE_URL, "/wp-json/wp/v2/media"),
        auth=(WP_USER, WP_APP_PASS),
        headers={"Content-Disposition": 'attachment; filename="cover.jpg"'},
        data=requests.get(image_url).content
    ).json()
    media_id = media["id"]

    # 5.2 发布文章
    post = {
        "title": title,
        "content": f'<img src="{media["source_url"]}" alt="Cover"/><p><em>Image by {image_credit} on Pixabay</em></p><div>{content}</div>',
        "status": "publish",
        "categories": [2],  # 修改为你的实际分类 ID
        "excerpt": content[:100] + "…"
    }
    r = requests.post(
        urljoin(WP_BASE_URL, "/wp-json/wp/v2/posts"),
        auth=(WP_USER, WP_APP_PASS),
        headers={"Content-Type": "application/json"},
        json=post
    )
    r.raise_for_status()
    print("🎉 发布成功，文章 ID:", r.json()["id"])

# 主流程
def main():
    news = fetch_top_news()
    article = generate_article(news)
    img_url, credit = fetch_image(news)
    title = f"每日行业洞察 - {datetime.now().strftime('%Y-%m-%d')}"
    publish_to_wp(title, article, img_url, credit)

if __name__ == "__main__":
    main()
