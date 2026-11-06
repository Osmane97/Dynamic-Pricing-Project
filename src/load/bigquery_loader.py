from google.cloud import bigquery

from src import config

TABLE_ID = f"{config.GCP_PROJECT_ID}.amazon_raw.gpu_scrapes"


def to_row(asin, product_data):
    overview = product_data['product overview']
    spec = product_data['product specifications']

    return {
        'scrape_time': product_data['scrape time'],
        'asin': asin,
        'currency': overview['currency'],
        'actual_price': overview['actual price'],
        'original_price': overview['original price'],
        'discount_percent': overview['discount %'],
        'last_month_sold': overview['at least last month sold'],
        'product_rating': overview['customer reviews'],
        'number_of_reviews': overview['reviews number'],
        'brand': spec['Brand'],
        'series': spec['Series'],
        'item_model_number': spec['Item model number'],
        'graphics_coprocessor': spec['Graphics Coprocessor'],
        'graphics_chipset_brand': spec['Graphics Chipset Brand'],
        'graphics_ram_type': spec['Graphics RAM Type'],
        'graphics_card_ram_size': spec['Graphics Card Ram Size'],
        'memory_clock_speed': spec['Memory Clock Speed'],
        'product_dimensions': spec['Product Dimensions'],
        'resolution': spec['Resolution'],
        'wattage': spec['Wattage'],
    }


def load(all_products):
    client = bigquery.Client(project=config.GCP_PROJECT_ID)
    rows = [to_row(asin, data) for asin, data in all_products.items()]

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_json(rows, TABLE_ID, job_config=job_config)
    job.result()  # wait for the job, and raise an error if it failed

    print(f"Loaded {job.output_rows} rows into {TABLE_ID}")
