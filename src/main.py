from src.load.mysql_loader import load
from src.scraper.amazon import scrape


def main():
    products = scrape()
    print(f"Scraped {len(products)} products")

    if not products:
        raise SystemExit("No products scraped, nothing to load")

    load(products)
    print("Load finished")


if __name__ == "__main__":
    main()
