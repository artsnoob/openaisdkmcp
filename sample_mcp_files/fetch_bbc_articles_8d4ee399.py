import feedparser

# Function to fetch the latest articles from the BBC RSS feed
def fetch_bbc_articles():
    # URL of the BBC RSS feed
    url = 'http://feeds.bbci.co.uk/news/rss.xml'
    try:
        # Parse the RSS feed
        feed = feedparser.parse(url)

        # Check if the feed is valid
        if feed.bozo:
            raise Exception(f'Feed is malformed: {feed.bozo_exception}')

        # Iterate through the latest articles
        articles = []
        for entry in feed.entries[:5]:  # Get only the first 5 articles
            if hasattr(entry, 'get'):
                title = entry.get('title', 'No Title Available')
                link = entry.get('link', '#')
                published = entry.get('published', entry.get('updated', 'No Date Available'))
                articles.append({'title': title, 'link': link, 'published': published})

        return articles
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    latest_articles = fetch_bbc_articles()
    for article in latest_articles:
        print(f"Title: {article['title']}, Link: {article['link']}, Published: {article['published']}")