import mysql.connector

from src import config

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

def load(all_products):
    connection = mysql.connector.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
    )
    cursor = connection.cursor()

    try:
        for asin, product_data in all_products.items():
            spec = product_data['product specifications']
            overview = product_data['product overview']

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

            cursor.execute(insert_product_overview, (
                product_data['scrape time'],
                asin,
                overview['actual price'],
                overview['discount %'],
                overview['at least last month sold'],
                overview['customer reviews'],
                overview['reviews number']
            ))

        connection.commit()
    finally:
        cursor.close()
        connection.close()
