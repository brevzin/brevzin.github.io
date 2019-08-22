import datetime
import os
import re
import sys

post = sys.argv[1]
parts = re.match('_posts/(\d{4})-(\d{2})-(\d{2})-(?P<title>.*).md', post)
parts = parts.groupdict()
today = datetime.datetime.today()
new_post = f'_posts/{today.strftime("%Y-%m-%d")}-{parts["title"]}.md'

os.rename(post, new_post)
