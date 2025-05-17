import feedparser

# BBC RSS Feed URL
rss_url = 'http://feeds.bbci.co.uk/news/rss.xml'

# Output Markdown file
output_file = '/Users/milanboonstra/code/openaisdkmcp_server_copy/sample_mcp_files/bbc_latest_articles.md'

def fetch_bbc_articles():
    articles_markdown = "# Latest BBC Articles\n\n"
    try:
        feed = feedparser.parse(rss_url)
        if feed.bozo:
            raise Exception(f"Feed is not valid: {feed.bozo_exception}")

        for entry in feed.entries:
            if hasattr(entry, 'get'):
                title = entry.get('title', 'No Title Available')
                link = entry.get('link', '#')
                published = entry.get('published', entry.get('updated', 'No Date Available'))
                articles_markdown += f'## {title}\n[Read more]({link})\nPublished: {published}\n\n'

        # Save to Markdown file
        with open(output_file, 'w') as file:
            file.write(articles_markdown)
        return f'Articles saved to {output_file}'
    except Exception as e:
        return str(e)

# Fetch and save the articles
result = fetch_bbc_articles()
result