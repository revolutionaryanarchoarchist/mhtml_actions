import asyncio
import os
import re
import argparse
from pyppeteer import launch
from urllib.parse import urlparse

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)

async def save_mhtml(url: str, output_file: str):
    browser = await launch(headless=True, args=['--no-sandbox'])
    page = await browser.newPage()
    await page.goto(url, waitUntil='networkidle0')
    mhtml_data = await page._client.send('Page.captureSnapshot', {})
    with open(output_file, 'wb') as f:
        f.write(mhtml_data['data'].encode())
    await browser.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()

    base_name = sanitize_filename(args.title)
    mhtml_filename = f"{base_name}.mhtml"
    download_dir = "download"
    os.makedirs(download_dir, exist_ok=True)
    mhtml_path = os.path.join(download_dir, mhtml_filename)

    print(f"Downloading {args.url} → {mhtml_path}")
    asyncio.run(save_mhtml(args.url, mhtml_path))
    print(f"✅ Saved {mhtml_path}")

if __name__ == "__main__":
    main()
