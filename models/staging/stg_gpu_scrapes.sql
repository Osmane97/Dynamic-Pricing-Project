with source as (

    select * from {{ source('amazon_raw', 'gpu_scrapes') }}

),

ram_parts as (

    -- RAM arrives as '16 GB', '16384 MB', '8' or 'unknown', so split out the number and the unit
    select
        *,
        safe_cast(regexp_extract(graphics_card_ram_size, r'[\d.]+') as numeric) as ram_number,
        lower(graphics_card_ram_size) like '%mb%' as ram_in_mb
    from source

),

cleaned as (

    select
        -- keys and time
        asin,
        scrape_time,
        date(scrape_time) as scrape_date,

        -- prices
        case currency
            when '£' then 'GBP'
            else currency
        end as currency,
        actual_price,
        original_price,
        discount_percent,

        -- popularity
        last_month_sold,
        product_rating,
        number_of_reviews,

        -- specs: the scraper saves 'unknown' when Amazon has no value
        nullif(brand, 'unknown') as brand,
        nullif(series, 'unknown') as series,
        nullif(item_model_number, 'unknown') as item_model_number,
        nullif(graphics_coprocessor, 'unknown') as graphics_coprocessor,
        nullif(graphics_chipset_brand, 'unknown') as graphics_chipset_brand,
        nullif(graphics_ram_type, 'unknown') as graphics_ram_type,
        nullif(memory_clock_speed, 'unknown') as memory_clock_speed,
        nullif(product_dimensions, 'unknown') as product_dimensions,
        nullif(resolution, 'unknown') as resolution,

        -- RAM in GB. MB values are rounded to whole GB, except cards under 1 GB
        case
            when not ram_in_mb then ram_number
            when ram_number < 1024 then round(ram_number / 1024, 1)
            else round(ram_number / 1024)
        end as ram_gb

    from ram_parts

)

select * from cleaned
