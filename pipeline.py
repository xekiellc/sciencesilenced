#!/usr/bin/env python3
import os, json, time, re, hashlib, feedparser
from datetime import datetime, timezone, timedelta
import requests
import anthropic

NEWSAPI_KEY   = os.environ['NEWSAPI_KEY']
ANTHROPIC_KEY = os.environ['ANTHROPIC_API_KEY']
NEWS_JSON     = 'news.json'
PODS_JSON     = 'podcasts.json'
MAX_ARTICLES  = 30
MAX_AGE_DAYS  = 14
MODEL         = 'claude-sonnet-4-20250514'

NEWS_QUERIES = [
    'suppressed medical research',
    'retracted study pharma',
    'NIH grant denied research',
    'FDA suppressed data clinical trial',
    'pharmaceutical fraud buried study',
    'Fauci NIH corruption',
    'medical whistleblower',
    'Alzheimer amyloid fraud',
    'nutrition science suppressed',
    'psychiatric medication harm study',
    'replication crisis medicine',
    'medical journal retraction fraud',
    'VAERS adverse event',
    'cancer metabolic therapy',
    'longevity research rapamycin metformin',
]

YOUTUBE_FEEDS = [
    'https://www.youtube.com/feeds/videos.xml?channel_id=UCnUYZLuoy1rq1aVMwx4aTzw',
    'https://www.youtube.com/feeds/videos.xml?channel_id=UC8kGsMa0LygSX9nkBcBH1Sg',
    'https://www.youtube.com/feeds/videos.xml?channel_id=UCj-z3B2-P7VvzMKDpAMBc4g',
    'https://www.youtube.com/feeds/videos.xml?channel_id=UCs9Gla2msTUNWi4kLkBM5OA',
]

ALT_FEEDS = [
    'https://brownstone.org/feed/',
    'https://www.thefp.com/feed',
]

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def load_existing(path):
    try:
        with open(path) as f:
            data = json.load(f)
            return data.get('articles', data) if isinstance(data, dict) else data
    except:
        return []

def load_existing_pods(path):
    try:
        with open(path) as f:
            data = json.load(f)
            return data.get('items', data) if isinstance(data, dict) else data
    except:
        return []

def article_id(title):
    return hashlib.md5(title.lower().strip().encode()).hexdigest()[:12]

def fetch_newsapi(query):
    try:
        r = requests.get('https://newsapi.org/v2/everything', params={
            'q': query,
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': 10,
            'from': (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%d'),
            'apiKey': NEWSAPI_KEY,
        }, timeout=15)
        r.raise_for_status()
        return [
            {
                'title': a.get('title',''),
                'description': a.get('description',''),
                'url': a.get('url',''),
                'source': a.get('source',{}).get('name',''),
                'date': a.get('publishedAt',''),
            }
            for a in r.json().get('articles',[])
            if a.get('title') and '[Removed]' not in a.get('title','')
        ]
    except Exception as e:
        print(f'NewsAPI error ({query}): {e}')
        return []

def fetch_rss(url, label='RSS'):
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:5]:
            items.append({
                'title': entry.get('title',''),
                'description': entry.get('summary','')[:400],
                'url': entry.get('link',''),
                'source': feed.feed.get('title', label),
                'date': entry.get('published', datetime.now(timezone.utc).isoformat()),
            })
        return items
    except Exception as e:
        print(f'RSS error ({url}): {e}')
        return []

def claude_categorize(raw_articles, existing_ids):
    new_articles = [a for a in raw_articles if article_id(a['title']) not in existing_ids]
    if not new_articles:
        print('No new articles to process.')
        return []

    articles_text = '\n\n'.join([
        f"TITLE: {a['title']}\nSOURCE: {a['source']}\nURL: {a['url']}\nDESC: {a.get('description','')[:300]}"
        for a in new_articles[:25]
    ])

    prompt = f"""You are the editorial AI for ScienceSilenced.com — a site aggregating suppressed, censored, and alternative medical and scientific research. Editorial voice: confrontational, evidence-based, fiercely independent. No pharma money. No approved narratives.

Review these articles and select the 8 most relevant. For each return a JSON object.

INCLUDE articles about:
- Suppressed or retracted medical/scientific studies
- Pharma fraud, buried clinical trial data
- NIH, FDA, CDC corruption or political interference
- Whistleblowers in medicine or research
- Alternative/metabolic theories of disease
- Longevity science funded outside the system
- Nutrition science suppression
- Psychiatric medication harm or overdiagnosis
- Replication crisis in medicine
- Fauci / gain of function / lab leak
- Wellness practices with genuine scientific backing being dismissed

REJECT: mainstream pharma announcements, routine medical news, political news unrelated to science suppression.

Return this exact JSON structure for each selected article:
{{
  "title": "punchy editorial headline — confrontational, specific",
  "summary": "2-3 sentence editorial summary. Direct. Names names. States what was suppressed and the impact.",
  "source": "original source name",
  "url": "original url",
  "date": "ISO date",
  "pillar": "one of: suppressed | exposed | vindicated | uncaged",
  "category": "e.g. Pharma Fraud / NIH Capture / Metabolic Research / Nutrition Science / Psychiatry / Replication Crisis / Longevity / Whistleblower",
  "topic": "e.g. Cardiovascular / Oncology / Neurology / Mental Health / Dietary Guidelines",
  "suppression_score": 1-5
}}

Return ONLY a valid JSON array. No preamble, no markdown fences.

ARTICLES:
{articles_text}"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{'role':'user','content':prompt}]
        )
        text = response.content[0].text.strip()
        text = re.sub(r'^```json\s*','',text)
        text = re.sub(r'\s*```$','',text)
        categorized = json.loads(text)
        print(f'Claude categorized {len(categorized)} articles.')
        return categorized
    except Exception as e:
        print(f'Claude error: {e}')
        return []

def age_label(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace('Z','+00:00'))
        diff = datetime.now(timezone.utc) - dt
        if diff.total_seconds() < 3600:
            return f'{int(diff.total_seconds()//60)} min ago'
        elif diff.total_seconds() < 86400:
            return f'{int(diff.total_seconds()//3600)} hrs ago'
        elif diff.days == 1:
            return 'Yesterday'
        else:
            return f'{diff.days} days ago'
    except:
        return ''

def is_too_old(date_str):
    try:
        dt = datetime.fromisoformat(date_str.replace('Z','+00:00'))
        return (datetime.now(timezone.utc) - dt).days > MAX_AGE_DAYS
    except:
        return False

def main():
    print(f'=== ScienceSilenced Pipeline {datetime.now(timezone.utc).isoformat()} ===')

    existing_articles = load_existing(NEWS_JSON)
    existing_ids = {article_id(a['title']) for a in existing_articles}
    print(f'Existing: {len(existing_articles)} articles')

    raw = []
    for query in NEWS_QUERIES:
        raw.extend(fetch_newsapi(query))
        time.sleep(0.3)
    for feed_url in ALT_FEEDS:
        raw.extend(fetch_rss(feed_url))

    print(f'Raw fetched: {len(raw)}')

    seen = set()
    deduped = []
    for a in raw:
        key = article_id(a['title'])
        if key not in seen and key not in existing_ids:
            seen.add(key)
            deduped.append(a)

    print(f'New unique: {len(deduped)}')

    new_categorized = claude_categorize(deduped, existing_ids)
    for a in new_categorized:
        a['age'] = age_label(a.get('date',''))

    merged = new_categorized + [
        a for a in existing_articles
        if not is_too_old(a.get('date',''))
        and article_id(a['title']) not in {article_id(n['title']) for n in new_categorized}
    ]
    merged = merged[:MAX_ARTICLES]

    with open(NEWS_JSON, 'w') as f:
        json.dump({'updated': datetime.now(timezone.utc).isoformat(), 'articles': merged}, f, indent=2)
    print(f'Wrote {len(merged)} articles.')

    existing_pods = load_existing_pods(PODS_JSON)
    existing_pod_ids = {article_id(p['title']) for p in existing_pods}
    new_pods = []

    for feed_url in YOUTUBE_FEEDS:
        for item in fetch_rss(feed_url, 'YouTube'):
            pid = article_id(item['title'])
            if pid not in existing_pod_ids:
                new_pods.append({
                    'show': item['source'],
                    'title': item['title'],
                    'guest': '',
                    'type': 'video',
                    'topic': '',
                    'url': item['url'],
                    'date': item['date'],
                    'age': age_label(item['date']),
                })
                existing_pod_ids.add(pid)

    if new_pods:
        merged_pods = (new_pods + existing_pods)[:40]
        with open(PODS_JSON, 'w') as f:
            json.dump({'updated': datetime.now(timezone.utc).isoformat(), 'items': merged_pods}, f, indent=2)
        print(f'Wrote {len(merged_pods)} podcasts.')

    print('=== Done ===')

if __name__ == '__main__':
    main()
