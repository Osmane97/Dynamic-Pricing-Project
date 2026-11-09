from time import sleep

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
import datetime

from src import config

URL = 'https://www.amazon.co.uk/'
MAX_PAGES = 5


def create_driver():
    chrome_option = webdriver.ChromeOptions()
    chrome_option.add_argument('--no-sandbox')  # Required for CI
    chrome_option.add_argument('--disable-dev-shm-usage')  # Fixes shared memory issues
    return webdriver.Chrome(options=chrome_option)


def open_listing_page(driver):
    driver.get(URL)

    wait = WebDriverWait(driver, 10)  # 10 seconds timeout

    # Continue shopping button appears sometimes, wait until clickable
    try:
        continue_shopping = wait.until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div/div[1]/div[3]/div/div/form/div/div/span/span/button'))
        )
        continue_shopping.click()
    except (TimeoutException, NoSuchElementException):
        pass

    # Decline cookies if present
    try:
        decline_cookies = wait.until(
            EC.element_to_be_clickable((By.ID, 'sp-cc-rejectall-link'))
        )
        decline_cookies.click()
    except (TimeoutException, NoSuchElementException):
        pass

    driver.get(config.LISTING_URL)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"]')))
    except TimeoutException:
        print("Listing page did not load. URL:", driver.current_url)
        print("Page title:", driver.title)
        raise


# Number of words for each key, purpose to split the string of each detail from there key
# Amazon's label for each spec. Some products use a different label for the same thing
SPEC_LABELS = {
    'Brand': ['brand name', 'brand'],
    'Series': ['gpu series', 'series'],
    'Item model number': ['model number', 'item model number'],
    'Resolution': ['display maximum resolution', 'maximum display resolution', 'resolution'],
    'Memory Clock Speed': ['memory clock speed'],
    'Graphics Coprocessor': ['graphics coprocessor'],
    'Graphics Chipset Brand': ['video processor', 'graphics chipset brand'],
    'Graphics RAM Type': ['graphics ram type'],
    'Graphics Card Ram Size': ['graphics card ram', 'graphics card ram size', 'graphics ram size'],
    'Product Dimensions': ['item dimensions l x w', 'product dimensions', 'item dimensions'],
    'Wattage': ['wattage'],
}


def product_information(driver):
    try:
        # Exctract review stars
        customer_reviews = float(driver.find_element(By.XPATH, '//*[@id="acrPopover"]/span[1]/a/span').text)
    except NoSuchElementException:
        customer_reviews = None
    # Getting number of reviews
    try:
        reviews_number = driver.find_element(By.ID, 'acrCustomerReviewText').text
        reviews_number = reviews_number.split(' ')
        reviews_number = int(reviews_number[0].replace(',', '').strip('()'))
    except NoSuchElementException:
        reviews_number = 0  # The product isn't rated

    # the past_month_product_bought results is at least this value
    try:
        last_month_sold = driver.find_element(By.ID, 'social-proofing-faceout-title-tk_bought').text
        last_month_sold = last_month_sold.split('+')
        last_month_sold = int(last_month_sold[0])
    except NoSuchElementException:
        last_month_sold = None

    try:
        # Get the price currency
        currency = driver.find_element(By.CLASS_NAME, 'a-price-symbol').text

        # Get the Price
        price_whole = driver.find_element(By.CLASS_NAME, 'a-price-whole').text.replace(',', '')
        price_fraction = driver.find_element(By.CLASS_NAME, 'a-price-fraction').text
        actual_price = float(price_whole + '.' + price_fraction)
    except (NoSuchElementException, ValueError):
        currency = None
        actual_price = None

    
    # Only a visible savings badge counts. Some pages have a hidden one for another offer
    discount = 0
    rrp_price = actual_price
    badges = driver.find_elements(By.CSS_SELECTOR, '#corePriceDisplay_desktop_feature_div .apex-savings-container')
    for badge in badges:
        discount_str = badge.text.replace('-', '').replace('%', '').strip()
        if discount_str.isdigit():
            discount = int(discount_str)
            break

    # The original price only appears when there's a discount
    if discount:
        basis_prices = driver.find_elements(By.CSS_SELECTOR, '#corePriceDisplay_desktop_feature_div .apex-basisprice-value .a-offscreen')
        if basis_prices:
            rrp_text = basis_prices[0].get_attribute('textContent')
            rrp_price = float(rrp_text.replace('£', '').replace(',', '').strip())


    return {
        'customer reviews': customer_reviews,
        'reviews number': reviews_number,
        'at least last month sold': last_month_sold,
        'currency': currency,
        'actual price': actual_price,
        'discount %': discount,
        'original price': rrp_price
    }

#parse = analysing, taking a messy string, then extract and clean the structured result in a dictionary
def parse_product_details(driver):
    # Read every row of Amazon's spec tables into {label: value}
    page_specs = {}
    for row in driver.find_elements(By.CSS_SELECTOR, '#prodDetails table.prodDetTable tr'):
        cells = row.find_elements(By.CSS_SELECTOR, 'th, td')
        if len(cells) == 2:
            label = cells[0].get_attribute('textContent').strip().lower()
            value = cells[1].get_attribute('textContent').replace('\u200e', '').strip()
            page_specs[label] = value

    # Pick the specs we want, using the first label that exists
    product_specs = {}
    for key, labels in SPEC_LABELS.items():
        product_specs[key] = next((page_specs[label] for label in labels if label in page_specs), 'unknown')
    return product_specs




def get_asins_on_page(driver):
    items = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
    filtered_items = [item for item in items if 'Sponsored' not in item.text and 'See options' not in item.text]
    asins = [item.get_attribute('data-asin') for item in filtered_items]
    return [asin for asin in asins if asin]  # drop empty ASINs


def collect_asins(driver):
    asins = set()  # a set ignores duplicates across pages
    wait = WebDriverWait(driver, 10)

    page_number = 1
    while page_number <= MAX_PAGES:
        # The next button loads last, so once it's here the page's products are ready
        try:
            next_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.s-pagination-next')))
        except TimeoutException:
            print(f"Page {page_number} did not finish loading, stopping here")
            break

        asins.update(get_asins_on_page(driver))

        # On the last results page the button is a disabled <span>, not a link
        if page_number == MAX_PAGES or next_button.tag_name != 'a':
            break

        next_button.click()
        wait.until(EC.staleness_of(next_button))  # the old page is gone
        page_number += 1

    return asins


def scrape_products(driver, asins):
    products = {}

    for asin in asins:
        try:
            driver.get(f"{URL}dp/{asin}")
            sleep(2)

            #getting scraping timestamp for each product
            scrape_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            #Get all product details
            product_overview = product_information(driver)
            if product_overview['actual price'] is None:
                print(f"Skipped {asin}: no price found")
                continue

            product_spec = parse_product_details(driver)

            #combine both dictionaries under the ASIN
            products[asin] = {
                'scrape time': scrape_time,
                'product overview': product_overview,
                'product specifications': product_spec
            }
        except Exception as e:
            print(f"Skipped {asin}: {type(e).__name__}: {e}")

    return products


def scrape():
    driver = create_driver()
    try:
        open_listing_page(driver)
        asins = collect_asins(driver)
        print(f"Found {len(asins)} products on the listing pages")
        return scrape_products(driver, asins)
    finally:
        driver.quit()
