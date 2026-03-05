import feedparser, requests, os, json
from datetime import datetime, timezone
from difflib import SequenceMatcher
from dateutil import parser

WEBHOOK = os.getenv("WECHAT_WEBHOOK")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
CACHE_FILE = "sent_cache.json"
SOURCE_FILE = "sources.json"
KEYWORDS = ["iran", "tehran", "israel", "nuclear", "sanction", "military"]

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return set(json.load(f))
    return set()

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(list(cache), f)

def is_today(entry):
    if "published" in entry:
        pub = parser.parse(entry.published)
    elif "updated" in entry:
        pub = parser.parse(entry.updated)
    else:
        return False
    return pub.date() == datetime.now(timezone.utc).date()

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

def fetch_news():
    results = []
    with open(SOURCE_FILE) as f:
        sources = json.load(f)
    for s in sources:
        feed = feedparser.parse(s["url"])
        for entry in feed.entries:
            if not is_today(entry):
                continue
            title = entry.title
            if not any(k in title.lower() for k in KEYWORDS):
                continue
            results.append({"title": title, "link": entry.link, "source": s["name"]})
    return results

def cluster_news(news):
    clusters = []
    for item in news:
        added = False
        for cluster in clusters:
            if similar(item["title"], cluster[0]["title"]) > 0.6:
                cluster.append(item)
                added = True
                break
        if not added:
            clusters.append([item])
    return clusters

def deepseek_summarize(cluster):
    titles = "\n".join([i["title"] for i in cluster])
    prompt = f"""
以下是多家媒体关于同一事件的新闻标题：
{titles}
请用中文一句话总结该事件，并标注重要性：高 / 中 / 低。
"""
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}]}
    r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data)
    result = r.json()
    return result["choices"][0]["message"]["content"]

def send_wechat(msg):
    requests.post(WEBHOOK, json={"msgtype": "text", "text": {"content": msg}})

def main():
    cache = load_cache()
    news = [n for n in fetch_news() if n["link"] not in cache]
    if not news:
        print("No new news")
        return
    clusters = cluster_news(news)
    messages = []
    for cluster in clusters[:10]:  # 只推送前10条
        summary = deepseek_summarize(cluster)
        sources = " / ".join(set([i["source"] for i in cluster]))
        link = cluster[0]["link"]
        messages.append(f"• {summary}\n来源: {sources}\n{link}")
        for item in cluster:
            cache.add(item["link"])
    save_cache(cache)
    final_msg = "【伊朗局势今日更新】\n\n" + "\n\n".join(messages)
    send_wechat(final_msg)

if __name__ == "__main__":
    main()
