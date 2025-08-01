from time import sleep

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
import datetime
import mysql.connector

URL = 'https://www.amazon.co.uk/'

# Keep chrome open
chrome_option = webdriver.ChromeOptions()
#chrome_option.add_argument('--headless')  # Run in headless mode
#chrome_option.add_argument('--disable-gpu')
#chrome_option.add_argument('window-size=1920,1080')
# Optional: spoof user agent to avoid detection
# chrome_option.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
#                             'AppleWebKit/537.36 (KHTML, like Gecko) '
#                             'Chrome/114.0.0.0 Safari/537.36')
chrome_option.add_argument('--no-sandbox')  # Required for CI
chrome_option.add_argument('--disable-dev-shm-usage')  # Fixes shared memory issues

driver = webdriver.Chrome(options=chrome_option)
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

# Navigate through menus using waits instead of sleeps
try:
    electronics_btn = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, 'Electronics')))
    electronics_btn.click()

    computer_accessories_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.nav-a[aria-label='Computers & Accessories']")))
    computer_accessories_btn.click()

    components_btn = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, 'Components')))
    components_btn.click()

    graphics_cards_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="s-refinements"]/div[1]/ul/li[10]/span/a/span')))
    graphics_cards_btn.click()

    features_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="a-autoid-0"]/span')))
    features_btn.click()

    best_seller_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'li[aria-labelledby="s-result-sort-select_5"]')))
    best_seller_btn.click()

except TimeoutException:
    print("One of the navigation elements did not appear.")
 #This will return a list of items



#Number of words for each key, purpose to split the string of each detail from there key
details_keys_split = {
    'Brand': 1,
    'Product Dimensions': 2,
    'Item model number': 3,
    'Series': 1,
    'Resolution': 1,
    'Memory Clock Speed': 3,
    'Graphics Coprocessor': 2,
    'Graphics Chipset Brand': 3,
    'Graphics RAM Type': 3,
    'Graphics Card Ram Size': 4,
    'Wattage': 1
}


def product_information():
    try:
        # Exctract review stars
        customer_reviews = float(driver.find_element(By.XPATH, '//*[@id="acrPopover"]/span[1]/a/span').text)
    except NoSuchElementException:
        customer_reviews = None
    # Getting number of reviews
    try:
        reviews_number = driver.find_element(By.ID, 'acrCustomerReviewText').text
        reviews_number = reviews_number.split(' ')
        reviews_number = int(reviews_number[0].replace(',', ''))
    except NoSuchElementException:
        reviews_number = 0  # The product isn't rated

    # the past_month_product_bought results is at least this value
    try:
        last_month_sold = driver.find_element(By.ID, 'social-proofing-faceout-title-tk_bought').text
        last_month_sold = last_month_sold.split('+')
        last_month_sold = int(last_month_sold[0])
    except NoSuchElementException:
        last_month_sold = None

    # Get the price currency
    currency = driver.find_element(By.CLASS_NAME, 'a-price-symbol').text

    # Get the Price
    price_whole = driver.find_element(By.CLASS_NAME, 'a-price-whole').text
    if ',' in price_whole:
        price_whole = price_whole.replace(',', '')
    price_fraction = driver.find_element(By.CLASS_NAME, 'a-price-fraction').text
    if price_whole and price_fraction:
        actual_price = float(price_whole + '.' + price_fraction)
    else:
        actual_price = None

    # check and get discount if any
    try:
        discount_text = driver.find_element(By.XPATH,
                                            '//*[@id="corePriceDisplay_desktop_feature_div"]/div[1]/span[2]').text
        discount_str = discount_text.replace('-', '').replace('%', '').strip()
        if discount_str.isdigit():
            discount = int(discount_str)
        else:
            discount = 0
    except NoSuchElementException:
        discount = 0

    # get recommended retail price (original price) if any
    try:
        rrp_price_text = driver.find_element(By.XPATH,
                                             '//*[@id="corePriceDisplay_desktop_feature_div"]/div[2]/span/span[1]/span[2]/span/span[2]').text
        if rrp_price_text == '':
            rrp_price = actual_price
        else:
                rrp_price_text = float(rrp_price_text.replace('£', '').replace(',','').strip())
                rrp_price =float(rrp_price_text)
        # try:
        #     rrp_price = float(rrp_price_string)
        # except NoSuchElementException:
        #     rrp_price = actual_price
    except NoSuchElementException:
        rrp_price = actual_price


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
#passing details_keys_split as a parameter is optional, doing this can let us  use the function for totally different type of product
def parse_product_details(details_keys_split):
    product_specs = {}
    try:
        product_details = driver.find_element(By.CSS_SELECTOR, 'table[id="productDetails_techSpec_section_1"]').text
    except NoSuchElementException:
      for key in details_keys_split:
          product_specs[key] = 'unknown'
      return product_specs


    for detail in product_details.split('\n'):
        for key, split_count in details_keys_split.items():
            if detail.startswith(key):
                split_count = details_keys_split[key]
                info = detail.split(' ', split_count)
                product_specs[key] = info[-1].strip()
                break

    for key in details_keys_split:
        if key not in product_specs:
            product_specs[key] = 'unknown'

    return product_specs

all_products = {} #holding all product details under their asin

def processing_all_products():
    items = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
    filtered_items = [item for item in items if 'Sponsored' not in item.text and 'See options' not in item.text ]

    for item in filtered_items:
        # Exctract the Identifier of the product
        asin = item.get_attribute('data-asin')  # get unique serial number
        if not asin:
            continue
        #Go inside product
        item.find_element(By.CSS_SELECTOR, 'div[data-cy="title-recipe"]').click()
        sleep(2)

        #getting scraping timestamp for each product
        scrape_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        #Get all product details
        product_overview = product_information()
        product_spec = parse_product_details(details_keys_split)

        #combine both dictionaries under the ASIN
        all_products[asin] = {
            'scrape time': scrape_time,
            'product overview': product_overview,
            'product specifications': product_spec
        }

        #Go back to product list
        driver.back()
    return  all_products



page_number = 1
while page_number <= 5 :
    processing_all_products()
    try:
        next_page = driver.find_element(By.CSS_SELECTOR, "a.s-pagination-item.s-pagination-next")
        if next_page.is_enabled():
            next_page.click()
            page_number += 1
            sleep(2)
        else:
            break

    except NoSuchElementException:
        break



print(all_products)



#connect to mysql database
connection = mysql.connector.connect(
    host='127.0.0.1',
    port = 3306,
    user="root",
    password="root",
    database="amazon"
)

#create a cursor object to execute sql queries like inserting data
cursor = connection.cursor()

# #excute insert statement to fill database
for asin, product_data in all_products.items():
    spec = product_data['product specifications']
    overview = product_data['product overview']


    insert_product_details = """
        INSERT INTO product_details(
        asin ,
        original_price ,
        series ,
        item_model_number ,
        brand ,
        graphics_coprocessor ,
        graphics_chipset_brand ,
        graphics_RAM_type ,
        graphics_card_RAM_size ,
        memory_clock_speed ,
        product_dimensions ,
        resolution ,
        wattage )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            original_price = IF(VALUES(original_price) <> original_price, VALUES(original_price), original_price),
            series = IF(VALUES(series) <> series, VALUES(series), series),
            item_model_number = IF(VALUES(item_model_number) <> item_model_number, VALUES(item_model_number), item_model_number),
            brand = IF(VALUES(brand) <> brand, VALUES(brand), brand),
            graphics_coprocessor = IF(VALUES(graphics_coprocessor) <> graphics_coprocessor, VALUES(graphics_coprocessor), graphics_coprocessor),
            graphics_chipset_brand = IF(VALUES(graphics_chipset_brand) <> graphics_chipset_brand, VALUES(graphics_chipset_brand), graphics_chipset_brand),
            graphics_RAM_type = IF(VALUES(graphics_RAM_type) <> graphics_RAM_type, VALUES(graphics_RAM_type), graphics_RAM_type),
            graphics_card_RAM_size = IF(VALUES(graphics_card_RAM_size) <> graphics_card_RAM_size, VALUES(graphics_card_RAM_size), graphics_card_RAM_size),
            memory_clock_speed = IF(VALUES(memory_clock_speed) <> memory_clock_speed, VALUES(memory_clock_speed), memory_clock_speed),
            product_dimensions = IF(VALUES(product_dimensions) <> product_dimensions, VALUES(product_dimensions), product_dimensions),
            resolution = IF(VALUES(resolution) <> resolution, VALUES(resolution), resolution),
            wattage = IF(VALUES(wattage) <> wattage, VALUES(wattage), wattage)
        """

    cursor.execute(insert_product_details, (
        asin,
        overview['original price'],
        spec['Series'],
        spec['Item model number'],
        spec['Brand'],
        spec['Graphics Coprocessor'],
        spec['Graphics Chipset Brand'],
        spec['Graphics RAM Type'],
        spec['Graphics Card Ram Size'],
        spec['Memory Clock Speed'],
        spec['Product Dimensions'],
        spec['Resolution'],
        spec['Wattage']


    ))

    insert_product_overview = """
    INSERT INTO scrape_results (
    scrape_time,
    asin,
    actual_price,
    discount,
    last_month_sold,
    product_rating,
    number_of_reviews)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    cursor.execute(insert_product_overview,(
        product_data['scrape time'],
        asin,
        overview['actual price'],
        overview['discount %'],
        overview['at least last month sold'],
        overview['customer reviews'],
        overview['reviews number']
    ))

    

connection.commit()
cursor.close()
connection.close()