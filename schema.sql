CREATE TABLE IF NOT EXISTS product_details (
    asin VARCHAR(12) NOT NULL PRIMARY KEY,
    original_price FLOAT NOT NULL,
    series VARCHAR(100),
    item_model_number VARCHAR(100),
    brand VARCHAR(20),
    graphics_coprocessor VARCHAR(40),
    graphics_chipset_brand VARCHAR(20),
    graphics_RAM_type VARCHAR(100),
    graphics_card_RAM_size VARCHAR(10),
    memory_clock_speed VARCHAR(20),
    product_dimensions VARCHAR(50),
    resolution VARCHAR(30),
    wattage VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS scrape_results (
    scrape_time TIMESTAMP NOT NULL,
    asin VARCHAR(12) NOT NULL,
    actual_price FLOAT NOT NULL,
    discount FLOAT,
    last_month_sold INT,
    product_rating FLOAT,
    number_of_reviews INT,
    PRIMARY KEY (scrape_time, asin),
    FOREIGN KEY (asin) REFERENCES product_details(asin)
);
