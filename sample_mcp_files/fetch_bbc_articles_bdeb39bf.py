import feedparser

# BBC RSS Feed URL
rss_url = 'http://feeds.bbci.co.uk/news/rss.xml'

def fetch_bbc_articles():
    try:
        feed = feedparser.parse(rss_url)
        if feed.bozo:
            raise Exception(f"Feed is not valid: {feed.bozo_exception}")
        articles = []

        for entry in feed.entries:
            if hasattr(entry, 'get'):
                title = entry.get('title', 'No Title Available')
                link = entry.get('link', '#')
                published = entry.get('published', entry.get('updated', 'No Date Available'))
                articles.append({
                    'title': title,
                    'link': link,
                    'published': published
                })
        return articles
    except Exception as e:
        return str(e)

# Fetch and print the latest articles
latest_articles = fetch_bbc_articles()
for article in latest_articles:
    print(article)