with scrapes as (

    select * from {{ ref('stg_gpu_scrapes') }}

),

ranked as (

    select
        *,
        min(scrape_time) over (partition by asin) as first_seen_at,
        max(scrape_time) over (partition by asin) as last_seen_at,
        count(*) over (partition by asin) as times_scraped
    from scrapes
    -- keep one row per product: the newest scrape that has specs
    qualify row_number() over (
        partition by asin
        order by brand is not null desc, scrape_time desc
    ) = 1

)

select
    asin,
    brand,
    series,
    item_model_number,
    graphics_coprocessor,
    graphics_chipset_brand,
    graphics_ram_type,
    ram_gb,
    memory_clock_speed,
    product_dimensions,
    resolution,
    first_seen_at,
    last_seen_at,
    times_scraped
from ranked
