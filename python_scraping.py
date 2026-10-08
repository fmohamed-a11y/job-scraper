import argparse
import csv
import json
from urllib.parse import quote_plus, urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TIME_FILTERS = {"day": "r86400", "week": "r604800", "month": "r2592000"}
INTERNSHIP_LEVEL = "1"  # Internship experience  level 


def build_url(keyword, location, posted, internships_only):
    url = (
        "https://www.linkedin.com/jobs/search"
        f"?keywords={quote_plus(keyword)}"
        f"&location={quote_plus(location)}"
        f"&f_TPR={TIME_FILTERS[posted]}"
    )
    if internships_only:
        url += f"&f_E={INTERNSHIP_LEVEL}"
    return url


def clean_link(href):
    if not href:
        return ""
    parts = urlsplit(href)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def scrape_keyword(page, keyword, args):
    url = build_url(keyword, args.location, args.posted, args.internships)
    print(f"[+] {keyword!r} -> {url}")
    page.goto(url, wait_until="domcontentloaded")

    try:
        page.wait_for_selector("ul.jobs-search__results-list li", timeout=15000)
    except PWTimeout:
        print("    no results (or LinkedIn showed a sign-in wall) - try --show")
        return []

    # LinkedIn here will loads more results as i scroll down 
    for _ in range(args.scrolls):
        page.mouse.wheel(0, 6000)
        page.wait_for_timeout(1500)
        more = page.query_selector("button.infinite-scroller__show-more-button")
        if more and more.is_visible():
            more.click()
            page.wait_for_timeout(1500)

    jobs = []
    for card in page.query_selector_all("ul.jobs-search__results-list li"):
        def text(selector):
            el = card.query_selector(selector)
            return el.inner_text().strip() if el else ""

        link_el = card.query_selector("a.base-card__full-link")
        time_el = card.query_selector("time")
        jobs.append({
            "keyword": keyword,
            "title": text("h3.base-search-card__title"),
            "company": text("h4.base-search-card__subtitle"),
            "location": text("span.job-search-card__location"),
            "posted": time_el.get_attribute("datetime") if time_el else "",
            "link": clean_link(link_el.get_attribute("href") if link_el else ""),
            "source": "LinkedIn",
        })
    print(f"    found {len(jobs)} listings")
    return jobs


def save_csv(rows, path):
    fields = ["keyword", "title", "company", "location", "posted", "link", "source"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def main():
    p = argparse.ArgumentParser(description="Scrape LinkedIn job/internship listings")
    p.add_argument("keywords", nargs="+", help='e.g. "software intern" "data analyst"')
    p.add_argument("-l", "--location", default="Remote", help='e.g. "Rwanda", "Kigali", "Remote"')
    p.add_argument("-p", "--posted", choices=TIME_FILTERS, default="week")
    p.add_argument("-i", "--internships", action="store_true", help="internship level only")
    p.add_argument("-s", "--scrolls", type=int, default=5, help="more scrolls = more results")
    p.add_argument("-o", "--output", default="jobs", help="file name without extension")
    p.add_argument("--show", action="store_true", help="show the browser window")
    args = p.parse_args()

    all_jobs, seen = [], set()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.show)
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36")
        )
        for kw in args.keywords:
            for job in scrape_keyword(page, kw, args):
                if job["link"] and job["link"] not in seen:
                    seen.add(job["link"])
                    all_jobs.append(job)
            page.wait_for_timeout(3000)  # be polite between searches
        browser.close()

    save_csv(all_jobs, f"{args.output}.csv")
    save_json(all_jobs, f"{args.output}.json")
    print(f"[done] {len(all_jobs)} unique listings saved to {args.output}.csv and {args.output}.json")


if __name__ == "__main__":
    main()