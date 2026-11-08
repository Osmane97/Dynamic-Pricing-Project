with scrapes as (

    select * from {{ ref('stg_gpu_scrapes') }}

)

select
    -- one row per product per scrape
    concat(asin, '|', format_timestamp('%Y-%m-%d %H:%M:%S', scrape_time)) as price_id,
    asin,
    scrape_time,
    scrape_date,

    -- never average across currencies: always filter or group by this
    currency,
    actual_price,
    original_price,
    discount_percent,
    discount_percent > 0 as is_discounted,

    last_month_sold,
    product_rating,
    number_of_reviews
from scrapes
