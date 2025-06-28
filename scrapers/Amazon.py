

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from time import sleep
from selenium import webdriver
import datetime


URL = 'https://www.amazon.co.uk/'

#Keep chrome open
chrome_option = webdriver.ChromeOptions()
chrome_option.add_experimental_option('detach', True)

driver = webdriver.Chrome(options = chrome_option)
driver.get(URL)

# Continue shopping button appears sometimes
try:
    continue_shopping = driver.find_element(By.XPATH, '/html/body/div/div[1]/div[3]/div/div/form/div/div/span/span/button')
    continue_shopping.click()
    sleep(1)
except NoSuchElementException:
    pass

# decline cookies if there's any
try:
    decline_cookies = driver.find_element(By.ID, 'sp-cc-rejectall-link')
    decline_cookies.click()
    sleep(2)
except NoSuchElementException:
    pass

electronics_btn = driver.find_element(By.LINK_TEXT, 'Electronics').click()
sleep(2)

computer_Accessories_btn = driver.find_element(By.CSS_SELECTOR, 'a[aria-label="Computers & Accessories"]').click()
sleep(2)

components_btn = driver.find_element(By.XPATH, '//*[@id="s-refinements"]/div[1]/ul/li[4]/span/a/span').click()
sleep(2)

Graphics_cards_btn = driver.find_element(By.XPATH, '//*[@id="s-refinements"]/div[1]/ul/li[10]/span/a/span').click()
sleep(2)

features_btn = driver.find_element(By.XPATH, '//*[@id="a-autoid-0"]/span').click()
sleep(1)

best_seller_btn = driver.find_element(By.CSS_SELECTOR, 'li[aria-labelledby="s-result-sort-select_5"]').click()

items = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]') #This will return a list of items


#filtered_items = [item for item in items if 'Sponsored' not in item.text or 'See options' not in item.text ]
# # Exctract the Identifier of the product
# asin = filtered_items[0].get_attribute('data-asin')  # get unique serial number
# #Click on the item
# filtered_items[0].find_element(By.CSS_SELECTOR, 'div[data-cy="title-recipe"]')
# filtered_items[0].click()

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
        customer_reviews = 'No review'
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
        last_month_sold = 'unknown'

    # Get the price currency
    currency = driver.find_element(By.CLASS_NAME, 'a-price-symbol').text

    # Get the Price
    price_whole = driver.find_element(By.CLASS_NAME, 'a-price-whole').text
    if ',' in price_whole:
        price_whole = price_whole.replace(',', '')
    price_fraction = driver.find_element(By.CLASS_NAME, 'a-price-fraction').text
    actual_price = float(price_whole + '.' + price_fraction)

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
#passing details_keys_split as a parameter is optional, doing this can let us to use the function for totally different type of product
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

filtered_items = [item for item in items if 'Sponsored' not in item.text and 'See options' not in item.text ]




for item in filtered_items:
    # Exctract the Identifier of the product
    asin = item.get_attribute('data-asin')  # get unique serial number

    #Go inside product
    item.find_element(By.CSS_SELECTOR, 'div[data-cy="title-recipe"]').click()
    sleep(2)

    #getting scraping timestamp for each product
    scrape_time = datetime.datetime.now().strftime("%x %X")

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

print(all_products)


